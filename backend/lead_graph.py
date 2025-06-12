from typing import List
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
import csv
import os
import sqlite3
from googleapiclient.http import MediaIoBaseUpload
import io
from gdrive_utils import get_drive_service  # Assuming gdrive_utils is in the same directory or accessible
from langchain_google_community import GoogleDriveLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.cache import SQLiteCache
import langchain
from langchain_core.runnables import RunnableMap
from langchain_community.cache import InMemoryCache
# Need to import datetime if used in save_lead_to_drive
from datetime import datetime
import traceback # Added for detailed traceback

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
print(f"[LEAD_GRAPH_INIT] llm initialized: {llm is not None}")

structured_llm = llm.with_structured_output(Lead)
print(f"[LEAD_GRAPH_INIT] structured_llm initialized: {structured_llm is not None}")

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
    save_lead_to_drive(lead)
    return lead

# ✅ RAG setup
FOLDER_ID = "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN"
# TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json") # Unused

def load_documents():
    print(f"[LEAD_GRAPH_INIT] Attempting to load documents from Google Drive folder: {FOLDER_ID}")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    print(f"[LEAD_GRAPH_INIT] Using service account key from env var GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
    
    if not creds_path:
        print("[LEAD_GRAPH_INIT] CRITICAL ERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        return []
        
    if not os.path.isfile(creds_path):
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR: Credentials file not found at path: {creds_path}")
        return []

    try:
        loader = GoogleDriveLoader(
            folder_id=FOLDER_ID,
            service_account_key=creds_path, # Use the variable
            file_types=["document", "pdf", "sheet"],
            recursive=True,
        )
        print("[LEAD_GRAPH_INIT] GoogleDriveLoader initialized.")
        docs = loader.load()
        print(f"[LEAD_GRAPH_INIT] loader.load() completed. Number of documents loaded: {len(docs) if docs is not None else 'None'}")
        if not docs: # This means docs is an empty list
            print("[LEAD_GRAPH_INIT] No documents were loaded. Check folder content, permissions, and loader configuration. Also check logs above for any specific errors from the loader.")
        return docs
    except Exception as e:
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR loading documents from Google Drive: {e}")
        print(f"[LEAD_GRAPH_INIT] Traceback: {traceback.format_exc()}")
        return []

def setup_rag():
    docs = load_documents()
    # The print for number of docs is now more detailed within load_documents
    print(f"[LEAD_GRAPH_INIT] setup_rag: docs loaded status: {docs is not None}, number of docs: {len(docs) if docs is not None else 'N/A'}")
    
    if not docs: # Handles None or empty list
        print("[LEAD_GRAPH_INIT] setup_rag: No documents loaded or an error occurred, RAG chain will not be functional.")
        return None

    embeddings = HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'}
    )

    vectorstore = FAISS.from_documents(docs, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2, "score_threshold": 0.8})

    prompt = ChatPromptTemplate.from_template("""
    ### Rôle ###
    Vous êtes un assistant virtuel expert de TRANSLAB INTERNATIONAL...
    ### Contexte ###
    {context}
    ### Question ###
    {question}
    """) # Simplified prompt for now

    rag_chain_local = (
        RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"]
            # "history": lambda x: x.get("history", []) # Removed for simplicity, can add back
        }) | prompt | llm
    )
    print(f"[LEAD_GRAPH_INIT] setup_rag: returning rag_chain: {rag_chain_local is not None}")
    return rag_chain_local

rag_chain = setup_rag()
print(f"[LEAD_GRAPH_INIT] Global rag_chain initialized: {rag_chain is not None}")

if __name__ == "__main__":
    # This section is for local testing
    print("Testing lead_graph.py locally...")
    if not os.getenv("GROQ_API_KEY"):
        print("Warning: GROQ_API_KEY not set.")
    
    # Test RAG chain
    if rag_chain:
        print("\n--- RAG Chain Test ---")
        try:
            response = rag_chain.invoke({"question": "Quels sont vos services ?"})
            print(f"RAG Response: {response.content if hasattr(response, 'content') else response}")
        except Exception as e:
            print(f"Error invoking RAG chain: {e}")
    else:
        print("\n--- RAG Chain Test ---")
        print("RAG chain is None. Skipping RAG test.")

    # Test Lead Extraction
    print("\n--- Lead Extraction Test ---")
    text = "Bonjour, je suis Jean Dupont. Mon email est jean.dupont@example.com et mon tel est 0123456789."
    try:
        lead = collect_lead_from_text(text)
        print(f"Extracted Lead: {lead}")
    except Exception as e:
        print(f"Error collecting lead: {e}")
