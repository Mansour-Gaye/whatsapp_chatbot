from typing import List, Dict, Any, Optional
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
import os
import traceback 
from googleapiclient.http import MediaIoBaseUpload 
import io
from gdrive_utils import get_drive_service, DriveLoader
from langchain_community.vectorstores import FAISS
from jina_embeddings import JinaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.cache import SQLiteCache
import langchain
from langchain_core.runnables import RunnableMap
from langchain_community.cache import InMemoryCache
from datetime import datetime 
from langchain_core.documents import Document
import json
import logging
from supabase import create_client, Client

# Configuration du logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configuration du cache Langchain
langchain.llm_cache = SQLiteCache(database_path=os.path.join(os.path.dirname(__file__), ".langchain.db"))
embedding_cache = {}

def get_supabase_client() -> Optional[Client]:
    """Crée un client Supabase."""
    try:
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            logger.error("SUPABASE_URL ou SUPABASE_KEY non configurés")
            return None
            
        client = create_client(supabase_url, supabase_key)
        logger.info("Client Supabase créé avec succès")
        return client
    except Exception as e:
        logger.error(f"Erreur lors de la création du client Supabase: {str(e)}")
        return None

def init_supabase():
    """Initialise la table leads dans Supabase."""
    try:
        client = get_supabase_client()
        if not client:
            return False
            
        # La table sera créée automatiquement par Supabase
        logger.info("Supabase initialisé avec succès")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de Supabase: {str(e)}")
        return False

# Initialiser Supabase au démarrage
init_supabase()

class Lead(BaseModel):
    name: str = Field(description="Nom complet de l'utilisateur")
    email: str = Field(description="Adresse e-mail valide de l'utilisateur")
    phone: str = Field(description="Numéro de téléphone de l'utilisateur")

def save_lead(lead: Lead) -> bool:
    """Sauvegarde un lead dans Supabase."""
    try:
        client = get_supabase_client()
        if not client:
            return False
            
        data = {
            "name": lead.name,
            "email": lead.email,
            "phone": lead.phone,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = client.table('leads').insert(data).execute()
        logger.info(f"Lead sauvegardé avec succès: {lead.model_dump()}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde du lead: {str(e)}")
        return False

def collect_lead_from_text(text: str) -> Lead:
    if structured_llm is None:
        logger.error("structured_llm is None. Cannot extract lead.")
        return Lead(name="Error: LLM N/A", email="Error: LLM N/A", phone="Error: LLM N/A") 
    lead_data = structured_llm.invoke(text)
    if save_lead(lead_data):
        logger.info("Lead sauvegardé avec succès dans Supabase")
    else:
        logger.error("Échec de la sauvegarde du lead dans Supabase")
    return lead_data

# Garder les fonctions save_lead_to_csv et save_lead_to_sqlite pour la compatibilité
def save_lead_to_csv(lead: Lead, filename=None):
    """Fonction de compatibilité qui utilise save_lead."""
    return save_lead(lead)

def save_lead_to_sqlite(lead: Lead, db_path=None):
    """Fonction de compatibilité qui utilise save_lead."""
    return save_lead(lead)

llm = ChatGroq(model="llama3-8b-8192", temperature=0, groq_api_key=os.getenv("GROQ_API_KEY") or "...")
logger.info(f"LLM initialisé: {llm is not None}")

structured_llm = llm.with_structured_output(Lead) if llm else None
logger.info(f"structured_llm initialisé: {structured_llm is not None}")

def load_documents():
    """Charge les documents depuis Google Drive."""
    logger.info("Tentative de chargement des documents depuis Google Drive")
    
    try:
        # Utiliser DriveLoader
        loader = DriveLoader()
        documents = loader.load()
        
        if not documents:
            logger.warning("Aucun document trouvé dans Google Drive")
            return []
            
        logger.info(f"Documents chargés avec succès depuis Google Drive ({len(documents)} documents)")
        return documents
        
    except Exception as e:
        logger.error(f"Erreur lors du chargement des documents: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def setup_rag():
    """Initialise la chaîne RAG avec les documents de Google Drive."""
    try:
        # Initialiser le loader Google Drive
        loader = DriveLoader()
        
        # Charger les documents
        documents = loader.load()
        
        if not documents:
            logger.warning("Aucun document trouvé dans Google Drive")
            return None
            
        # Utiliser Jina Embeddings
        embeddings = JinaEmbeddings()
        logger.info("Jina Embeddings chargés")
        
        # Créer le vectorstore
        vectorstore = FAISS.from_documents(documents, embeddings)
        logger.info("Vectorstore FAISS créé")
        
        # Créer le retriever
        retriever = vectorstore.as_retriever(
            search_kwargs={
                "k": 1 if len(documents) == 1 else 2,
                "score_threshold": 0.8
            }
        )
        logger.info("Retriever créé")

        # Créer le prompt template
        prompt = ChatPromptTemplate.from_template(
            "### Rôle ###\nVous êtes un assistant virtuel expert de TRANSLAB INTERNATIONAL..."
            "\n### Contexte Documentaire (si disponible) ###\n{context}"
            "\n### Historique de Conversation (si disponible) ###\n{history}"
            "\n### Question de l'utilisateur ###\n{question}"
            "\n### Instructions Additionnelles ###\n- Si la question ne semble pas nécessiter de contexte documentaire, répondez directement."
            "\n- Si la question de l'utilisateur est une simple salutation ou une conversation légère, répondez de manière appropriée sans chercher de contexte."
            "\n- Utilisez le contexte documentaire pour répondre aux questions spécifiques sur TRANSLAB INTERNATIONAL."
            "\n- Ne mentionnez PAS le contexte documentaire ou l'historique dans votre réponse, utilisez-les discrètement."
            "\n- Répondez en FRANÇAIS."
        )
        logger.info("Template de prompt créé")

        # Créer la chaîne RAG
        rag_chain = RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"],
            "history": lambda x: x.get("history", [])
        }) | prompt | llm
        
        logger.info("Chaîne RAG créée avec succès")
        return rag_chain
        
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la chaîne RAG: {str(e)}")
        return None

# Initialisation du RAG au démarrage
logger.info("Initialisation de la chaîne RAG...")
_rag_chain_instance = setup_rag()
logger.info(f"Chaîne RAG initialisée: {_rag_chain_instance is not None}")

def get_rag_chain():
    """Retourne l'instance du RAG chain."""
    return _rag_chain_instance

if __name__ == "__main__":
    print("Testing lead_graph.py locally...")
    if not os.getenv("GROQ_API_KEY"): print("Warning: GROQ_API_KEY not set.")
    
    print("\n--- RAG Chain Test ---")
    test_rag_chain = get_rag_chain()
    if test_rag_chain:
        print("RAG chain obtained via get_rag_chain().")
        try:
            response = test_rag_chain.invoke({"question": "Quels sont vos services ?"})
            print(f"Test RAG Response: '{response.content if hasattr(response, 'content') else response}'")
        except Exception as e: print(f"Error invoking test RAG chain: '{e}'")
    else: print("RAG chain is None after get_rag_chain(). Skipping RAG test.")
    
    print("\n--- Lead Extraction Test ---")
    text = "Bonjour, je suis Jean Dupont. Mon email est jean.dupont@example.com et mon tel est 0123456789."
    try:
        if structured_llm:
            collected_lead = collect_lead_from_text(text) 
            print(f"Extracted Lead: '{collected_lead}'")
        else:
            print("structured_llm is None, skipping lead extraction test.")
    except Exception as e: print(f"Error collecting lead: '{e}'")








