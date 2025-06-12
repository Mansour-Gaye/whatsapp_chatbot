import os
import json
import hmac # Not strictly used in current logic, but often present in webhook setups
import hashlib # Same as hmac
import requests
from flask import Blueprint, request, jsonify # Consolidated Flask imports
from dotenv import load_dotenv
import traceback # For more detailed error logging in webhook

# Attempt to import components from lead_graph
try:
    from lead_graph import Lead, structured_llm, rag_chain, llm as base_llm_from_graph
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = True
except ImportError as e:
    print(f"[CRITICAL_IMPORT_ERROR] Failed to import from lead_graph: {e}. Some functionalities will be disabled.")
    LEAD_GRAPH_IMPORTED_SUCCESSFULLY = False
    Lead, structured_llm, rag_chain, base_llm_from_graph = None, None, None, None

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

def get_user_state(phone_number):
    if phone_number not in user_states:
        user_states[phone_number] = {
            "step": 0,
            "exchange_count": 0,
            "history": [],
            "lead": {"name": "", "email": "", "phone": phone_number} # Ensure phone_number is pre-filled if available
        }
    return user_states[phone_number]

def process_message(message_body: str, phone_number: str) -> str:
    state = get_user_state(phone_number)
    history = state["history"]
    history.append({"role": "user", "content": message_body})
    
    response_text = "Je rencontre un problème technique pour le moment. Veuillez réessayer plus tard." # Default error

    if not LEAD_GRAPH_IMPORTED_SUCCESSFULLY:
        print("[PROCESS_MESSAGE] Critical: lead_graph components not imported. Using static error message.")
        history.append({"role": "assistant", "content": response_text})
        return response_text

    current_step = state["step"]

    if current_step == 0:
        state["exchange_count"] += 1
        if rag_chain is None:
            print("[PROCESS_MESSAGE] rag_chain is None (step 0). Using fallback LLM.")
            if base_llm_from_graph:
                try:
                    response_text = base_llm_from_graph.invoke(f"Répondez de manière utile à la question suivante, même si vous n'avez pas de contexte spécifique: {message_body}").content
                except Exception as e:
                    print(f"[PROCESS_MESSAGE] Error during fallback LLM (step 0): {e}")
                    response_text = "Je ne peux pas accéder à ma base de connaissances pour le moment, mais comment puis-je vous aider autrement ?"
            else:
                print("[PROCESS_MESSAGE] base_llm_from_graph is None (step 0). Cannot use fallback LLM.")
                response_text = "Je ne peux pas accéder à ma base de connaissances pour le moment. Essayez une question plus générale."
        else:
            try:
                response_obj = rag_chain.invoke({
                    "history": history, "question": message_body,
                    "company_name": "TRANSLAB INTERNATIONAL", 
                    "company_specialty": "Interprétation de conférence et Traduction"
                })
                response_text = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error during RAG chain invocation (step 0): {e}")
                response_text = "J'ai eu un souci en consultant ma base de données. Pouvez-vous reformuler ?"

        if state["exchange_count"] >= 2 and current_step == 0: # Ensure step hasn't changed
            state["step"] = 1
            response_text += "\n\nPour mieux vous aider, puis-je connaître votre nom, email et téléphone ?"
    
    elif current_step == 1:
        if structured_llm is None:
            print("[PROCESS_MESSAGE] structured_llm is None (step 1). Cannot process lead.")
            response_text = "Je rencontre un souci pour traiter vos informations. Veuillez réessayer plus tard."
        else:
            try:
                lead_data = state["lead"]
                lead_infos = structured_llm.invoke(message_body)
                if lead_infos.name: lead_data["name"] = lead_infos.name
                if lead_infos.email: lead_data["email"] = lead_infos.email
                if lead_infos.phone: lead_data["phone"] = lead_infos.phone
                
                missing = [field for field in ["name", "email", "phone"] if not lead_data.get(field)]
                if missing:
                    response_text = f"Merci ! Il me manque encore votre {', '.join(missing)}."
                else:
                    # Assuming save_lead_to_csv etc. are available globally if imported from lead_graph
                    # from lead_graph import save_lead_to_csv, save_lead_to_sqlite # Or ensure they are imported
                    if Lead and callable(Lead) and callable(save_lead_to_csv) and callable(save_lead_to_sqlite):
                         save_lead_to_csv(Lead(**lead_data))
                         save_lead_to_sqlite(Lead(**lead_data))
                         # from lead_graph import save_lead_to_drive # If you want to save to drive
                         # save_lead_to_drive(Lead(**lead_data))
                         state["step"] = 2
                         response_text = "Merci, vos informations ont bien été enregistrées ! Comment puis-je vous aider ?"
                    else:
                        print("[PROCESS_MESSAGE] Lead saving functions or Lead class not available.")
                        response_text = "Merci pour les informations. Comment puis-je vous aider ensuite?"

            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error during lead processing (step 1): {e}")
                response_text = "Un problème est survenu lors de l'enregistrement de vos informations."
                
    else: # current_step == 2 or any other state (general conversation)
        if rag_chain is None:
            print("[PROCESS_MESSAGE] rag_chain is None (step 2+). Using fallback LLM.")
            if base_llm_from_graph:
                try:
                    response_text = base_llm_from_graph.invoke(f"Répondez de manière utile à la question suivante, même si vous n'avez pas de contexte spécifique: {message_body}").content
                except Exception as e:
                    print(f"[PROCESS_MESSAGE] Error during fallback LLM (step 2+): {e}")
                    response_text = "Comment puis-je vous assister davantage ?"
            else:
                print("[PROCESS_MESSAGE] base_llm_from_graph is None (step 2+). Cannot use fallback LLM.")
                response_text = "Comment puis-je vous aider ?"
        else:
            try:
                response_obj = rag_chain.invoke({
                    "history": history, "question": message_body,
                    "company_name": "TRANSLAB INTERNATIONAL", 
                    "company_specialty": "Interprétation de conférence et Traduction"
                })
                response_text = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
            except Exception as e:
                print(f"[PROCESS_MESSAGE] Error during RAG chain invocation (step 2+): {e}")
                response_text = "J'ai eu un souci en consultant mes notes. Que voulez-vous savoir d'autre ?"

    history.append({"role": "assistant", "content": response_text})
    return response_text

@whatsapp.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    print(f"[WEBHOOK] Vérification - Mode: {mode}, Token: {token}, Expected: {VERIFY_TOKEN}")
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("[WEBHOOK] Vérification réussie.")
        return challenge, 200
    else:
        print(f"[WEBHOOK] Vérification échouée. Mode: {mode}, Token: {token}")
        return 'Forbidden', 403

@whatsapp.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print(f"[WEBHOOK] Données reçues: {json.dumps(data, indent=2)}")
    try:
        if data.get('object') == 'whatsapp_business_account':
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if value.get('messages'):
                        for message_obj in value.get('messages', []): # Renamed to avoid conflict
                            from_number = message_obj.get('from')
                            if message_obj.get('text'):
                                message_body = message_obj['text']['body']
                                print(f"[WEBHOOK] Message de {from_number}: {message_body}")
                                response_text = process_message(message_body, from_number)
                                print(f"[WEBHOOK] Réponse générée: {response_text}")
                                if response_text: # Ensure there's a response to send
                                    send_whatsapp_message(from_number, response_text)
                            else:
                                print(f"[WEBHOOK] Type de message non supporté ou message vide: {message_obj.get('type')}")
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(f"[WEBHOOK] Erreur webhook: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def send_whatsapp_message(to_number, message_text):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("[WHATSAPP] ERREUR: WHATSAPP_TOKEN ou WHATSAPP_PHONE_ID manquant.")
        return {"error": "Configuration WhatsApp manquante côté serveur."}

    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": message_text}}
    
    print(f"[WHATSAPP] Envoi à {to_number} (type: {payload['type']}): {message_text}")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10) # Added timeout
        response.raise_for_status() 
        result = response.json()
        print(f"[WHATSAPP] Réponse API: {result}")
        return result
    except requests.exceptions.Timeout:
        print(f"[WHATSAPP] Erreur d'envoi: Timeout")
        return {"error": "Timeout lors de l'envoi du message WhatsApp."}
    except requests.exceptions.RequestException as e:
        print(f"[WHATSAPP] Erreur d'envoi: {e}")
        if e.response is not None:
            print(f"[WHATSAPP] Détails erreur API ({e.response.status_code}): {e.response.text}")
        return {"error": str(e)}
    except Exception as e:
        print(f"[WHATSAPP] Exception inattendue lors de l'envoi: {e}\n{traceback.format_exc()}")
        return {"error": "Exception inattendue lors de l'envoi du message."}
