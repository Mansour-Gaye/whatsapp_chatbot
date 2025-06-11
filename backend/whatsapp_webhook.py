from flask import Blueprint, request, jsonify
import requests
import os
from dotenv import load_dotenv
import json
from lead_graph import (
    collect_lead, 
    Lead, 
    structured_llm, 
    rag_chain, 
    llm,
    save_lead_to_csv,
    save_lead_to_sqlite
)

load_dotenv()

whatsapp = Blueprint('whatsapp', __name__)

# Configuration WhatsApp
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_PHONE_ID = os.getenv('WHATSAPP_PHONE_ID')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')

# Dictionnaire pour stocker l'état de la conversation par numéro
conversation_states = {}
# Dictionnaire pour stocker les leads en cours de collecte
pending_leads = {}

# Pour chaque numéro : état, nombre d'échanges, historique, lead
user_states = {}  # {phone_number: {"step": 0, "exchange_count": 0, "history": [], "lead": {...}}}

print(f"[CONFIG] WhatsApp Phone ID: {WHATSAPP_PHONE_ID}")
print(f"[CONFIG] Verify Token: {VERIFY_TOKEN}")
print(f"[CONFIG] WhatsApp Token: {'✅ Présent' if WHATSAPP_TOKEN else '❌ Manquant'}")

def get_or_create_lead(phone_number):
    """Récupère ou crée un nouveau lead pour un numéro"""
    if phone_number not in pending_leads:
        pending_leads[phone_number] = Lead(name="", email="", phone=phone_number)
    return pending_leads[phone_number]

def get_user_state(phone_number):
    if phone_number not in user_states:
        user_states[phone_number] = {
            "step": 0,
            "exchange_count": 0,
            "history": [],
            "lead": {"name": "", "email": "", "phone": phone_number}
        }
    return user_states[phone_number]

def process_message(message, phone_number):
    state = get_user_state(phone_number)
    step = state["step"]
    history = state["history"]
    lead = state["lead"]

    # Ajoute le message utilisateur à l'historique
    history.append({"role": "user", "content": message})

    if step == 0:
        state["exchange_count"] += 1
        # Appel à la chaîne RAG (comme sur le web)
        response = rag_chain.invoke({
            "history": history,
            "question": message,
            "company_name": "TRANSLAB INTERNATIONAL",
            "company_specialty": "Interprétation de conférence et Traduction"
        }).content
        history.append({"role": "assistant", "content": response})

        # Après 2 échanges, on passe à la collecte
        if state["exchange_count"] >= 2:
            state["step"] = 1
            return response + "\n\nPour mieux vous aider, puis-je connaître votre nom, email et téléphone ?"
        else:
            return response

    elif step == 1:
        # Appel à la chaîne de parsing de lead (comme sur le web)
        lead_infos = structured_llm.invoke(message)
        # Met à jour le lead
        if lead_infos.name:
            lead["name"] = lead_infos.name
        if lead_infos.email:
            lead["email"] = lead_infos.email
        if lead_infos.phone:
            lead["phone"] = lead_infos.phone

        # Vérifie les champs manquants
        missing = []
        if not lead["name"]:
            missing.append("nom")
        if not lead["email"]:
            missing.append("email")
        if not lead["phone"]:
            missing.append("téléphone")

        if missing:
            return f"Merci ! Il me manque encore votre {', '.join(missing)}."
        else:
            # Sauvegarde le lead
            save_lead_to_csv(Lead(**lead))
            save_lead_to_sqlite(Lead(**lead))
            state["step"] = 2
            return "Merci, vos informations ont bien été enregistrées ! Comment puis-je vous aider ?"

    else:
        # Chat normal après collecte
        response = rag_chain.invoke({
            "history": history,
            "question": message,
            "company_name": "TRANSLAB INTERNATIONAL",
            "company_specialty": "Interprétation de conférence et Traduction"
        }).content
        history.append({"role": "assistant", "content": response})
        return response

@whatsapp.route('/webhook', methods=['GET'])
def verify_webhook():
    """Vérification du webhook pour WhatsApp"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    print(f"[WEBHOOK] Vérification - Mode: {mode}, Token: {token}")

    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("[WEBHOOK] Vérification réussie")
            return challenge
        print("[WEBHOOK] Vérification échouée")
        return 'Forbidden', 403

@whatsapp.route('/webhook', methods=['POST'])
def webhook():
    """Gestion des messages entrants de WhatsApp"""
    data = request.get_json()
    print(f"[WEBHOOK] Données reçues: {json.dumps(data, indent=2)}")
    
    try:
        if 'object' in data and data['object'] == 'whatsapp_business_account':
            for entry in data['entry']:
                for change in entry['changes']:
                    if change['value'].get('messages'):
                        for message in change['value']['messages']:
                            from_number = message['from']
                            print(f"[WEBHOOK] Message reçu de: {from_number}")
                            
                            if 'text' in message:
                                message_body = message['text']['body']
                                print(f"[WEBHOOK] Contenu du message: {message_body}")
                                
                                # Passer le numéro de téléphone à process_message
                                response = process_message(message_body, from_number)
                                print(f"[WEBHOOK] Réponse générée: {response}")
                                
                                result = send_whatsapp_message(from_number, response)
                                print(f"[WEBHOOK] Résultat de l'envoi: {json.dumps(result, indent=2)}")
                            else:
                                print(f"[WEBHOOK] Type de message non supporté: {message.get('type')}")
            
            return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(f"[WEBHOOK] Erreur: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def send_whatsapp_message(to_number, message):
    """Envoie un message WhatsApp"""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message}
    }
    
    print(f"[WHATSAPP] Envoi du message à {to_number}")
    print(f"[WHATSAPP] URL: {url}")
    print(f"[WHATSAPP] Headers: {json.dumps(headers, indent=2)}")
    print(f"[WHATSAPP] Données: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        
        print(f"[WHATSAPP] Status Code: {response.status_code}")
        print(f"[WHATSAPP] Réponse: {json.dumps(result, indent=2)}")
        
        if response.status_code != 200:
            print(f"[WHATSAPP] Erreur d'envoi: {json.dumps(result, indent=2)}")
        
        return result
    except Exception as e:
        print(f"[WHATSAPP] Exception lors de l'envoi: {str(e)}")
        return {"error": str(e)} 