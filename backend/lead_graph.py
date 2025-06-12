from typing import List
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
import csv
import os
import sqlite3
import traceback
from googleapiclient.http import MediaIoBaseUpload
import io
# from gdrive_utils import get_drive_service # Still commented out
try:
    from gdrive_utils import get_drive_service
except ImportError:
    print("[LEAD_GRAPH_INIT] Warning: gdrive_utils or get_drive_service not found. `save_lead_to_drive` might fail if re-enabled.")
    def get_drive_service():
        print("Error: get_drive_service not available due to missing gdrive_utils (currently commented out).")
        return None

from langchain_google_community import GoogleDriveLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.cache import SQLiteCache
import langchain
from langchain_core.runnables import RunnableMap
from langchain_community.cache import InMemoryCache
from datetime import datetime

langchain.llm_cache = SQLiteCache(database_path=os.path.join(os.path.dirname(__file__), ".langchain.db"))
embedding_cache = {}

def get_cached_embeddings(text: str, embeddings: HuggingFaceEmbeddings) -> List[float]:
    cache_key = f"embed_{hash(text)}"
    if cache_key in embedding_cache: return embedding_cache[cache_key]
    embedding = embeddings.embed_query(text)
    embedding_cache[cache_key] = embedding
    return embedding

class Lead(BaseModel):
    name: str = Field(description="Nom complet de l'utilisateur")
    email: str = Field(description="Adresse e-mail valide de l'utilisateur")
    phone: str = Field(description="Numéro de téléphone de l'utilisateur")

llm = ChatGroq(model="llama3-8b-8192", temperature=0, groq_api_key=os.getenv("GROQ_API_KEY") or "...")
print(f"[LEAD_GRAPH_INIT] llm initialized: {llm is not None}")

structured_llm = llm.with_structured_output(Lead) if llm else None
print(f"[LEAD_GRAPH_INIT] structured_llm initialized: {structured_llm is not None}")

def save_lead_to_csv(lead: Lead, filename=None):
    if filename is None: filename = os.path.join(os.path.dirname(__file__), "leads.csv")
    file_exists = os.path.isfile(filename)
    with open(filename, mode="a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["name", "email", "phone"])
        if not file_exists: writer.writeheader()
        writer.writerow(lead.model_dump())

def save_lead_to_sqlite(lead: Lead, db_path=None):
    if db_path is None: db_path = os.path.join(os.path.dirname(__file__), "leads.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, phone TEXT)")
    c.execute("INSERT INTO leads (name, email, phone) VALUES (?, ?, ?)", (lead.name, lead.email, lead.phone))
    conn.commit()
    conn.close()

# def save_lead_to_drive(lead: Lead): # Still commented out
#     print("[Google Drive] save_lead_to_drive called, but is temporarily disabled.")
#     return None

def collect_lead_from_text(text: str) -> Lead:
    if structured_llm is None:
        print("[COLLECT_LEAD] structured_llm is None. Cannot extract lead.")
        return Lead(name="Error: LLM N/A", email="Error: LLM N/A", phone="Error: LLM N/A")
    lead_data = structured_llm.invoke(text) # Renamed variable to avoid conflict with class
    save_lead_to_csv(lead_data)
    save_lead_to_sqlite(lead_data)
    # save_lead_to_drive(lead_data) # Still commented out
    return lead_data


ACTIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN")

def load_documents(): # This function will not be called by the stubbed setup_rag
    print(f"[LEAD_GRAPH_INIT] Attempting to load documents. Context Folder ID (not used for specific ID load): '{ACTIVE_FOLDER_ID}'")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    print(f"[LEAD_GRAPH_INIT] Using service account key from env var GOOGLE_APPLICATION_CREDENTIALS: '{creds_path}'")

    if not creds_path:
        print("[LEAD_GRAPH_INIT] CRITICAL ERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        return []
    if not os.path.isfile(creds_path):
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR: Credentials file not found at path: '{creds_path}'")
        return []
    else:
        print(f"[LEAD_GRAPH_INIT] Credentials file confirmed to exist at: '{creds_path}'")

    try:
        specific_doc_id = "14K4ZhA334LNGrCG5gYHLgcr3TWVu-Dpki1Kw4TI93EU"
        print(f"[LEAD_GRAPH_INIT] Attempting to load new specific document ID: '{specific_doc_id}'")

        loader = GoogleDriveLoader(
            service_account_key=creds_path,
            document_ids=[specific_doc_id],
            file_types=["pdf"]
        )
        print(f"[LEAD_GRAPH_INIT] GoogleDriveLoader initialized for specific PDF ID: '{specific_doc_id}'.")
        docs = loader.load()

        print(f"[LEAD_GRAPH_INIT] loader.load() completed. Number of documents loaded: {len(docs) if docs is not None else 'None'}")
        if not docs:
            print(f"[LEAD_GRAPH_INIT] No document loaded for specific PDF ID: '{specific_doc_id}'. Please ensure: \n1. The ID is absolutely correct. \n2. The file is a PDF. \n3. The service account ('{os.getenv('GDRIVE_SERVICE_ACCOUNT_EMAIL_FOR_LOGGING', 'render3@intricate-sweep-453002-p1.iam.gserviceaccount.com')}') has 'Viewer' permission DIRECTLY on this file. \n4. The file is not in the trash or in a restricted state preventing API access.")
        return docs
    except Exception as e:
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR loading specific document from Google Drive: '{e}'")
        print(f"[LEAD_GRAPH_INIT] Traceback: {traceback.format_exc()}")
        return []

def setup_rag():
    print("[LEAD_GRAPH_INIT] setup_rag: Temporarily stubbed out. Returning None.")
    return None

rag_chain = setup_rag()
print(f"[LEAD_GRAPH_INIT] Global rag_chain initialized: {rag_chain is not None}") # This will print False

if __name__ == "__main__":
    print("Testing lead_graph.py locally...")
    if not os.getenv("GROQ_API_KEY"): print("Warning: GROQ_API_KEY not set.")
    if rag_chain: # This will be false
        print("\n--- RAG Chain Test ---")
        try:
            response = rag_chain.invoke({"question": "Quels sont vos services ?"})
            print(f"RAG Response: '{response.content if hasattr(response, 'content') else response}'")
        except Exception as e: print(f"Error invoking RAG chain: '{e}'")
    else: print("\n--- RAG Chain Test --- \nRAG chain is None. Skipping RAG test.")
    print("\n--- Lead Extraction Test ---")
    text = "Bonjour, je suis Jean Dupont. Mon email est jean.dupont@example.com et mon tel est 0123456789."
    try:
        if structured_llm:
            # Renamed variable in collect_lead_from_text call if it was conflicting
            collected_lead = collect_lead_from_text(text)
            print(f"Extracted Lead: '{collected_lead}'")
        else:
            print("structured_llm is None, skipping lead extraction test.")
    except Exception as e: print(f"Error collecting lead: '{e}'")

