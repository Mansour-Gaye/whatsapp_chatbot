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
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.cache import SQLiteCache
import langchain
from langchain_core.runnables import RunnableMap
from langchain_community.cache import InMemoryCache
import re
from datetime import datetime 
from langchain_core.documents import Document
import json
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

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

# --- Gestion des images disponibles ---
IMAGE_DIR = os.path.join(os.path.dirname(__file__), 'static', 'public')

def get_available_images():
    """Scans the image directory and returns a list of filenames."""
    try:
        if not os.path.exists(IMAGE_DIR):
            logger.warning(f"Le répertoire d'images n'existe pas : {IMAGE_DIR}")
            return []
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        files = [f for f in os.listdir(IMAGE_DIR) if os.path.splitext(f)[1].lower() in image_extensions]
        return files
    except Exception as e:
        logger.error(f"Erreur lors du scan du répertoire d'images : {e}")
        return []

AVAILABLE_IMAGES = get_available_images()
logger.info(f"Images disponibles trouvées : {AVAILABLE_IMAGES}")
# --- Fin de la gestion des images ---

class Lead(BaseModel):
    name: Optional[str] = Field(None, description="Nom complet de l'utilisateur")
    email: Optional[str] = Field(None, description="Adresse e-mail valide de l'utilisateur")
    phone: Optional[str] = Field(None, description="Numéro de téléphone de l'utilisateur")

def save_lead(lead: Lead, visitor_id: str = None) -> bool:
    """Sauvegarde ou met à jour un lead dans Supabase en utilisant le visitor_id."""
    try:
        client = get_supabase_client()
        if not client:
            return False
            
        # Préparer les données en filtrant les valeurs non fournies
        data = {k: v for k, v in lead.model_dump().items() if v}

        # Ne rien faire si aucune donnée n'est fournie
        if not data:
            logger.warning("Tentative de sauvegarde d'un lead vide. Opération annulée.")
            return True # Retourner True pour ne pas bloquer le flux

        # Gérer le timestamp
        data["updated_at"] = datetime.utcnow().isoformat()

        if visitor_id:
            data["visitor_id"] = visitor_id
            # Upsert: met à jour si le visitor_id existe, sinon insère.
            # 'visitor_id' doit être une contrainte unique (clé primaire ou unique) dans la table Supabase.
            # La colonne 'on_conflict' doit être celle qui a la contrainte unique.
            logger.info(f"Tentative d'UPSERT pour le visiteur {visitor_id} avec les données : {data}")
            result = client.table('leads').upsert(data, on_conflict='visitor_id').execute()
            logger.info(f"Lead upserted avec succès pour le visiteur {visitor_id}")
        else:
            # Ancien comportement si aucun visitor_id n'est fourni
            data["created_at"] = data.get("updated_at")
            del data["updated_at"]
            logger.info(f"Tentative d'INSERT (sans visitor_id) avec les données : {data}")
            result = client.table('leads').insert(data).execute()
            logger.info(f"Lead inséré avec succès (sans visitor_id)")

        return True
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde du lead: {str(e)}")
        # Afficher le traceback pour un meilleur débogage
        logger.error(traceback.format_exc())
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

llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0, groq_api_key=os.getenv("GROQ_API_KEY"))
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

        # Diviser les documents en chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(documents)
        logger.info(f"Documents divisés en {len(splits)} chunks.")

        # Créer le vectorstore à partir des chunks
        vectorstore = FAISS.from_documents(splits, embeddings)
        logger.info("Vectorstore FAISS créé à partir des chunks.")
        
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
    "## Rôle\n"
    "Tu es l'assistant virtuel expert de TRANSLAB INTERNATIONAL, entreprise de services linguistiques basée à Dakar depuis 2009. Tu es hautement qualifié, créatif et doté d'un talent exceptionnel pour l'engagement client.\n\n"
    
    "## Instructions Principales\n"
    "1. **Réponds DIRECTEMENT** à la question posée - ne montre JAMAIS ton processus de réflexion\n"
    "2. **Adapte ta réponse** au contexte de la question :\n"
    "   - Salutation simple → Réponse courte et amicale SANS image\n"
    "   - Question sur nos services → Réponse détaillée AVEC image pertinente\n"
    "   - Question spécifique → Réponse ciblée sur le sujet demandé\n"
    "3. **Format image** : Commence par `[image: nom_exact.ext]` si nécessaire\n"
    "4. **Utilise UNIQUEMENT** les noms d'images de la liste fournie\n"
    "5. **Ton professionnel** avec emojis et formatage Markdown\n\n"
    
    "## Informations Clés TRANSLAB\n"
    "- **Fondée en 2009** à Dakar, Sénégal\n"
    "- **Équipe experte** : Demba Diallo, Irahima Ndao, Alfred Diop (15+ ans d'expérience)\n"
    "- **Services** : Interprétation (simultanée, consécutive, liaison, à distance) + Traduction certifiée\n"
    "- **Secteurs** : Juridique, Médical, Financier, Institutionnel, ONG\n"
    "- **Zone** : Sénégal, Afrique de l'Ouest + mondial à distance\n"
    "- **Contact** : +221 77 509 04 01 | WhatsApp: +221 78 148 10 10 | contact@translab-international.com\n"
    "- **Standards** : Équipements ISO 2603, confidentialité NDA, réactivité 24/7\n\n"
    
    "## Contexte de la conversation\n"
    "{context}\n\n"
    "## Images disponibles\n"
    "{available_images}\n\n"
    "## Historique\n"
    "{history}\n\n"
    "## Question utilisateur\n"
    "{question}\n\n"
    
    "## Exemples de réponses\n"
    "**Salutation :** \"Bonjour ! 👋 Ravi de vous accueillir chez TRANSLAB INTERNATIONAL. Comment puis-je vous aider ?\"\n\n"
    
    "**Services généraux :**\n"
    "```\n"
    "[image: services.jpg]\n"
    "Nos services linguistiques depuis 2009 :\n"
    "🗣️ **INTERPRÉTATION** (simultanée, consécutive, liaison, à distance)\n"
    "📄 **TRADUCTION** certifiée (juridique, médicale, technique)\n"
    "🌍 **Secteurs** : Juridique, Médical, Financier, ONG\n"
    "```\n\n"
    
    "**Question spécifique localisation :**\n"
    "```\n"
    "[image: localisation.jpg]\n"
    "Notre service de **localisation culturelle** :\n"
    "✅ Adaptation de vos contenus pour l'Afrique de l'Ouest\n"
    "✅ Prise en compte des nuances culturelles locales\n"
    "✅ Expertise des codes socio-culturels sénégalais\n"
    "Parfait pour vos documents marketing, sites web, communications institutionnelles !\n"
    "```\n\n"
    
    "## RÈGLES CRITIQUES\n"
    "- ❌ **JAMAIS** d'analyse visible de ta réflexion\n"
    "- ❌ **JAMAIS** de demande d'informations personnelles non sollicitée\n"
    "- ❌ **JAMAIS** de réponse générique identique\n"
    "- ✅ **TOUJOURS** répondre spécifiquement à la question\n"
    "- ✅ **TOUJOURS** utiliser l'historique pour éviter les répétitions\n"
    "- ✅ **TOUJOURS** commencer par l'image si nécessaire : `[image: nom.ext]`\n"
)

        logger.info("Template de prompt créé")

        # Créer la chaîne RAG
        rag_chain = RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"],
            "history": lambda x: x.get("history", []),
            "available_images": lambda x: ", ".join(AVAILABLE_IMAGES) if AVAILABLE_IMAGES else "Aucune"
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



















































































































