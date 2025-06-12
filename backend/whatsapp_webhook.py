import os
import json
import requests
from flask import Blueprint, request, jsonify
from dotenv import load_dotenv
import traceback

# Attempt to import components from lead_graph
try:
    from lead_graph import Lead, structured_llm, rag_chain, llm as base_llm_from_graph
    from lead_graph import save_lead_to_csv, save_lead_to_sqlite
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = True
    print("[WHATSAPP_WEBHOOK_INIT] Successfully imported components from lead_graph.")
except ImportError as e:
    print(f"[WHATSAPP_WEBHOOK_INIT] CRITICAL_IMPORT_ERROR: Failed to import from lead_graph: '{e}'. Fallback mode will be active.") # Corrected f-string
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = False
    Lead, structured_llm, rag_chain, base_llm_from_graph = None, None, None, None
    save_lead_to_csv, save_lead_to_sqlite = None, None

load_dotenv()
whatsapp = Blueprint('whatsapp', __name__)

WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_PHONE_ID = os.getenv('WHATSAPP_PHONE_ID')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
user_states = {}

print(f"[CONFIG] WhatsApp Phone ID: '{WHATSAPP_PHONE_ID}'") # Corrected f-string
print(f"[CONFIG] Verify Token: '{VERIFY_TOKEN}'") # Corrected f-string
print(f"[CONFIG] WhatsApp Token: {'✅ Présent' if WHATSAPP_TOKEN else '❌ Manquant'}")

def get_user_state(phone_number: str) -> dict:
    if phone_number not in user_states:
        user_states[phone_number] = {
            "step": 0, "exchange_count": 0, "history": [],
            "lead": {"name": "", "email": "", "phone": phone_number}
        }
    return user_states[phone_number]

def process_message(message_body: str, phone_number: str) -> str:
    state = get_user_state(phone_number)
    history = state["history"]
    history.append({"role": "user", "content": message_body})
    response_text = "Je rencontre un problème technique. Veuillez réessayer plus tard." # Default

    if not LEAD_GRAPH_IMPORTED_SUCCESSFULLY:
        print("[PROCESS_MESSAGE] Critical: lead_graph components not imported.")
        history.append({"role": "assistant", "content": response_text})
        return response_text

    current_step = state["step"]

    if current_step == 0:
        state["exchange_count"] += 1
        print(f"[PROCESS_MESSAGE] Step 0, exchange_count: {state['exchange_count']}")
        if rag_chain is None:
            print("[PROCESS_MESSAGE] rag_chain is None (step 0). Using fallback LLM.")
            if base_llm_from_graph:
                try:
                    response_text = base_llm_from_graph.invoke(f"Répondez de manière utile à la question suivante: {message_body}").content
                except Exception as e:
                    print(f"[PROCESS_MESSAGE] Error fallback LLM (step 0): '{e}'") # Corrected f-string
                    response_text = "Je ne peux pas utiliser ma base de connaissances, mais comment puis-je aider ?"
            else:
                print("[PROCESS_MESSAGE] base_llm_from_graph is None (step 0).")
                response_text = "Mes outils de réponse avancés sont indisponibles. Question générale ?"
        else:
            try:
                print("[PROCESS_MESSAGE] rag_chain found (step 0). Attempting RAG invoke.")
                response_obj = rag_chain.invoke({"history": history, "question": message_body, "company_name": "TRANSLAB INTERNATIONAL", "company_specialty": "Interprétation et Traduction"})
                response_text = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error RAG chain (step 0): '{e}'") # Corrected f-string
                response_text = "Souci avec ma base de données. Reformulez svp."

        if state["exchange_count"] >= 2:
            print("[PROCESS_MESSAGE] Transitioning to step 1 (lead collection).")
            state["step"] = 1
            current_response_str = str(response_text)
            current_response_str += "\n\nPour mieux vous servir, quels sont vos nom, email et téléphone ?"
            response_text = current_response_str

    elif current_step == 1:
        print("[PROCESS_MESSAGE] Step 1: Lead Collection")
        lead_data = state["lead"]
        if structured_llm is None:
            print("[PROCESS_MESSAGE] structured_llm is None (step 1).")
            response_text = "Souci avec le traitement d'infos. Réessayez plus tard."
        else:
            try:
                print("[PROCESS_MESSAGE] structured_llm found (step 1). Attempting invoke.")
                lead_infos = structured_llm.invoke(message_body)
                if lead_infos.name: lead_data["name"] = lead_infos.name
                if lead_infos.email: lead_data["email"] = lead_infos.email
                if lead_infos.phone: lead_data["phone"] = lead_infos.phone
                missing = [f_item for f_item in ["name", "email", "phone"] if not lead_data.get(f_item)] # Renamed loop var
                if missing:
                    response_text = f"Merci ! Il manque: {', '.join(missing)}."
                else:
                    if Lead and callable(save_lead_to_csv) and callable(save_lead_to_sqlite):
                        current_lead = Lead(**lead_data)
                        save_lead_to_csv(current_lead)
                        save_lead_to_sqlite(current_lead)
                        print(f'[PROCESS_MESSAGE] Lead collected: "{lead_data}"')
                        state["step"] = 2
                        response_text = "Merci, infos enregistrées ! D'autres questions ?"
                    else:
                        print("[PROCESS_MESSAGE] Lead class/saving functions unavailable.")
                        response_text = "Merci pour les infos. Comment aider ensuite ?"
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error lead processing (step 1): '{e}'\n{traceback.format_exc()}") # Corrected f-string
                response_text = "Problème d'enregistrement des infos."

    else: # current_step >= 2
        print(f"[PROCESS_MESSAGE] Step {current_step}: General post-lead chat")
        if rag_chain is None:
            print(f"[PROCESS_MESSAGE] rag_chain is None (step {current_step}). Fallback LLM.")
            if base_llm_from_graph:
                try:
                    response_text = base_llm_from_graph.invoke(f"Répondez utilement: {message_body}").content
                except Exception as e:
                    print(f"[PROCESS_MESSAGE] Error fallback LLM (step {current_step}): '{e}'") # Corrected f-string
                    response_text = "Comment puis-je aider encore ?"
            else:
                print(f"[PROCESS_MESSAGE] base_llm_from_graph is None (step {current_step}).")
                response_text = "Comment aider ?"
        else:
            try:
                print(f"[PROCESS_MESSAGE] rag_chain found (step {current_step}). RAG invoke.")
                response_obj = rag_chain.invoke({"history": history, "question": message_body, "company_name": "TRANSLAB INTERNATIONAL", "company_specialty": "Interprétation et Traduction"})
                response_text = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error RAG chain (step {current_step}): '{e}'") # Corrected f-string
                response_text = "Souci avec mes notes. Une autre question ?"

    history.append({"role": "assistant", "content": response_text})
    return response_text

@whatsapp.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    print(f"[WEBHOOK_VERIFY] Mode: '{mode}', Token: '{token}', Expected: '{VERIFY_TOKEN}'") # Corrected f-string
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("[WEBHOOK_VERIFY] Success.")
        return challenge, 200
    else:
        print("[WEBHOOK_VERIFY] Failed.")
        return 'Forbidden', 403

@whatsapp.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    # print(f"[WEBHOOK_POST] Received: {json.dumps(data, indent=2)}") # Verbose
    try:
        if data.get('object') == 'whatsapp_business_account':
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if value.get('messages'):
                        for msg_obj in value.get('messages', []):
                            from_number_val = msg_obj.get('from')
                            msg_type = msg_obj.get('type')
                            if from_number_val and msg_type == 'text':
                                msg_body = msg_obj['text']['body']
                                print(f'[WEBHOOK_POST] Processing text message from {from_number_val}: "{msg_body}"')
                                response_text_val = process_message(msg_body, from_number_val)
                                print(f'[WEBHOOK_POST] Generated response for {from_number_val}: "{response_text_val}"')
                                if response_text_val:
                                    send_whatsapp_message(from_number_val, response_text_val)
                                else:
                                    print(f"[WEBHOOK_POST] No response for {from_number_val}.")
                            elif from_number_val:
                                print(f"[WEBHOOK_POST] Non-text type '{msg_type}' from {from_number_val}.")
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(f"[WEBHOOK_POST] Error: '{str(e)}'\n{traceback.format_exc()}") # Corrected f-string
        return jsonify({'status': 'error', 'message': "Internal server error"}), 500

def send_whatsapp_message(to_number: str, message_text: str):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("[WHATSAPP_SEND] CRITICAL: Token/PhoneID missing.")
        return {"error": "Server WhatsApp config error."}
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": message_text}}

    print(f'[WHATSAPP_SEND] To {to_number}: "{message_text}"')

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
        return result
    except requests.exceptions.Timeout:
        print(f"[WHATSAPP_SEND] Error: Timeout for {to_number}")
        return {"error": "Timeout sending."}
    except requests.exceptions.HTTPError as err:
        print(f"[WHATSAPP_SEND] HTTP error for {to_number}: {err}") # err is already a string
        if err.response is not None: print(f"[WHATSAPP_SEND] API Error ({err.response.status_code}): {err.response.text}")
        return {"error": f"HTTP {err.response.status_code}."} # Corrected f-string
    except requests.exceptions.RequestException as err:
        print(f"[WHATSAPP_SEND] Request error for {to_number}: {err}") # err is already a string
        return {"error": f"Request error: {err}"} # Corrected f-string
    except Exception as e:
        print(f"[WHATSAPP_SEND] Unexpected exception for {to_number}: '{e}'\n{traceback.format_exc()}") # Corrected f-string
        return {"error": "Unexpected server error."}
2. backend/lead_graph.py (from Turn 57 - Google Drive saving commented out, attempts folder load):

from typing import List
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
import csv
import os
import sqlite3
import traceback
from googleapiclient.http import MediaIoBaseUpload
import io
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

# def save_lead_to_drive(lead: Lead): # Temporarily commented out
#     print("[Google Drive] save_lead_to_drive called, but is temporarily disabled.")
#     return None

def collect_lead_from_text(text: str) -> Lead:
    if structured_llm is None:
        print("[COLLECT_LEAD] structured_llm is None. Cannot extract lead.")
        return Lead(name="Error: LLM N/A", email="Error: LLM N/A", phone="Error: LLM N/A")
    lead = structured_llm.invoke(text)
    save_lead_to_csv(lead)
    save_lead_to_sqlite(lead)
    # save_lead_to_drive(lead) # Temporarily commented out
    return lead

ACTIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1SXe5kPSgjbN9jT1T9TgWyY-JpNlbynqN")

def load_documents():
    print(f"[LEAD_GRAPH_INIT] Attempting to load documents from folder. Effective Folder ID being used: '{ACTIVE_FOLDER_ID}'") # Corrected f-string
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    print(f"[LEAD_GRAPH_INIT] Using service account key from env var GOOGLE_APPLICATION_CREDENTIALS: '{creds_path}'") # Corrected f-string

    if not creds_path:
        print("[LEAD_GRAPH_INIT] CRITICAL ERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        return []
    if not os.path.isfile(creds_path):
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR: Credentials file not found at path: '{creds_path}'") # Corrected f-string
        return []
    else:
        print(f"[LEAD_GRAPH_INIT] Credentials file confirmed to exist at: '{creds_path}'") # Corrected f-string

    try:
        print(f"[LEAD_GRAPH_INIT] Attempting to load from folder_id: '{ACTIVE_FOLDER_ID}' using GoogleDriveLoader.") # Corrected f-string
        loader = GoogleDriveLoader(
            service_account_key=creds_path,
            folder_id=ACTIVE_FOLDER_ID,
            file_types=["document", "pdf", "sheet"],
            recursive=True
        )
        print("[LEAD_GRAPH_INIT] GoogleDriveLoader initialized for folder scan.")
        docs = loader.load()
        print(f"[LEAD_GRAPH_INIT] loader.load() completed. Number of documents loaded: {len(docs) if docs is not None else 'None'}")
        if not docs:
            print(f"[LEAD_GRAPH_INIT] No documents loaded from folder: '{ACTIVE_FOLDER_ID}'. Check folder content, SA permissions, etc.") # Corrected f-string
        return docs
    except Exception as e:
        print(f"[LEAD_GRAPH_INIT] CRITICAL ERROR loading documents from folder '{ACTIVE_FOLDER_ID}': '{e}'") # Corrected f-string
        print(f"[LEAD_GRAPH_INIT] Traceback: {traceback.format_exc()}")
        return []

def setup_rag():
    docs = load_documents()
    print(f"[LEAD_GRAPH_INIT] setup_rag: docs loaded status: {docs is not None}, number of docs: {len(docs) if docs is not None else 'N/A'}")
    if not docs:
        print("[LEAD_GRAPH_INIT] setup_rag: No documents loaded, RAG chain will not be functional.")
        return None
    embeddings = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2", model_kwargs={'device': 'cpu'})
    vectorstore = FAISS.from_documents(docs, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2, "score_threshold": 0.8})
    prompt = ChatPromptTemplate.from_template("### Rôle ###\nVous êtes un assistant virtuel expert de TRANSLAB INTERNATIONAL...\n### Contexte ###\n{context}\n### Question ###\n{question}")
    rag_chain_local = RunnableMap({"context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]), "question": lambda x: x["question"]}) | prompt | llm
    print(f"[LEAD_GRAPH_INIT] setup_rag: returning rag_chain: {rag_chain_local is not None}")
    return rag_chain_local

rag_chain = setup_rag()
print(f"[LEAD_GRAPH_INIT] Global rag_chain initialized: {rag_chain is not None}")

if __name__ == "__main__":
    print("Testing lead_graph.py locally...")
    if not os.getenv("GROQ_API_KEY"): print("Warning: GROQ_API_KEY not set.")
    if rag_chain:
        print("\n--- RAG Chain Test ---")
        try:
            response = rag_chain.invoke({"question": "Quels sont vos services ?"})
            print(f"RAG Response: '{response.content if hasattr(response, 'content') else response}'") # Corrected f-string
        except Exception as e: print(f"Error invoking RAG chain: '{e}'") # Corrected f-string
    else: print("\n--- RAG Chain Test --- \nRAG chain is None. Skipping RAG test.")
    print("\n--- Lead Extraction Test ---")
    text = "Bonjour, je suis Jean Dupont. Mon email est jean.dupont@example.com et mon tel est 0123456789."
    try:
        if structured_llm:
            lead = collect_lead_from_text(text)
            print(f"Extracted Lead: '{lead}'") # Corrected f-string
        else:
            print("structured_llm is None, skipping lead extraction test.")
    except Exception as e: print(f"Error collecting lead: '{e}'") # Corrected
