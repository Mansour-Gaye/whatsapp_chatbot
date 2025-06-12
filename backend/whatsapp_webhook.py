import os
import json
# import hmac # Not strictly used, can be omitted if not needed elsewhere
# import hashlib # Not strictly used
import requests
from flask import Blueprint, request, jsonify # Consolidated Flask imports
from dotenv import load_dotenv
import traceback # For more detailed error logging in webhook

# Attempt to import components from lead_graph
try:
    from lead_graph import Lead, structured_llm, rag_chain, llm as base_llm_from_graph
    # Also import saving functions if they are to be called from here
    from lead_graph import save_lead_to_csv, save_lead_to_sqlite 
    # from lead_graph import save_lead_to_drive # If you plan to re-enable and call this
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = True
    print("[WHATSAPP_WEBHOOK_INIT] Successfully imported components from lead_graph.")
except ImportError as e:
    print(f"[WHATSAPP_WEBHOOK_INIT] CRITICAL_IMPORT_ERROR: Failed to import from lead_graph: {e}. Fallback mode will be active.")
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = False
    # Define placeholders if import fails, so the rest of the script doesn't crash immediately on definition
    Lead, structured_llm, rag_chain, base_llm_from_graph = None, None, None, None
    save_lead_to_csv, save_lead_to_sqlite = None, None 
    # save_lead_to_drive = None

load_dotenv()

whatsapp = Blueprint('whatsapp', __name__)

# WhatsApp Configuration
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_PHONE_ID = os.getenv('WHATSAPP_PHONE_ID')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')

user_states = {} 

print(f"[CONFIG] WhatsApp Phone ID: {WHATSAPP_PHONE_ID}")
print(f"[CONFIG] Verify Token: {VERIFY_TOKEN}")
print(f"[CONFIG] WhatsApp Token: {'✅ Présent' if WHATSAPP_TOKEN else '❌ Manquant'}")

def get_user_state(phone_number: str) -> dict:
    if phone_number not in user_states:
        user_states[phone_number] = {
            "step": 0,
            "exchange_count": 0,
            "history": [],
            "lead": {"name": "", "email": "", "phone": phone_number}
        }
    return user_states[phone_number]

def process_message(message_body: str, phone_number: str) -> str:
    state = get_user_state(phone_number)
    history = state["history"]
    history.append({"role": "user", "content": message_body})
    
    # Default response in case all logic paths fail
    response_text = "Je rencontre un problème technique pour le moment. Veuillez réessayer plus tard." 

    if not LEAD_GRAPH_IMPORTED_SUCCESSFULLY:
        print("[PROCESS_MESSAGE] Critical: lead_graph components were not imported. Using static error message.")
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
                    response_text = base_llm_from_graph.invoke(f"Répondez de manière utile à la question suivante, même si vous n'avez pas de contexte spécifique: {message_body}").content
                except Exception as e:
                    print(f"[PROCESS_MESSAGE] Error during fallback LLM (step 0): {e}")
                    response_text = "Je ne peux pas accéder à ma base de connaissances pour le moment, mais comment puis-je vous aider autrement ?"
            else: # base_llm_from_graph is also None
                print("[PROCESS_MESSAGE] base_llm_from_graph is None (step 0). Cannot use fallback LLM. GROQ_API_KEY might be missing or llm failed to init.")
                response_text = "Je ne peux pas accéder à mes outils de réponse avancés pour le moment. Essayez une question plus générale."
        else: # rag_chain is available
            try:
                print("[PROCESS_MESSAGE] rag_chain found (step 0). Attempting RAG invoke.")
                response_obj = rag_chain.invoke({
                    "history": history, "question": message_body,
                    "company_name": "TRANSLAB INTERNATIONAL", 
                    "company_specialty": "Interprétation de conférence et Traduction"
                })
                response_text = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error during RAG chain invocation (step 0): {e}")
                response_text = "J'ai eu un souci en consultant ma base de données. Pouvez-vous reformuler ?"
        
        # Transition to lead collection after 2 exchanges
        if state["exchange_count"] >= 2: # Check before modifying response_text
            print(f"[PROCESS_MESSAGE] Transitioning to step 1 (lead collection).")
            state["step"] = 1
            response_text += "\n\nPour mieux vous aider, puis-je connaître votre nom, email et téléphone ?"
    
    elif current_step == 1:
        print("[PROCESS_MESSAGE] Step 1: Lead Collection")
        lead_data = state["lead"]
        if structured_llm is None:
            print("[PROCESS_MESSAGE] structured_llm is None (step 1). Cannot process lead.")
            response_text = "Je rencontre un souci pour traiter vos informations. Veuillez réessayer plus tard."
        else:
            try:
                print("[PROCESS_MESSAGE] structured_llm found (step 1). Attempting structured_llm.invoke.")
                lead_infos = structured_llm.invoke(message_body)
                if lead_infos.name: lead_data["name"] = lead_infos.name
                if lead_infos.email: lead_data["email"] = lead_infos.email
                if lead_infos.phone: lead_data["phone"] = lead_infos.phone
                
                missing = [field for field in ["name", "email", "phone"] if not lead_data.get(field)]
                if missing:
                    response_text = f"Merci ! Il me manque encore votre {', '.join(missing)}."
                else:
                    if Lead and callable(save_lead_to_csv) and callable(save_lead_to_sqlite):
                         current_lead_instance = Lead(**lead_data)
                         save_lead_to_csv(current_lead_instance)
                         save_lead_to_sqlite(current_lead_instance)
                         # if callable(save_lead_to_drive): save_lead_to_drive(current_lead_instance) # If re-enabled
                         print(f"[PROCESS_MESSAGE] Lead collected and saved: {lead_data}")
                         state["step"] = 2
                         response_text = "Merci, vos informations ont bien été enregistrées ! Comment puis-je vous aider ?"
                    else:
                        print("[PROCESS_MESSAGE] Lead class or saving functions (CSV/SQLite) not available/imported correctly.")
                        response_text = "Merci pour les informations. Comment puis-je vous aider ensuite?"
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error during lead processing (step 1): {e}\n{traceback.format_exc()}")
                response_text = "Un problème est survenu lors de l'enregistrement de vos informations."
                
    else: # current_step == 2 or any other state (general conversation post-lead)
        print(f"[PROCESS_MESSAGE] Step {current_step}: General post-lead conversation")
        if rag_chain is None:
            print(f"[PROCESS_MESSAGE] rag_chain is None (step {current_step}). Using fallback LLM.")
            if base_llm_from_graph:
                try:
                    response_text = base_llm_from_graph.invoke(f"Répondez de manière utile à la question suivante, même si vous n'avez pas de contexte spécifique: {message_body}").content
                except Exception as e:
                    print(f"[PROCESS_MESSAGE] Error during fallback LLM (step {current_step}): {e}")
                    response_text = "Comment puis-je vous assister davantage ?"
            else: # base_llm_from_graph is also None
                print(f"[PROCESS_MESSAGE] base_llm_from_graph is None (step {current_step}). Cannot use fallback LLM.")
                response_text = "Comment puis-je vous aider ?"
        else: # rag_chain is available
            try:
                print(f"[PROCESS_MESSAGE] rag_chain found (step {current_step}). Attempting RAG invoke.")
                response_obj = rag_chain.invoke({
                    "history": history, "question": message_body,
                    "company_name": "TRANSLAB INTERNATIONAL", 
                    "company_specialty": "Interprétation de conférence et Traduction"
                })
                response_text = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error during RAG chain invocation (step {current_step}): {e}")
                response_text = "J'ai eu un souci en consultant mes notes. Que voulez-vous savoir d'autre ?"

    history.append({"role": "assistant", "content": response_text})
    return response_text

@whatsapp.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    print(f"[WEBHOOK_VERIFY] Mode: {mode}, Token: {token}, Expected Verify Token: {VERIFY_TOKEN}")
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("[WEBHOOK_VERIFY] Verification successful.")
        return challenge, 200
    else:
        print(f"[WEBHOOK_VERIFY] Verification failed.")
        return 'Forbidden', 403

@whatsapp.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print(f"[WEBHOOK_POST] Received data: {json.dumps(data, indent=2)}")
    try:
        if data.get('object') == 'whatsapp_business_account':
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if value.get('messages'):
                        for message_obj in value.get('messages', []): # Renamed to avoid conflict
                            from_number = message_obj.get('from')
                            message_type = message_obj.get('type')
                            if from_number and message_type == 'text':
                                message_body = message_obj['text']['body']
                                # Corrected print statement:
                                print(f'[WEBHOOK_POST] Processing text message from {from_number}: "{message_body}"')
                                response_text = process_message(message_body, from_number)
                                print(f"[WEBHOOK_POST] Generated response for {from_number}: "{response_text}"")
                                if response_text: # Ensure there's a response to send
                                    send_whatsapp_message(from_number, response_text)
                                else:
                                    print(f"[WEBHOOK_POST] No response generated for {from_number}.")
                            elif from_number: # Message received but not text
                                print(f"[WEBHOOK_POST] Received non-text message type '{message_type}' from {from_number}. No action taken.")
                            else:
                                print(f"[WEBHOOK_POST] Message received without 'from_number' or not a text message.")
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(f"[WEBHOOK_POST] Error processing webhook: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': "Internal server error"}), 500

def send_whatsapp_message(to_number: str, message_text: str):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("[WHATSAPP_SEND] CRITICAL ERROR: WHATSAPP_TOKEN or WHATSAPP_PHONE_ID missing from environment variables.")
        return {"error": "Server configuration error for WhatsApp."}

    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": message_text}}
    
    print(f"[WHATSAPP_SEND] Sending to {to_number}: "{message_text}"")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15) 
        response.raise_for_status() 
        result = response.json()
        print(f"[WHATSAPP_SEND] API Response: {result}")
        return result
    except requests.exceptions.Timeout:
        print(f"[WHATSAPP_SEND] Error: Timeout after 15s for {to_number}")
        return {"error": "Timeout sending WhatsApp message."}
    except requests.exceptions.HTTPError as http_err:
        print(f"[WHATSAPP_SEND] HTTP error for {to_number}: {http_err}")
        if http_err.response is not None:
            print(f"[WHATSAPP_SEND] API Error Details ({http_err.response.status_code}): {http_err.response.text}")
        return {"error": f"HTTP {http_err.response.status_code} error sending message."}
    except requests.exceptions.RequestException as req_err:
        print(f"[WHATSAPP_SEND] Request error for {to_number}: {req_err}")
        return {"error": f"Request error sending message: {req_err}"}
    except Exception as e: 
        print(f"[WHATSAPP_SEND] Unexpected exception for {to_number}: {e}\n{traceback.format_exc()}")
        return {"error": "Unexpected server error sending message."
