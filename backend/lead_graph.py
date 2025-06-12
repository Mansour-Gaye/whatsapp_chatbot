from typing import List
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
import csv
import os
import sqlite3
import traceback # Moved import traceback to the top
from googleapiclient.http import MediaIoBaseUpload
import io
# from gdrive_utils import get_drive_service  # Temporarily commented out for circular import diagnosis
from langchain_google_community import GoogleDriveLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.cache import SQLiteCache
import langchain
from langchain_core.runnables import RunnableMap
from langchain_community.cache import InMemoryCache
from langchain_google_community import GoogleDriveLoader

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

# def save_lead_to_drive(lead: Lead): # Temporarily commented out for circular import diagnosis
#     """Sauvegarde le lead dans Google Drive sous forme de fichier texte"""
#     try:
#         drive = get_drive_service()
        
#         file_metadata = {
#             'name': f"lead_{lead.phone}.txt",
#             'mimeType': 'text/plain',
#             'parents': [os.getenv('GOOGLE_DRIVE_FOLDER_ID')]  # Optionnel : dossier spécifique
#         }
        
#         content = f"""Nom: {lead.name}
# Email: {lead.email}
# Téléphone: {lead.phone}
# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
#         media = MediaIoBaseUpload(
#             io.BytesIO(content.encode('utf-8')),
#             mimetype='text/plain'
#         )
        
#         file = drive.files().create(
#             body=file_metadata,
#             media_body=media,
#             fields='id'
#         ).execute()
        
#         print(f"[Google Drive] Lead sauvegardé (ID: {file.get('id')})")
#         return file
        
#     except Exception as e:
#         print(f"[Google Drive] Erreur : {str(e)}")
#         return None
        
def collect_lead_from_text(text: str) -> Lead:
    lead = structured_llm.invoke(text)
    save_lead_to_csv(lead)
    save_lead_to_sqlite(lead)
    # save_lead_to_drive(lead)  # Temporarily commented out for circular import diagnosis
    return lead

# ✅ RAG setup
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN")
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")

from langchain_google_community import GoogleDriveLoader

def load_documents():
    print(f"[LEAD_GRAPH_INIT] Attempting to load documents. Effective Folder ID being used: {FOLDER_ID}")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    print(f"[LEAD_GRAPH_INIT] Using service account key from env var GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")

    if not creds_path:
        print("[LEAD_GRAPH_INIT] CRITICAL ERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        return []

    if not os.path.isfile(creds_path): # <--- ADD THIS CHECK
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR: Credentials file not found at path specified by GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
        return []
    else:
        print(f"[LEAD_GRAPH_INIT] Credentials file confirmed to exist at: {creds_path}") # <--- ADD THIS CONFIRMATION
    try:
        specific_doc_id = "14K4ZhA334LNGrCG5gYHLgcr3TWVu-Dpki1Kw4TI93EU" # New ID
        print(f"[LEAD_GRAPH_INIT] Attempting to load new specific document ID: {specific_doc_id}")

        loader = GoogleDriveLoader(
            service_account_key=creds_path,
            document_ids=[specific_doc_id]
        )
        print(f"[LEAD_GRAPH_INIT] GoogleDriveLoader initialized for specific PDF ID: {specific_doc_id}.")
        docs = loader.load()

        print(f"[LEAD_GRAPH_INIT] loader.load() completed. Number of documents loaded: {len(docs) if docs is not None else 'None'}")
        if not docs:
            print(f"[LEAD_GRAPH_INIT] No document loaded for specific PDF ID: '{specific_doc_id}'. Please ensure: \n1. The ID is absolutely correct. \n2. The file is a PDF. \n3. The service account ('{os.getenv('GDRIVE_SERVICE_ACCOUNT_EMAIL_FOR_LOGGING', 'render3@intricate-sweep-453002-p1.iam.gserviceaccount.com')}') has 'Viewer' permission DIRECTLY on this file. \n4. The file is not in the trash or in a restricted state preventing API access.")
        return docs
    except Exception as e:
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR loading specific document from Google Drive: {e}")
        # import traceback # Ensure traceback is imported -- it's at the top now
        print(f"[LEAD_GRAPH_INIT] Traceback: {traceback.format_exc()}")
        return [] # Return empty list on error


def setup_rag():
    docs = load_documents()
    print(f"[LEAD_GRAPH_INIT] setup_rag: docs loaded: {docs is not None}, number of docs: {len(docs) if docs else 0}")
    if not docs:
        print("[LEAD_GRAPH_INIT] setup_rag: No documents loaded, RAG chain cannot be setup.")
        return None

    embeddings = HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'}
    )
    print("[LEAD_GRAPH_INIT] setup_rag: Embeddings loaded.")

    # No need to pre-cache embeddings here if FAISS handles it or if it's too slow for init

    vectorstore = FAISS.from_documents(docs, embeddings)
    print("[LEAD_GRAPH_INIT] setup_rag: FAISS vector store created.")
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2, "score_threshold": 0.8})
    print("[LEAD_GRAPH_INIT] setup_rag: Retriever created.")

    prompt = ChatPromptTemplate.from_template("""
    ### Rôle ###
    Vous êtes un assistant virtuel expert de TRANSLAB INTERNATIONAL. Votre rôle est d'aider les utilisateurs en répondant à leurs questions sur les services de traduction et d'interprétation, et de collecter leurs informations (nom, email, téléphone) s'ils expriment un intérêt pour un devis ou plus d'informations. Soyez concis et direct.

    ### Contexte Documentaire (si disponible) ###
    {context}

    ### Historique de Conversation (si disponible) ###
    {history}

    ### Question de l'utilisateur ###
    {question}

    ### Instructions Additionnelles ###
    - Si la question ne semble pas nécessiter de contexte documentaire, répondez directement.
    - Si la question de l'utilisateur est une simple salutation ou une conversation légère, répondez de manière appropriée sans chercher de contexte.
    - Utilisez le contexte documentaire pour répondre aux questions spécifiques sur TRANSLAB INTERNATIONAL.
    - Ne mentionnez PAS le contexte documentaire ou l'historique dans votre réponse, utilisez-les discrètement.
    - Répondez en FRANÇAIS.
    """)
    print("[LEAD_GRAPH_INIT] setup_rag: Prompt template created.")

    rag_chain_local = (
        RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"],
            "history": lambda x: x.get("history", []) # Pass history
        }) | prompt | llm
    )
    print(f"[LEAD_GRAPH_INIT] setup_rag: Runnable RAG chain constructed. Returning chain. Is None: {rag_chain_local is None}")
    return rag_chain_local

# Global state for lazy initialization of RAG chain
_rag_chain_instance = None
_rag_chain_initialized = False
# from threading import Lock # Optional: Lock for thread-safety
# _rag_chain_lock = Lock()   # Optional: Lock for thread-safety

def get_rag_chain():
    global _rag_chain_instance, _rag_chain_initialized #, _rag_chain_lock # Optional
    # with _rag_chain_lock: # Optional: Lock for thread-safety
    if not _rag_chain_initialized:
        print("[LEAD_GRAPH_LAZY_INIT] First call to get_rag_chain. Initializing RAG chain now.")
        _rag_chain_instance = setup_rag() # setup_rag() should return the chain or None
        _rag_chain_initialized = True
        print(f"[LEAD_GRAPH_LAZY_INIT] RAG chain initialization attempt complete. Instance is None: {_rag_chain_instance is None}")
    return _rag_chain_instance

# Remove old: rag_chain = setup_rag()
# print(f"[LEAD_GRAPH_INIT] Global rag_chain initialized: {rag_chain is not None}") # This also needs to be removed or updated if we want to log at import time

if __name__ == "__main__":
    text = "Bonjour, je m'appelle Alice Martin. Vous pouvez me joindre à alice.martin@email.com ou au 06 12 34 56 78."
    lead = collect_lead_from_text(text)
    print("✅ Lead extrait :", lead)
