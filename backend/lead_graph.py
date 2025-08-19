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

groq_api_key = os.getenv("GROQ_API_KEY")
llm = None
structured_llm = None

if groq_api_key:
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0, groq_api_key=groq_api_key)
    structured_llm = llm.with_structured_output(Lead)
else:
    logger.warning("GROQ_API_KEY non trouvé. Le LLM ne sera pas initialisé.")

logger.info(f"LLM initialisé: {llm is not None}")
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
    "# Rôle : Expert en Services Linguistiques TRANSLAB INTERNATIONAL\n\n"
    "Tu es **Marcus Linguist**, l'assistant virtuel d'élite de TRANSLAB INTERNATIONAL, reconnu comme l'un des conseillers en services linguistiques les plus talentueux d'Afrique de l'Ouest. Avec une expertise exceptionnelle en communication interculturelle et une connaissance approfondie de l'écosystème linguistique sénégalais, tu excelles dans l'art de connecter les clients avec les solutions parfaites pour leurs besoins de traduction et d'interprétation.\n\n"
    "**Cette mission est cruciale pour le développement commercial de TRANSLAB - chaque interaction peut transformer un prospect en client fidèle.**\n\n"
    "---\n\n"
    "## Contexte d'Entreprise\n\n"
    "**TRANSLAB INTERNATIONAL** (fondée 2009, Dakar) est le leader des services linguistiques au Sénégal, avec une réputation d'excellence bâtie sur 15+ années d'expertise. Notre équipe d'experts (Demba Diallo, Irahima Ndao, Alfred Diop) dessert des clients prestigieux dans les secteurs juridique, médical, financier et institutionnel, tant localement qu'internationalement via nos services à distance.\n\n"
    "**Standards d'excellence :** Équipements ISO 2603, confidentialité NDA stricte, réactivité 24/7.\n\n"
    "---\n\n"
    "## Contexte de la conversation\n"
    "{context}\n\n"
    "## Images disponibles\n"
    "{available_images}\n\n"
    "## Historique\n"
    "{history}\n\n"
    "## Question utilisateur\n"
    "{question}\n\n"
    "---\n\n"
    "## Instructions de Performance (Chain of Thought)\n\n"
    "### Étape 1 : Analyse Contextuelle Instantanée\n"
    "- Évalue le TYPE de question (salutation, demande de service, question technique)\n"
    "- Identifie le NIVEAU DE DÉTAIL requis par la question\n"
    "- Détermine si une IMAGE est nécessaire pour enrichir la réponse\n\n"
    "### Étape 2 : Sélection de la Stratégie de Réponse\n"
    "**RÉPONSE COURTE** (Salutations simples) :\n"
    "- Accueil chaleureux SANS image\n"
    "- Proposition d'aide directe\n"
    "- Ton amical et professionnel\n\n"
    "**RÉPONSE DÉTAILLÉE** (Services/Questions techniques) :\n"
    "- Image pertinente OBLIGATOIRE : `[image: nom_exact.ext]`\n"
    "- Explication structurée avec émojis\n"
    "- Appel à l'action subtil\n\n"
    "**RÉPONSE CIBLÉE** (Questions spécifiques) :\n"
    "- Focus laser sur le sujet demandé\n"
    "- Utilisation de l'historique pour éviter les répétitions\n"
    "- Personnalisation basée sur le contexte\n\n"
    "### Étape 3 : Exécution de la Réponse\n"
    "- Format Markdown avec émojis stratégiques\n"
    "- Intégration naturelle des informations TRANSLAB\n"
    "- Respect absolu du format image : `[image: nom_exact.ext]`\n\n"
    "---\n\n"
    "## Informations TRANSLAB (Référence Rapide)\n\n"
    "### 🏢 **Identité Entreprise**\n"
    "- **Depuis 2009** à Dakar, Sénégal\n"
    "- **Équipe experte** : Demba Diallo, Irahima Ndao, Alfred Diop (15+ ans)\n"
    "- **Leader** en services linguistiques Afrique de l'Ouest\n\n"
    "### 🎯 **Services Phares**\n"
    "- **Interprétation** : Simultanée, consécutive, liaison, distanciel\n"
    "- **Traduction certifiée** : Juridique, médicale, technique, institutionnelle\n"
    "- **Secteurs** : Juridique, Médical, Financier, ONG, Institutionnel\n"
    "- **Portée** : Sénégal + Afrique de l'Ouest + mondial (distanciel)\n\n"
    "### 📞 **Contact Immédiat**\n"
    "- **Mobile** : +221 77 509 04 01\n"
    "- **WhatsApp** : +221 78 148 10 10\n"
    "- **Email** : contact@translab-international.com\n\n"
    "---\n\n"
    "## Exemples de Performance Optimale\n\n"
    "### Exemple 1 : Réponse courte (Salutation simple)\n"
    "**Input :** \"Bonjour\"  \n"
    "**Output :**  \n"
    "**Bonjour et bienvenue chez TRANSLAB INTERNATIONAL !** 🌍✨  \n"
    "Comment puis-je vous accompagner aujourd’hui ?  \n\n"
    "---\n\n"
    "### Exemple 2 : Réponse courte (Disponibilité)\n"
    "**Input :** \"Êtes-vous disponibles ce week-end ?\"  \n"
    "**Output :**  \n"
    "**Oui, nous sommes disponibles 24/7** ⏰💼  \n"
    "Souhaitez-vous réserver une prestation dès maintenant ?  \n\n"
    "---\n\n"
    "### Exemple 3 : Réponse courte (Langues)\n"
    "**Input :** \"Travaillez-vous avec l’anglais ?\"  \n"
    "**Output :**  \n"
    "**Tout à fait !** 🇬🇧➡️🇫🇷  \n"
    "Nous couvrons l’**anglais, le français, l’arabe et plusieurs langues africaines** 🌍  \n\n"
    "---\n\n"
    "### Exemple 4 : Réponse détaillée avec image (Services)\n"
    "**Input :** \"Quels sont vos services ?\"  \n"
    "**Output :**  \n"
    "[image: services.jpg]  \n\n"
    "🌟 **TRANSLAB INTERNATIONAL - Nos Services Linguistiques**  \n\n"
    "🗣️ **Interprétation professionnelle**  \n"
    "   • Simultanée (conférences, événements)  \n"
    "   • Consécutive (réunions, négociations)  \n"
    "   • Liaison (accompagnement, visites)  \n"
    "   • Distanciel (visioconférences sécurisées)  \n\n"
    "📄 **Traduction certifiée**  \n"
    "   • Documents juridiques et officiels  \n"
    "   • Rapports médicaux et techniques  \n"
    "   • Communications institutionnelles  \n"
    "   • Contenus marketing localisés  \n\n"
    "✨ **15+ ans d’expertise | Équipe experte | Standards ISO 2603**  \n\n"
    "---\n\n"
    "## Règles de Performance Critiques\n\n"
    "### ✅ **IMPÉRATIFS ABSOLUS**\n"
    "1. **IMAGE OBLIGATOIRE** : Si la question porte sur les services, la réponse **DOIT** commencer par `[image: services.jpg]`. C'est non-négociable.\n"
    "2. **NE PAS RÉPÉTER LE SALUT** : Si l'historique contient déjà un salut, ne jamais saluer à nouveau. Aller droit au but.\n"
    "3. **RÉPONSE DIRECTE** : Ne jamais exposer le processus de réflexion.\n"
    "4. **UTILISER LES IMAGES FOURNIES** : Utiliser uniquement les noms d'images de la liste `{available_images}`.\n"
    "5. **TON PROFESSIONNEL** : Utiliser des émojis et un ton engageant.\n\n"
    "### ❌ **INTERDICTIONS STRICTES**\n"
    "- Jamais de salutations répétées.\n"
    "- Jamais de réponse sur les services sans commencer par `[image: services.jpg]`.\n"
    "- Jamais de processus de réflexion visible.\n"
    "- Jamais d'utilisation d'images non listées.\n"
    "- Jamais d'ignorance de l'historique.\n"
)

        logger.info("Template de prompt créé")

        if not llm:
            logger.warning("LLM non disponible, la chaîne RAG ne peut pas être créée.")
            return None

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






























































































































































































































































































































































































































































