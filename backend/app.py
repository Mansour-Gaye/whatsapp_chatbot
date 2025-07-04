import os
from flask import Flask, request, jsonify
from supabase import create_client, Client
from flask_cors import CORS

from whatsapp_webhook import whatsapp
from functools import wraps

# --- Section d'importation des modules de traitement ---
try:
    from lead_graph import structured_llm, collect_lead_from_text, llm, Lead
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    LEAD_GRAPH_FOR_APP_IMPORTED = True
    print("[APP_INIT] Successfully imported all necessary modules.")
except ImportError as e:
    print(f"[APP_INIT] ERROR importing modules: {e}. API routes might fail.")
    LEAD_GRAPH_FOR_APP_IMPORTED = False
    structured_llm, collect_lead_from_text, llm, Lead, HumanMessage, AIMessage = None, None, None, None, None, None

app = Flask(__name__)
CORS(app)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')

# Supabase Client Initialization
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase_client: Client = None # Type hint for clarity

if supabase_url and supabase_key:
    try:
        supabase_client = create_client(supabase_url, supabase_key)
        print("[APP_INIT] Successfully connected to Supabase.")
    except Exception as e:
        print(f"[APP_INIT] ERROR connecting to Supabase: {e}")
else:
    print("[APP_INIT] WARNING: SUPABASE_URL and/or SUPABASE_KEY environment variables not set. Supabase integration will be disabled.")

def log_requests(f):
    """Un décorateur simple pour logger les requêtes (désactivé par défaut)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/chat", methods=["POST"])
@log_requests
def chat():
    data = request.get_json()
    history = data.get("history", []) # This is the original list of dicts from the request
    if not history:
        return jsonify({"status": "error", "response": "L'historique de conversation est vide"}), 400

    try:
        if not LEAD_GRAPH_FOR_APP_IMPORTED or llm is None or HumanMessage is None:
            print("[API_CHAT] LLM or message components not available.")
            raise Exception("LLM not configured for chat API")

        # --- Transformation de l'historique pour LangChain ---
        processed_history_for_llm = []
        for msg_data in history: # Use original history for transforming for LLM
            role = msg_data.get("role", "").lower()
            content = msg_data.get("content", "")
            if role == "user":
                processed_history_for_llm.append(HumanMessage(content=content))
            elif role in ("assistant", "ai"):
                processed_history_for_llm.append(AIMessage(content=content))

        # --- Prepend SystemMessage with company context ---
        company_context = "You are a helpful assistant for TRANSLAB INTERNATIONAL. Be polite and professional."
        # Add SystemMessage to the list that goes to the LLM
        processed_history_for_llm.insert(0, SystemMessage(content=company_context))
        # --- End of SystemMessage ---

        # question = history[-1].get("content", "") if history else "" # Not strictly needed if LLM uses the whole processed_history_for_llm

        # --- Debugging Print Statements (Optional) ---
        # print(f"[API_CHAT_DEBUG] Type of processed_history_for_llm: {type(processed_history_for_llm)}")
        # if processed_history_for_llm:
        #     print(f"[API_CHAT_DEBUG] Type of first element: {type(processed_history_for_llm[0])}")
        # print(f"[API_CHAT_DEBUG] Content of processed_history_for_llm: {processed_history_for_llm}")
        # --- End of Debugging ---

        response = llm.invoke(processed_history_for_llm) 

        # --- Log conversation to Supabase ---
        if supabase_client:
            user_id_to_log = "web_chat_session_01" # Placeholder
            try:
                # 1. Log System Message (company_context)
                system_message_data = {
                    "user_id": user_id_to_log,
                    "role": "system",
                    "content": company_context 
                }
                supabase_client.table("conversations").insert(system_message_data).execute()

                # 2. Log all messages from the original incoming 'history'
                for msg_data in history: # Iterate original history for logging
                    role = msg_data.get("role", "unknown").lower()
                    content = msg_data.get("content", "")
                    message_to_log = {
                        "user_id": user_id_to_log,
                        "role": role,
                        "content": content
                    }
                    supabase_client.table("conversations").insert(message_to_log).execute()

                # 3. Log Assistant's final response
                assistant_response_data = {
                    "user_id": user_id_to_log,
                    "role": "assistant",
                    "content": response.content
                }
                supabase_client.table("conversations").insert(assistant_response_data).execute()
                
                print("[API_CHAT] Successfully logged full conversation turn to Supabase.")
            except Exception as e_log:
                print(f"[API_CHAT] ERROR logging to Supabase: {e_log}")
        # --- End of Supabase logging ---

        return jsonify({"status": "success", "response": response.content})

    except Exception as e:
        print(f"[API_CHAT] Erreur dans /api/chat: {str(e)}")
        # Keeping your custom error message here as you might have a reason for it
        return jsonify({"status": "error", "response": "TEST DE DEPLOIEMENT REUSSI - ERREUR PERSISTE."}), 500

# --- /api/lead and health routes remain the same ---
@app.route("/api/lead", methods=["POST"])
@log_requests
def lead():
    data = request.get_json()
    user_input = data.get("input", "")
    save_flag = data.get("save", False)
    try:
        if not LEAD_GRAPH_FOR_APP_IMPORTED or structured_llm is None or collect_lead_from_text is None:
            print("[API_LEAD] Lead processing components not available.")
            raise Exception("Lead components not configured for lead API")

        lead_info = structured_llm.invoke(user_input)

        if not any([lead_info.name, lead_info.email, lead_info.phone]):
            return jsonify({"status": "error", "message": "Informations manquantes. Merci de fournir nom, email ou téléphone."}), 400

        if save_flag:
            collect_lead_from_text(user_input)
            print("[APP.PY] save_lead_to_drive call is temporarily disabled.")

        return jsonify({"status": "success", "lead": lead_info.model_dump()})

    except Exception as e:
        print(f"[API_LEAD] Erreur dans /api/lead: {str(e)}")
        return jsonify({"status": "error", "message": f"Erreur lors du traitement des informations de lead: {e}"}), 500

@app.route("/health")
def health():
    """Route pour vérifier que le service est en ligne."""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    is_debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=is_debug, host="0.0.0.0", port=port)
