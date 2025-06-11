from typing import Annotated, List
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
import csv
import os
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_google_community import GoogleDriveLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.cache import SQLiteCache
import langchain
from langchain_core.runnables import RunnableMap
from langchain_community.cache import InMemoryCache

# Configuration du cache
langchain.llm_cache = SQLiteCache(database_path=".langchain.db")
memory_cache = InMemoryCache()

# Initialisation du cache pour les embeddings
embedding_cache = {}

def get_cached_embeddings(text: str, embeddings: HuggingFaceEmbeddings) -> List[float]:
    """Récupère les embeddings avec cache."""
    cache_key = f"embed_{hash(text)}"
    if cache_key in embedding_cache:
        return embedding_cache[cache_key]
    embedding = embeddings.embed_query(text)
    embedding_cache[cache_key] = embedding
    return embedding

# Définir la structure du lead
class Lead(BaseModel):
    name: str = Field(description="Nom complet de l'utilisateur")
    email: str = Field(description="Adresse e-mail valide de l'utilisateur")
    phone: str = Field(description="Numéro de téléphone de l'utilisateur")

# Définir l'état du graphe (contexte conversationnel)
class State(Annotated[dict, add_messages]):
    messages: list
    thread_id: str

# Initialiser le modèle Groq
llm = ChatGroq(
    model="llama3-8b-8192",
    temperature=0,
    groq_api_key="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"
)

# Extraction structurée avec la méthode moderne
structured_llm = llm.with_structured_output(Lead)

def save_lead_to_csv(lead: Lead, filename=None):
    if filename is None:
        filename = os.path.join(os.path.dirname(__file__), "leads.csv")
    file_exists = os.path.isfile(filename)
    with open(filename, mode="a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["name", "email", "phone"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({"name": lead.name, "email": lead.email, "phone": lead.phone})

def save_lead_to_sqlite(lead: Lead, db_path="leads.db"):
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

def collect_lead(state: State):
    user_message = state["messages"][-1]["content"]
    lead = structured_llm.invoke(user_message)
    save_lead_to_csv(lead)
    save_lead_to_sqlite(lead)
    return {
        "messages": state["messages"] + [{"role": "system", "content": str(lead)}],
        "lead": lead.model_dump(),
        "thread_id": state["thread_id"]
    }

# Création du graphe
graph = StateGraph(State)
graph.add_node("collect_lead", collect_lead)
graph.set_entry_point("collect_lead")
graph.add_edge("collect_lead", END)

# ✅ Utilise le context manager pour SqliteSaver correctement
from langgraph.checkpoint.sqlite import SqliteSaver

FOLDER_ID = "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN"  # Remplace par ton ID Google Drive
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")  # Ton fichier d'identifiants Google

# Ajout d'un log pour vérifier la présence du fichier credentials.json
if os.path.isfile(TOKEN_PATH):
    print(f"✅ [AUTH] Fichier d'identifiants trouvé : {TOKEN_PATH}")
else:
    print(f"❌ [AUTH] Fichier d'identifiants NON trouvé : {TOKEN_PATH}")

def load_documents():
    print("⏳ [RAG] Démarrage du chargement des documents Google Drive...")
    print(f"📁 [RAG] Tentative d'accès au dossier : {FOLDER_ID}")
    try:
        loader = GoogleDriveLoader(
            folder_id=FOLDER_ID,
            token_path=TOKEN_PATH,
            file_types=["document", "pdf", "sheet"],
            recursive=True
        )
        print("🔑 [RAG] Configuration du loader réussie")
        docs = loader.load()
        print(f"✅ [RAG] {len(docs)} document(s) chargé(s) depuis Google Drive.")
        if len(docs) == 0:
            print("⚠️ [RAG] Aucun document trouvé dans le dossier spécifié. Vérifiez :")
            print("   - Le FOLDER_ID est correct")
            print("   - Le dossier contient des documents")
            print("   - Les permissions sont correctes")
        return docs
    except Exception as e:
        print(f"❌ [RAG] Erreur lors du chargement Google Drive : {e}")
        print("🔍 [RAG] Détails de l'erreur :")
        print(f"   - Token path : {TOKEN_PATH}")
        print(f"   - Folder ID : {FOLDER_ID}")
        return []

def setup_rag():
    docs = load_documents()
    if not docs:
        print("❌ [RAG] Aucun document chargé, le système RAG ne sera pas initialisé.")
        return None

    # Initialisation des embeddings
    embeddings = HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'}
    )
    
    # Préchargement des embeddings pour les documents
    print("⏳ [RAG] Préchargement des embeddings...")
    for doc in docs:
        get_cached_embeddings(doc.page_content[:1000], embeddings)
    
    print("✅ [RAG] Préchargement terminé")

    vectorstore = FAISS.from_documents(docs, embeddings)
    retriever = vectorstore.as_retriever(
        search_kwargs={
            "k": 2,
            "score_threshold": 0.8
        }
    )

    template = """
    ### Rôle ###
    Vous êtes un assistant virtuel expert de TRANSLAB INTERNATIONAL. Répondez aux questions de manière professionnelle, naturelle et engageante.

    ### Directives ###
    1. Ton : Professionnel mais chaleureux (éviter le jargon technique inutile)
    2. Style : 
       - Phrases courtes et claires
       - Émojis pertinents pour aérer le texte (🎯, ✅, 🌍)
       - Puces pour les listes (•, →)
       - Sauts de ligne entre les idées
    3. Contenu :
       - Réponse précise basée UNIQUEMENT sur le contexte fourni
       - Si information manquante : "Je ne trouve pas cette information précise dans nos documents. Vous pouvez nous contacter directement au..."
       - Proposer systématiquement une action (contact, devis...)

    ### Contexte ###
    {context}

    ### Question ###
    {question}

    ### Exemple de réponse idéale ###
    "TRANSLAB propose l'interprétation simultanée avec des experts certifiés 🌍
    • Couverture multilingue pour événements internationaux
    • Équipement technique fourni si besoin
    → Demandez un devis personnalisé via notre formulaire en ligne."
    """
    prompt = ChatPromptTemplate.from_template(template)

    # Pipeline RAG : injecte automatiquement le contexte
    rag_chain = (
        RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"]
        })
        | prompt
        | llm
    )
    return rag_chain

rag_chain = setup_rag()

if __name__ == "__main__":
    initial_state = {
        "messages": [{
            "role": "user",
            "content": "Bonjour, je m'appelle Alice Martin. Vous pouvez me joindre à alice.martin@email.com ou au 06 12 34 56 78."
        }],
        "thread_id": "test-thread-001"
    }

    # ⛏️ Important : compiler le graphe à l'intérieur du bloc `with`
    with SqliteSaver.from_conn_string("leads.sqlite") as saver:
        runnable = graph.compile(checkpointer=saver, debug=True)
        result = runnable.invoke(initial_state, config={"configurable": {"thread_id": initial_state["thread_id"]}})
        
        # ...après l'appel à invoke
        if hasattr(result, "items"):
            state_values = dict(result.items())
        else:
            state_values = result

        last_message = state_values["messages"][-1]["content"]
        print("Lead structuré extrait :", last_message)

        lead_data = state_values.get("lead")
        if lead_data:
            lead = Lead(**lead_data)
            save_lead_to_csv(lead)
            save_lead_to_sqlite(lead)
