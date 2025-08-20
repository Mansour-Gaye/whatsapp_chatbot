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
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
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

def create_rag_chain(image_families: Dict[str, List[str]] = None):
    """Crée la chaîne RAG avec les documents de Google Drive et les familles d'images."""
    if image_families is None:
        image_families = {}

    try:
        loader = DriveLoader()
        documents = loader.load()
        if not documents:
            logger.warning("Aucun document trouvé dans Google Drive")
            return None
            
        embeddings = JinaEmbeddings()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(documents)
        vectorstore = FAISS.from_documents(splits, embeddings)
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": 1 if len(documents) == 1 else 2, "score_threshold": 0.8}
        )

        # Nous passons les familles de carrousels au prompt.
        available_carousels_str = ", ".join(image_families.keys()) if image_families else "Aucun"

        system_prompt = f"""# Rôle et Objectif
Tu es un assistant virtuel expert pour **Translab International**, une entreprise leader en traduction, interprétation et localisation basée à Dakar. Ton but est de répondre aux questions des utilisateurs de manière professionnelle, chaleureuse, et extrêmement concise, tout en utilisant les outils à ta disposition pour enrichir l'interaction.

### Outils Spéciaux
Tu peux intégrer des images ou des carrousels d'images dans tes réponses en utilisant des balises spécifiques.

1.  **Image simple `[image: ...]`**:
    *   **Quand l'utiliser** : Pour illustrer un point précis ou après plusieurs échanges textuels pour dynamiser la conversation.
    *   **Images disponibles** : `{", ".join(AVAILABLE_IMAGES) if AVAILABLE_IMAGES else "Aucune"}`
    *   **Format** : `[image: nom_du_fichier.jpeg]`

2.  **Carrousel d'images `[carousel: ...]`**:
    *   **Quand l'utiliser** : Exclusivement lorsque l'utilisateur demande à voir des exemples concrets de matériel, d'installations ou de réalisations (ex: "montrez-moi vos cabines", "je veux voir des photos de vos interprètes", "quels sont vos équipements ?").
    *   **Carrousels disponibles** : `{available_carousels_str}`
    *   **Format** : `[carousel: nom_de_la_famille]`
    *   **Exemple de conversation** :
        *   Utilisateur: "Avez-vous des photos de vos cabines d'interprétation ?"
        *   Ta réponse: "Absolument ! Voici un aperçu de nos cabines professionnelles. [carousel: interpretation-cabine]"

### Instructions de Communication
- **Concisión Maximale**: Tes réponses doivent faire 1 à 3 phrases dans 80% des cas. Sois direct et va à l'essentiel.
- **Services et Devis**: Si on te questionne sur les services, réponds clairement. Pour toute demande de devis, de prix ou de tarif, redirige systématiquement vers **contact@translab-international.com**.
- **Ton**: Adopte un ton professionnel mais chaleureux. Utilise des emojis (🙂, 🌍, 📞) avec parcimonie et pertinence.
- **Fiabilité**: Base TOUTES tes réponses sur le **Contexte** fourni. Ne fournis jamais d'informations qui ne proviennent pas de ce contexte.

---
**Contexte de la conversation (source de vérité)**:
{{context}}
---
"""

        # Mettre à jour le prompt template pour utiliser le nouveau system_prompt formaté
        # et retirer les variables qui sont maintenant directement dans le f-string.
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt.format(
                available_images=", ".join(AVAILABLE_IMAGES) if AVAILABLE_IMAGES else "Aucune",
                available_carousels_str=available_carousels_str
            )),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])
        logger.info("Template de prompt créé")


        if not llm:
            logger.warning("LLM non disponible, la chaîne RAG ne peut pas être créée.")
            return None

        # La chaîne n'a plus besoin de peupler `available_images` ou `available_carousels`
        # car ils sont maintenant intégrés dans le system prompt au moment de la création.
        rag_chain = RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"],
            "history": lambda x: x.get("history", []),
        }) | prompt | llm
        
        logger.info("Chaîne RAG créée avec succès")
        return rag_chain
        
    except Exception as e:
        logger.error(f"Erreur lors de la création de la chaîne RAG: {str(e)}")
        # Afficher le traceback pour un meilleur débogage en développement
        logger.error(traceback.format_exc())
        return None

if __name__ == "__main__":
    print("Testing lead_graph.py locally...")
    from langchain_core.messages import AIMessage, HumanMessage
    if not os.getenv("GROQ_API_KEY"): print("Warning: GROQ_API_KEY not set.")

    print("\n--- RAG Chain Test ---")
    test_rag_chain = get_rag_chain()
    if test_rag_chain:
        print("RAG chain obtained via get_rag_chain().")
        try:
            # Test 1: First question
            print("\n--- Test 1: First Question ---")
            response1 = test_rag_chain.invoke({
                "question": "Quels sont vos services ?",
                "history": []
            })
            print(f"Test RAG Response 1: '{response1.content}'")

            # Test 2: Follow-up question
            print("\n--- Test 2: Follow-up Question ---")
            response2 = test_rag_chain.invoke({
                "question": "Et pour la traduction ?",
                "history": [
                    HumanMessage(content="Quels sont vos services ?"),
                    AIMessage(content=response1.content)
                ]
            })
            print(f"Test RAG Response 2: '{response2.content}'")

        except Exception as e:
            print(f"Error invoking test RAG chain: '{e}'")
            # Print traceback for more details
            import traceback
            traceback.print_exc()
    else:
        print("RAG chain is None after get_rag_chain(). Skipping RAG test.")

    print("\n--- Lead Extraction Test ---")
    text = "Bonjour, je suis Jean Dupont. Mon email est jean.dupont@example.com et mon tel est 0123456789."
    try:
        if structured_llm:
            collected_lead = collect_lead_from_text(text)
            print(f"Extracted Lead: '{collected_lead}'")
        else:
            print("structured_llm is None, skipping lead extraction test.")
    except Exception as e:
        print(f"Error collecting lead: '{e}'")

































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































