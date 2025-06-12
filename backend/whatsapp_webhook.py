import os
import json
import requests
from flask import Blueprint, request, jsonify
from dotenv import load_dotenv
import traceback

try:
    from lead_graph import Lead, structured_llm, rag_chain, llm as base_llm_from_graph
    from lead_graph import save_lead_to_csv, save_lead_to_sqlite
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = True
    print("[WHATSAPP_WEBHOOK_INIT] Successfully imported components from lead_graph.")
except ImportError as e:
    print(f"[WHATSAPP_WEBHOOK_INIT] CRITICAL_IMPORT_ERROR: Failed to import from lead_graph: '{e}'. Fallback mode will be active.")
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = False
    Lead, structured_llm, rag_chain, base_llm_from_graph = None, None, None, None
    save_lead_to_csv, save_lead_to_sqlite = None, None

load_dotenv()
whatsapp = Blueprint('whatsapp', __name__)

WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_PHONE_ID = os.getenv('WHATSAPP_PHONE_ID')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
user_states = {}

print(f"[CONFIG] WhatsApp Phone ID: '{WHATSAPP_PHONE_ID}'")
print(f"[CONFIG] Verify Token: '{VERIFY_TOKEN}'")
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
    response_text = "Je rencontre un problème technique. Veuillez réessayer plus tard."

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
                    print(f"[PROCESS_MESSAGE] Error fallback LLM (step 0): '{e}'")
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
                print(f"[PROCESS_MESSAGE] Error RAG chain (step 0): '{e}'")
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
                missing = [f_item for f_item in ["name", "email", "phone"] if not lead_data.get(f_item)]
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
                print(f"[PROCESS_MESSAGE] Error lead processing (step 1): '{e}'\n{traceback.format_exc()}")
                response_text = "Problème d'enregistrement des infos."

    else: # current_step >= 2
        print(f"[PROCESS_MESSAGE] Step {current_step}: General post-lead chat")
        if rag_chain is None:
            print(f"[PROCESS_MESSAGE] rag_chain is None (step {current_step}). Fallback LLM.")
            if base_llm_from_graph:
                try:
                    response_text = base_llm_from_graph.invoke(f"Répondez utilement: {message_body}").content
                except Exception as e:
                    print(f"[PROCESS_MESSAGE] Error fallback LLM (step {current_step}): '{e}'")
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
                print(f"[PROCESS_MESSAGE] Error RAG chain (step {current_step}): '{e}'")
                response_text = "Souci avec mes notes. Une autre question ?"

    history.append({"role": "assistant", "content": response_text})
    return response_text

@whatsapp.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    print(f"[WEBHOOK_VERIFY] Mode: '{mode}', Token: '{token}', Expected: '{VERIFY_TOKEN}'")
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
        print(f"[WEBHOOK_POST] Error: '{str(e)}'\n{traceback.format_exc()}")
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
        print(f"[WHATSAPP_SEND] HTTP error for {to_number}: {err}")
        if err.response is not None: print(f"[WHATSAPP_SEND] API Error ({err.response.status_code}): {err.response.text}")
        return {"error": f"HTTP {err.response.status_code}."}
    except requests.exceptions.RequestException as err:
        print(f"[WHATSAPP_SEND] Request error for {to_number}: {err}")
        return {"error": f"Request error: {err}"}
    except Exception as e:
        print(f"[WHATSAPP_SEND] Unexpected exception for {to_number}: '{e}'\n{traceback.format_exc()}")
        return {"error": "Unexpected server error."}
