import os
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, Response
from supabase import create_client, Client
from flask_cors import CORS
import csv
import io
from datetime import datetime, timedelta

from whatsapp_webhook import whatsapp
from functools import wraps

# --- Section d'importation des modules de traitement ---
try:
    # Importation sélective pour la clarté
    from lead_graph import structured_llm, save_lead, llm, Lead, get_rag_chain # Ajout de get_rag_chain
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    LEAD_GRAPH_FOR_APP_IMPORTED = True
    print("[APP_INIT] Successfully imported all necessary modules.")
except ImportError as e:
    print(f"[APP_INIT] ERROR importing modules: {e}. API routes might fail.")
    LEAD_GRAPH_FOR_APP_IMPORTED = False
    structured_llm, save_lead, llm, Lead, HumanMessage, AIMessage, get_rag_chain = None, None, None, None, None, None, None

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

# Groq API Key Check
if not os.environ.get("GROQ_API_KEY"):
    print("[APP_INIT] CRITICAL: GROQ_API_KEY environment variable is not set. The chat API will not work.")

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
    visitor_id = data.get("visitorId", "unknown_visitor")

    if not history:
        return jsonify({"status": "error", "response": "L'historique de conversation est vide"}), 400

    try:
        # --- Utilisation de la chaîne RAG ---
        rag_chain = get_rag_chain()
        if not rag_chain:
            print("[API_CHAT] CRITICAL: RAG chain is not available.")
            raise Exception("La chaîne de conversation RAG n'est pas initialisée.")

        # Extraire la dernière question et formater l'historique
        last_user_message = history[-1]["content"]
        
        # Formatter l'historique précédent pour le prompt
        formatted_history = []
        for msg in history[:-1]:
            role = "Utilisateur" if msg.get("role") == "user" else "Assistant"
            formatted_history.append(f"{role}: {msg.get('content')}")
        
        history_str = "\n".join(formatted_history)

        # Invoquer la chaîne RAG
        response = rag_chain.invoke({
            "question": last_user_message,
            "history": history_str
        })
        
        response_content = response.content if hasattr(response, 'content') else str(response)

        # --- Log conversation to Supabase ---
        if supabase_client and visitor_id != "unknown_visitor":
            try:
                # Log du dernier message utilisateur
                user_message_to_log = {
                    "visitor_id": visitor_id,
                    "role": "user",
                    "content": last_user_message
                }
                supabase_client.table("conversations").insert(user_message_to_log).execute()

                # Log de la réponse de l'assistant
                assistant_response_data = {
                    "visitor_id": visitor_id,
                    "role": "assistant",
                    "content": response_content
                }
                supabase_client.table("conversations").insert(assistant_response_data).execute()
                
                print(f"[API_CHAT] Successfully logged conversation turn for {visitor_id} to Supabase.")
            except Exception as e_log:
                print(f"[API_CHAT] ERROR logging to Supabase for {visitor_id}: {e_log}")
        # --- End of Supabase logging ---

        return jsonify({"status": "success", "response": response_content})

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


@app.route("/demo")
def demo_page():
    return send_from_directory(os.path.dirname(app.root_path), "example.html")


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

@app.route('/api/admin/stats', methods=['GET'])
@login_required
def get_admin_stats():
    try:
        # 1. Get total number of leads
        count_response = supabase_client.table("leads").select("*", count='exact').execute()
        total_leads = count_response.count

        # 2. Get leads from the last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        leads_response = supabase_client.table("leads").select("created_at").gte("created_at", thirty_days_ago.isoformat()).execute()

        # 3. Process data to group by day
        leads_by_day = { (datetime.utcnow().date() - timedelta(days=i)).strftime('%Y-%m-%d'): 0 for i in range(30) }
        for lead in leads_response.data:
            # Ensure correct parsing of timezone-aware timestamp
            lead_date_str = lead['created_at'].split('T')[0]
            if lead_date_str in leads_by_day:
                leads_by_day[lead_date_str] += 1

        # 4. Format for Chart.js, ensuring correct order
        sorted_dates = sorted(leads_by_day.keys())
        labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%d %b') for d in sorted_dates]
        data = [leads_by_day[d] for d in sorted_dates]

        return jsonify({
            "total_leads": total_leads,
            "leads_over_time": {
                "labels": labels,
                "data": data
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/leads', methods=['GET'])
@login_required
def get_admin_leads():
    try:
        leads_response = supabase_client.table("leads").select("*").order("created_at", desc=True).execute()
        return jsonify(leads_response.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/leads/<visitor_id>', methods=['PUT'])
@login_required
def update_lead(visitor_id):
    try:
        data = request.get_json()
        # Valider/nettoyer les données ici si nécessaire
        update_data = {
            "name": data.get("name"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase_client.table("leads").update(update_data).eq("visitor_id", visitor_id).execute()

        if not response.data:
            return jsonify({"error": "Lead not found or update failed"}), 404

        return jsonify(response.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/leads/<visitor_id>/conversations', methods=['GET'])
@login_required
def get_lead_conversations(visitor_id):
    if not visitor_id or visitor_id in ['null', 'undefined']:
        return jsonify({"error": "Invalid visitor_id"}), 400
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
