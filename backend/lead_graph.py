from typing import List
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
import csv
import os
import sqlite3
from googleapiclient.http import MediaIoBaseUpload
import io
from gdrive_utils import get_drive_service  
from langchain_google_community import GoogleDriveLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.cache import SQLiteCache
import langchain
from langchain_core.runnables import RunnableMap
from langchain_community.cache import InMemoryCache

# 💾 Cache
langchain.llm_cache = SQLiteCache(database_path=os.path.join(os.path.dirname(__file__), ".langchain.db"))
embedding_cache = {}

# ✅ Embedding avec cache
def get_cached_embeddings(text: str, embeddings: HuggingFaceEmbeddings) -> List[float]:
    cache_key = f"embed_{hash(text)}"
    if cache_key in embedding_cache:
        return embedding_cache[cache_key]
    embedding = embeddings.embed_query(text)
    embedding_cache[cache_key] = embedding
    return embedding

# ✅ Structure de données
class Lead(BaseModel):
    name: str = Field(description="Nom complet de l'utilisateur")
    email: str = Field(description="Adresse e-mail valide de l'utilisateur")
    phone: str = Field(description="Numéro de téléphone de l'utilisateur")

# ✅ Initialiser Groq
llm = ChatGroq(
    model="llama3-8b-8192",
    temperature=0,
    groq_api_key=os.getenv("GROQ_API_KEY") or "..."  # 🔐 pense à sécuriser cette clé
)

structured_llm = llm.with_structured_output(Lead)

# ✅ Sauvegardes
def save_lead_to_csv(lead: Lead, filename=None):
    if filename is None:
        filename = os.path.join(os.path.dirname(__file__), "leads.csv")
    file_exists = os.path.isfile(filename)
    with open(filename, mode="a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["name", "email", "phone"])
        if not file_exists:
            writer.writeheader()
        writer.writerow(lead.model_dump())

def save_lead_to_sqlite(lead: Lead, db_path=None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "leads.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT
        )
    """)
    c.execute("INSERT INTO leads (name, email, phone) VALUES (?, ?, ?)",
              (lead.name, lead.email, lead.phone))
    conn.commit()
    conn.close()

def save_lead_to_drive(lead: Lead):
    """Sauvegarde le lead dans Google Drive sous forme de fichier texte"""
    try:
        drive = get_drive_service()
        
        file_metadata = {
            'name': f"lead_{lead.phone}.txt",
            'mimeType': 'text/plain',
            'parents': [os.getenv('GOOGLE_DRIVE_FOLDER_ID')]  # Optionnel : dossier spécifique
        }
        
        content = f"""Nom: {lead.name}
Email: {lead.email}
Téléphone: {lead.phone}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode('utf-8')),
            mimetype='text/plain'
        )
        
        file = drive.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"[Google Drive] Lead sauvegardé (ID: {file.get('id')})")
        return file
        
    except Exception as e:
        print(f"[Google Drive] Erreur : {str(e)}")
        return None
        
def collect_lead_from_text(text: str) -> Lead:
    lead = structured_llm.invoke(text)
    save_lead_to_csv(lead)
    save_lead_to_sqlite(lead)
    save_lead_to_drive(lead)  # Nouvelle fonctionnalité
    return lead

# ✅ RAG setup
FOLDER_ID = "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN"
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")

def load_documents():
    try:
        loader = GoogleDriveLoader(
            folder_id=FOLDER_ID,
            token_path=TOKEN_PATH,
            file_types=["document", "pdf", "sheet"],
            recursive=True
        )
        return loader.load()
    except Exception as e:
        print(f"[❌ RAG] Erreur de chargement : {e}")
        return []

def setup_rag():
    docs = load_documents()
    if not docs:
        return None

    embeddings = HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'}
    )

    for doc in docs:
        get_cached_embeddings(doc.page_content[:1000], embeddings)

    vectorstore = FAISS.from_documents(docs, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2, "score_threshold": 0.8})

    prompt = ChatPromptTemplate.from_template("""
    ### Rôle ###
    Vous êtes un assistant virtuel expert de TRANSLAB INTERNATIONAL...
    ### Contexte ###
    {context}
    ### Question ###
    {question}
    """)

    rag_chain = (
        RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"]
        }) | prompt | llm
    )
    return rag_chain

rag_chain = setup_rag()

if __name__ == "__main__":
    text = "Bonjour, je m'appelle Alice Martin. Vous pouvez me joindre à alice.martin@email.com ou au 06 12 34 56 78."
    lead = collect_lead_from_text(text)
    print("✅ Lead extrait :", lead)
