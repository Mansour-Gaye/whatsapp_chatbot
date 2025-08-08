import os
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, Response
from supabase import create_client, Client
from flask_cors import CORS
import csv
import io

from whatsapp_webhook import whatsapp
from functools import wraps

# --- Section d'importation des modules de traitement ---
try:
    # Importation sélective pour la clarté
    from lead_graph import structured_llm, save_lead, llm, Lead
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    LEAD_GRAPH_FOR_APP_IMPORTED = True
    print("[APP_INIT] Successfully imported all necessary modules.")
except ImportError as e:
    print(f"[APP_INIT] ERROR importing modules: {e}. API routes might fail.")
    LEAD_GRAPH_FOR_APP_IMPORTED = False
    structured_llm, save_lead, llm, Lead, HumanMessage, AIMessage = None, None, None, None, None, None

app = Flask(__name__)
CORS(app)

# --- Configuration pour l'admin ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default-secret-key-for-dev')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin') # Utiliser 'admin' comme mot de passe par défaut pour le dev

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
    history = data.get("history", [])
    visitor_id = data.get("visitorId", "unknown_visitor") # Récupérer le visitorId

    if not history:
        return jsonify({"status": "error", "response": "L'historique de conversation est vide"}), 400

    try:
        if not LEAD_GRAPH_FOR_APP_IMPORTED or llm is None or HumanMessage is None:
            print("[API_CHAT] LLM or message components not available.")
            raise Exception("LLM not configured for chat API")

        # --- Transformation de l'historique pour LangChain ---
        processed_history_for_llm = []
        for msg_data in history:
            role = msg_data.get("role", "").lower()
            content = msg_data.get("content", "")
            if role == "user":
                processed_history_for_llm.append(HumanMessage(content=content))
            elif role in ("assistant", "ai"):
                processed_history_for_llm.append(AIMessage(content=content))

        # --- Prepend SystemMessage with company context ---
        company_context = "You are a helpful assistant for TRANSLAB INTERNATIONAL. Be polite and professional."
        processed_history_for_llm.insert(0, SystemMessage(content=company_context))
        # --- End of SystemMessage ---

        response = llm.invoke(processed_history_for_llm) 

        # --- Log conversation to Supabase ---
        if supabase_client and visitor_id != "unknown_visitor":
            try:
                # 2. Log last user message from history
                last_user_message = history[-1]
                user_message_to_log = {
                    "visitor_id": visitor_id,
                    "role": "user",
                    "content": last_user_message.get("content", "")
                }
                supabase_client.table("conversations").insert(user_message_to_log).execute()

                # 3. Log Assistant's final response
                assistant_response_data = {
                    "visitor_id": visitor_id,
                    "role": "assistant",
                    "content": response.content
                }
                supabase_client.table("conversations").insert(assistant_response_data).execute()
                
                print(f"[API_CHAT] Successfully logged conversation turn for {visitor_id} to Supabase.")
            except Exception as e_log:
                print(f"[API_CHAT] ERROR logging to Supabase for {visitor_id}: {e_log}")
        # --- End of Supabase logging ---

        return jsonify({"status": "success", "response": response.content})

    except Exception as e:
        print(f"[API_CHAT] Erreur dans /api/chat: {str(e)}")
        return jsonify({"status": "error", "response": f"Une erreur interne est survenue: {str(e)}"}), 500

@app.route("/api/lead", methods=["POST"])
@log_requests
def lead():
    data = request.get_json()
    user_input = data.get("input", "")
    current_lead_data = data.get("current_lead", {})
    visitor_id = data.get("visitorId") # Récupérer le visitorId

    try:
        if not LEAD_GRAPH_FOR_APP_IMPORTED or structured_llm is None or save_lead is None:
            print("[API_LEAD] Lead processing components not available.")
            raise Exception("Lead components not configured for lead API")

        # 1. Crée un objet Lead à partir des données actuelles
        current_lead = Lead(**current_lead_data)

        # 2. Extrait les nouvelles informations du message de l'utilisateur
        new_info = structured_llm.invoke(user_input)

        # 3. Met à jour le lead avec les nouvelles informations non vides
        updated_data = current_lead.model_dump()
        new_data = new_info.model_dump()
        for key, value in new_data.items():
            if value:
                updated_data[key] = value

        updated_lead = Lead(**updated_data)

        # 4. Sauvegarde les informations (partielles ou complètes) dans Supabase
        save_lead(updated_lead, visitor_id=visitor_id)

        # 5. Vérifie si le lead est "suffisamment" complet pour changer de message
        is_complete = all([updated_lead.name, updated_lead.email, updated_lead.phone])

        response_message = "Merci pour ces informations ! Continuons."
        if is_complete:
            response_message = "Merci ! Vos informations sont complètes. Comment puis-je vous aider maintenant ?"

        return jsonify({
            "status": "success",
            "lead": updated_lead.model_dump(),
            "complete": is_complete,
            "message": response_message
        })

    except Exception as e:
        print(f"[API_LEAD] Erreur dans /api/lead: {str(e)}")
        return jsonify({"status": "error", "message": f"Une erreur interne est survenue: {str(e)}"}), 500

@app.route("/api/visitor/lookup", methods=["POST"])
def visitor_lookup():
    data = request.get_json()
    visitor_id = data.get("visitorId")

    if not visitor_id:
        return jsonify({"status": "error", "message": "visitorId manquant"}), 400

    try:
        lead_data = None
        history = []

        # Récupérer les informations du lead
        lead_response = supabase_client.table("leads").select("*").eq("visitor_id", visitor_id).single().execute()
        if lead_response.data:
            lead_data = lead_response.data

        # Récupérer l'historique de la conversation
        history_response = supabase_client.table("conversations").select("role, content, created_at").eq("visitor_id", visitor_id).order("created_at", desc=False).execute()
        if history_response.data:
            # Formatter l'historique pour le frontend
            for item in history_response.data:
                # Le frontend attend 'sender' et 'text'
                history.append({
                    "sender": item['role'],
                    "text": item['content'],
                    "timestamp": item['created_at']
                })


        return jsonify({
            "status": "success",
            "lead": lead_data,
            "history": history
        })

    except Exception as e:
        # Gérer le cas où .single() ne trouve rien (lance une exception)
        if "PostgrestError" in str(e) and "0 rows" in str(e):
             return jsonify({
                "status": "success",
                "lead": None,
                "history": []
            })
        print(f"[API_LOOKUP] Erreur dans /api/visitor/lookup: {str(e)}")
        return jsonify({"status": "error", "message": f"Une erreur interne est survenue: {str(e)}"}), 500


@app.route("/health")
def health():
    """Route pour vérifier que le service est en ligne."""
    return jsonify({"status": "healthy"}), 200

from flask import send_from_directory

@app.route("/chatbot")
def chatbot_page():
    return send_from_directory("static", "index.html")

# =================================================================
# Section Admin
# =================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
def admin_home():
    if 'logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return 'Mot de passe incorrect', 401
    return send_from_directory('static', 'admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    return send_from_directory('static', 'admin/dashboard.html')

# --- API pour l'interface d'administration ---

@app.route('/api/admin/leads', methods=['GET'])
@login_required
def get_admin_leads():
    try:
        leads_response = supabase_client.table("leads").select("*").order("created_at", desc=True).execute()
        return jsonify(leads_response.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/leads/<visitor_id>/conversations', methods=['GET'])
@login_required
def get_lead_conversations(visitor_id):
    try:
        history_response = supabase_client.table("conversations").select("role, content, created_at").eq("visitor_id", visitor_id).order("created_at", desc=False).execute()
        return jsonify(history_response.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/leads/export', methods=['GET'])
@login_required
def export_leads_csv():
    try:
        leads_response = supabase_client.table("leads").select("name, email, phone, created_at").execute()

        output = io.StringIO()
        writer = csv.writer(output)

        # Écrire l'en-tête
        writer.writerow(['Nom', 'Email', 'Téléphone', 'Date de création'])

        # Écrire les données
        for lead in leads_response.data:
            writer.writerow([lead.get('name'), lead.get('email'), lead.get('phone'), lead.get('created_at')])

        output.seek(0)

        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=leads.csv"}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    is_debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=is_debug, host="0.0.0.0", port=port)
