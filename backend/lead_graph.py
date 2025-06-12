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
        # Use the same FOLDER_ID logic for consistency if saving leads to the same Drive area
        folder_id_to_save = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN")
        file_metadata = {
            'name': f"lead_{lead.phone}.txt",
            'mimeType': 'text/plain',
            'parents': [folder_id_to_save]
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
# Use environment variable for Folder ID, with a fallback to the previously hardcoded one.
ACTIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN")
# TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json") # Unused

def load_documents():
    # This print now uses ACTIVE_FOLDER_ID to show what's effectively being considered for folder scans (though not used in this specific doc test)
    print(f"[LEAD_GRAPH_INIT] Attempting to load documents. Effective Folder ID for general scanning (if used): {ACTIVE_FOLDER_ID}")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    print(f"[LEAD_GRAPH_INIT] Using service account key from env var GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
    
    if not creds_path:
        print("[LEAD_GRAPH_INIT] CRITICAL ERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        return []
        
    if not os.path.isfile(creds_path):
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR: Credentials file not found at path specified by GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
        return []
    else:
        print(f"[LEAD_GRAPH_INIT] Credentials file confirmed to exist at: {creds_path}")

    try:
        specific_doc_id = "1ZffgKTE5uE0OT6dTjt3Y90dM59qRQ4-TxCA7VeV7WLs"
        print(f"[LEAD_GRAPH_INIT] Attempting to load specific document ID: {specific_doc_id}")
        
        loader = GoogleDriveLoader(
            # folder_id=ACTIVE_FOLDER_ID, # Commented out for specific doc test
            document_ids=[specific_doc_id], 
            service_account_key=creds_path
            # recursive=True, # Not needed for specific document_ids
            # file_types=["document", "pdf", "sheet"], # Not needed for specific document_ids
        )
        print("[LEAD_GRAPH_INIT] GoogleDriveLoader initialized for specific document.")
        docs = loader.load()
        print(f"[LEAD_GRAPH_INIT] loader.load() completed. Number of documents loaded: {len(docs) if docs is not None else 'None'}")
        if not docs:
            print(f"[LEAD_GRAPH_INIT] No document loaded for specific ID: {specific_doc_id}. Check permissions on this specific file for the service account, or if the ID is correct and the file is not trashed.")
        return docs
    except Exception as e:
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR loading specific document from Google Drive: {e}")
        print(f"[LEAD_GRAPH_INIT] Traceback: {traceback.format_exc()}")
        return []

def setup_rag():
    docs = load_documents()
    print(f"[LEAD_GRAPH_INIT] setup_rag: docs loaded status: {docs is not None}, number of docs: {len(docs) if docs is not None else 'N/A'}")
    
    if not docs: 
        print("[LEAD_GRAPH_INIT] setup_rag: No documents loaded, RAG chain will not be functional.")
        return None

    embeddings = HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'}
    )

    vectorstore = FAISS.from_documents(docs, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 1 if len(docs) == 1 else 2, "score_threshold": 0.8}) # Adjust k if only 1 doc

    prompt = ChatPromptTemplate.from_template("""
    ### Rôle ###
    Vous êtes un assistant virtuel expert de TRANSLAB INTERNATIONAL...
    ### Contexte ###
    {context}
    ### Question ###
    {question}
    """)

    rag_chain_local = (
        RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"]
        }) | prompt | llm
    )
    print(f"[LEAD_GRAPH_INIT] setup_rag: returning rag_chain: {rag_chain_local is not None}")
    return rag_chain_local

rag_chain = setup_rag()
print(f"[LEAD_GRAPH_INIT] Global rag_chain initialized: {rag_chain is not None}")

if __name__ == "__main__":
    print("Testing lead_graph.py locally...")
    if not os.getenv("GROQ_API_KEY"):
        print("Warning: GROQ_API_KEY not set.")
    
    if rag_chain:
        print("\n--- RAG Chain Test ---")
        try:
            response = rag_chain.invoke({"question": "Quel est le contenu du document?"}) # Generic question
            print(f"RAG Response: {response.content if hasattr(response, 'content') else response}")
        except Exception as e:
            print(f"Error invoking RAG chain: {e}")
    else:
        print("\n--- RAG Chain Test ---")
        print("RAG chain is None. Skipping RAG test.")

    print("\n--- Lead Extraction Test ---")
    text = "Bonjour, je suis Jean Dupont. Mon email est jean.dupont@example.com et mon tel est 0123456789."
    try:
        lead = collect_lead_from_text(text)
        print(f"Extracted Lead: {lead}")
    except Exception as e:
        print(f"Error collecting lead: {e}")

