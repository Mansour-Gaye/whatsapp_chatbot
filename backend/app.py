import os
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, Response
from supabase import create_client, Client
from flask_cors import CORS
import csv
import io
import re
from datetime import datetime, timedelta
from collections import defaultdict

from whatsapp_webhook import whatsapp
from functools import wraps

# --- Section d'importation des modules de traitement ---
try:
    # Importation sélective pour la clarté
    from lead_graph import structured_llm, save_lead, llm, Lead, create_rag_chain
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    LEAD_GRAPH_FOR_APP_IMPORTED = True
    print("[APP_INIT] Successfully imported all necessary modules.")
except ImportError as e:
    print(f"[APP_INIT] ERROR importing modules: {e}. API routes might fail.")
    LEAD_GRAPH_FOR_APP_IMPORTED = False
    structured_llm, save_lead, llm, Lead, HumanMessage, AIMessage, SystemMessage, create_rag_chain = None, None, None, None, None, None, None, None

app = Flask(__name__)
CORS(app)

# --- Image Family Discovery ---
def discover_image_families(static_dir):
    """
    Automatically discovers image families by finding common prefixes in filenames.
    A family is a group of 2 or more images sharing a common prefix ending in a hyphen.
    """
    public_dir = os.path.join(static_dir, 'public')
    if not os.path.exists(public_dir):
        print(f"[IMAGE_DISCOVERY] Directory not found: {public_dir}")
        return {}

    # Group files by their first component (e.g., "interpretation-cabine-1.png" -> "interpretation")
    # This helps to narrow down the search space for common prefixes.
    groups = defaultdict(list)
    all_files = [f for f in os.listdir(public_dir) if os.path.isfile(os.path.join(public_dir, f)) and '-' in f]
    for filename in all_files:
        groups[filename.split('-', 1)[0]].append(filename)

    final_families = {}
    for key, file_list in groups.items():
        if len(file_list) < 2:
            continue

        # Find the longest common prefix for the group
        strs = sorted(file_list)
        first, last = strs[0], strs[-1]
        i = 0
        while i < len(first) and i < len(last) and first[i] == last[i]:
            i += 1
        prefix = first[:i]

        # Refine the prefix to end at the last sensible hyphen
        if '-' in prefix:
            # This will correctly find "interpretation-cabine" from "interpretation-cabine-"
            family_name = prefix.rsplit('-', 1)[0]


            # Recalculate files belonging to this more precise family prefix
            family_files = [f for f in file_list if f.startswith(family_name + '-')]

            if len(family_files) >= 2:
                final_families[family_name] = [f"/static/public/{f}" for f in sorted(family_files)]


    print(f"[IMAGE_DISCOVERY] Automatically discovered families: {list(final_families.keys())}")
    return final_families

IMAGE_FAMILIES = {} # Initialize as global
with app.app_context():
    IMAGE_FAMILIES = discover_image_families(app.static_folder)
# --- End Image Family Discovery ---


# --- Emotion Discovery ---
def discover_emotions(static_dir):
    """
    Automatically discovers emotion images by scanning for 'personnage-*' with any common image extension.
    Returns a map of emotion names to their web paths.
    """
    public_dir = os.path.join(static_dir, 'public')
    if not os.path.exists(public_dir):
        print(f"[EMOTION_DISCOVERY] Directory not found: {public_dir}")
        return {}

    emotion_map = {}
    prefix = "personnage-"
    valid_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

    for filename in os.listdir(public_dir):
        if filename.startswith(prefix):
            name, ext = os.path.splitext(filename)
            if ext.lower() in valid_extensions:
                emotion_name = name[len(prefix):]
                if emotion_name: # Ensure it's not an empty string
                    emotion_map[emotion_name] = f"/static/public/{filename}"

    print(f"[EMOTION_DISCOVERY] Automatically discovered emotions: {list(emotion_map.keys())}")
    return emotion_map

EMOTION_MAP = {} # Initialize as global
with app.app_context():
    EMOTION_MAP = discover_emotions(app.static_folder)
# --- End Emotion Discovery ---


# --- RAG Chain Initialization ---
RAG_CHAIN = None
if LEAD_GRAPH_FOR_APP_IMPORTED:
    print("[APP_INIT] Initializing RAG chain...")
    RAG_CHAIN = create_rag_chain(image_families=IMAGE_FAMILIES, available_emotions=EMOTION_MAP)
    if RAG_CHAIN:
        print("[APP_INIT] RAG chain initialized successfully.")
    else:
        print("[APP_INIT] CRITICAL: RAG chain initialization failed.")
# --- End RAG Chain Initialization ---


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

def log_analytic_event(visitor_id: str, event_type: str, event_value: str):
    """Logs a single analytic event to the Supabase table."""
    if not supabase_client or visitor_id == "unknown_visitor":
        return

    try:
        event_data = {
            "visitor_id": visitor_id,
            "event_type": event_type,
            "event_value": event_value
        }
        supabase_client.table("analytics_events").insert(event_data).execute()
        print(f"[ANALYTICS] Logged event: {event_type} - {event_value} for {visitor_id}")
    except Exception as e:
        print(f"[ANALYTICS] ERROR logging event for {visitor_id}: {e}")

def manage_history_for_speed(history: list) -> list:
    """
    Manages conversation history for speed by truncating it if it gets too long.
    This is a "sliding window" approach.
    """
    MAX_MESSAGES = 10  # Trigger truncation if history exceeds this many messages
    MESSAGES_TO_KEEP = 8   # When truncating, keep the last N messages

    if len(history) > MAX_MESSAGES:
        print(f"[HISTORY_MANAGEMENT] History has {len(history)} messages. Truncating to keep the last {MESSAGES_TO_KEEP}.")
        return history[-MESSAGES_TO_KEEP:]

    return history


@app.route("/api/chat", methods=["POST"])
@log_requests
def chat():
    data = request.get_json()
    client_history = data.get("history", []) # Renommé pour éviter la confusion
    visitor_id = data.get("visitorId", "unknown_visitor")

    if not client_history:
        return jsonify({"status": "error", "response": "L'historique de conversation du client est vide"}), 400

    try:
        if not RAG_CHAIN:
            print("[API_CHAT] CRITICAL: RAG_CHAIN is not available.")
            return jsonify({"status": "error", "response": "L'assistant IA est actuellement indisponible."}), 500

        langchain_history = []
        for msg in client_history[:-1]:
            if msg.get("role") == "user":
                langchain_history.append(HumanMessage(content=msg.get("content")))
            elif msg.get("role") in ["assistant", "bot"]:
                langchain_history.append(AIMessage(content=msg.get("content")))

        # --- GESTION DE L'HISTORIQUE (OPTIMISÉ POUR LA VITESSE) ---
        langchain_history = manage_history_for_speed(langchain_history)
        # --- FIN DE LA GESTION DE L'HISTORIQUE ---

        last_user_message = client_history[-1]["content"]

        # Invoquer la chaîne RAG de manière synchrone pour le débogage
        response_message = RAG_CHAIN.invoke({
            "question": last_user_message,
            "history": langchain_history
        })
        
        response_content = response_message.content
        response_options = {}

        # --- Analyse de la réponse pour les commandes spéciales ---
        carousel_match = re.search(r'\[carousel:\s*([^\]]+)\]', response_content)

        if carousel_match:
            family_name = carousel_match.group(1).strip()
            log_analytic_event(visitor_id, "carousel", family_name)
            # Nettoyer le texte de la réponse
            response_content = response_content.replace(carousel_match.group(0), '').strip()

            if family_name in IMAGE_FAMILIES:
                response_options['carousel_images'] = IMAGE_FAMILIES[family_name]
                print(f"[API_CHAT] Carousel triggered for family: {family_name}")
            else:
                # Si la famille demandée par le LLM n'existe pas, on loggue une alerte
                print(f"[API_CHAT] WARNING: Carousel requested for non-existent family: {family_name}")


        # --- Smart Guardrail for "near misses" on carousels ---
        # If the AI announced a carousel but forgot the tag, we'll try to add it.
        guardrail_triggers = ["carrousel", "voici les images", "voici des photos", "galerie d'images", "quelques exemples en image"]
        if not response_options.get('carousel_images') and any(trigger in response_content.lower() for trigger in guardrail_triggers):
            user_message_lower = last_user_message.lower()
            # This keyword map is specifically for the guardrail
            guardrail_family_map = {
                "interpretes": "interprete",
                "interprete": "interprete",
                "cabines": "interpretation-cabine",
                "cabine": "interpretation-cabine",
                "personnages": "personnage",
                "personnage": "personnage",
                "technologie": "technologie-cabine",
                "webinaire": "webinaire-onu-femmes-crdi",
                "expériences": "webinaire-onu-femmes-crdi", # Map "experiences" to a relevant carousel
                "experience": "webinaire-onu-femmes-crdi",
                "services": "interpretation-cabine" # Map "services" to a relevant carousel
            }
            for keyword, family in guardrail_family_map.items():
                if keyword in user_message_lower and family in IMAGE_FAMILIES:
                    print(f"[API_CHAT] Smart Guardrail: AI announced a carousel, adding family '{family}' based on user query.")
                    log_analytic_event(visitor_id, "carousel", family)
                    response_options['carousel_images'] = IMAGE_FAMILIES[family]
                    break

        # --- Analyse de la réponse pour l'émotion ---
        emotion_match = re.search(r'\[emotion:\s*([^\]]+)\]', response_content)
        if emotion_match:
            emotion_name = emotion_match.group(1).strip()
            log_analytic_event(visitor_id, "emotion", emotion_name)
            response_content = response_content.replace(emotion_match.group(0), '').strip()


            # Use the dynamically discovered EMOTION_MAP
            if emotion_name in EMOTION_MAP:
                response_options['emotion_image'] = EMOTION_MAP[emotion_name]
                print(f"[API_CHAT] Emotion triggered: {emotion_name}")
            else:
                # This case is now more important, as the LLM might hallucinate an emotion
                # that doesn't exist as a file.
                print(f"[API_CHAT] WARNING: Emotion '{emotion_name}' requested by LLM but not found in discovered files.")

        # --- Analyse de la réponse pour les images individuelles ---
        image_regex = r'\[image:\s*([^\]]+)\]'
        image_matches = re.findall(image_regex, response_content)
        for image_name in image_matches:
            log_analytic_event(visitor_id, "image_tag", image_name.strip())

        # --- Log de la conversation dans Supabase ---
        if supabase_client and visitor_id != "unknown_visitor":
            try:
                user_message_to_log = {
                    "visitor_id": visitor_id,
                    "role": "user",
                    "content": last_user_message
                }
                supabase_client.table("conversations").insert(user_message_to_log).execute()

                # On loggue la réponse textuelle, même si un carrousel est présent
                assistant_response_data = {
                    "visitor_id": visitor_id,
                    "role": "assistant",
                    "content": response_content
                }
                supabase_client.table("conversations").insert(assistant_response_data).execute()
                
                print(f"[API_CHAT] Successfully logged conversation turn for {visitor_id} to Supabase.")
            except Exception as e_log:
                print(f"[API_CHAT] ERROR logging to Supabase for {visitor_id}: {e_log}")
        # --- Fin du log Supabase ---

        return jsonify({"status": "success", "response": response_content, "options": response_options})

    except Exception as e:
        print(f"[API_CHAT] Erreur dans /api/chat: {str(e)}")
        # Ajout du traceback pour un meilleur débogage
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "response": f"Une erreur interne est survenue: {str(e)}"}), 500

@app.route("/api/track", methods=["POST"])
@log_requests
def track_event():
    data = request.get_json()
    visitor_id = data.get("visitorId")
    event_type = data.get("event_type")
    event_value = data.get("event_value")

    if not all([visitor_id, event_type, event_value]):
        return jsonify({"status": "error", "message": "Missing required event data"}), 400

    log_analytic_event(visitor_id, event_type, event_value)

    return jsonify({"status": "success"})


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

        # Récupérer les informations du lead (manière robuste)
        lead_response = supabase_client.table("leads").select("*").eq("visitor_id", visitor_id).execute()
        if lead_response.data:
            lead_data = lead_response.data[0] # Prendre le premier résultat

        # Récupérer l'historique de la conversation
        history_response = supabase_client.table("conversations").select("role, content, created_at").eq("visitor_id", visitor_id).order("created_at", desc=False).execute()
        if history_response.data:
            # Formatter l'historique pour le frontend
            for item in history_response.data:
                history.append({
                    "sender": item['role'],
                    "text": item['content'],
                    "timestamp": item['created_at']
                })

        return jsonify({
            "status": "success",
            "lead": lead_data, # Sera None si non trouvé
            "history": history # Sera une liste vide si non trouvée
        })

    except Exception as e:
        print(f"[API_LOOKUP] Erreur inattendue dans /api/visitor/lookup: {str(e)}")
        return jsonify({"status": "error", "message": f"Une erreur interne inattendue est survenue: {str(e)}"}), 500


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

@app.route('/api/admin/analytics', methods=['GET'])
@login_required
def get_admin_analytics():
    try:
        # --- 1. Conversation Stats ---
        conv_response = supabase_client.table("conversations").select("visitor_id").execute()
        all_visitor_ids = [item['visitor_id'] for item in conv_response.data]

        total_conversations = len(set(all_visitor_ids))
        total_messages = len(all_visitor_ids)
        avg_messages_per_conversation = round(total_messages / total_conversations, 2) if total_conversations > 0 else 0

        # --- 2. Lead Stats (from original function) ---
        leads_count_response = supabase_client.table("leads").select("visitor_id", count='exact').execute()
        total_leads = leads_count_response.count

        # --- 3. Analytics Events Stats ---
        events_response = supabase_client.table("analytics_events").select("event_type, event_value").execute()
        events_data = events_response.data

        # Aggregate counts for each event type
        event_counts = defaultdict(lambda: defaultdict(int))
        for event in events_data:
            event_counts[event['event_type']][event['event_value']] += 1

        def get_top_events(event_type, limit=5):
            if event_type not in event_counts:
                return []

            sorted_events = sorted(event_counts[event_type].items(), key=lambda item: item[1], reverse=True)
            return [{"name": name, "count": count} for name, count in sorted_events[:limit]]

        # --- 4. Assemble Response ---
        analytics_data = {
            "summary_stats": {
                "total_conversations": total_conversations,
                "total_leads": total_leads,
                "avg_messages_per_conversation": avg_messages_per_conversation,
            },
            "top_events": {
                "carousels": get_top_events("carousel"),
                "emotions": get_top_events("emotion"),
                "image_tags": get_top_events("image_tag"),
                "quick_reply_clicks": get_top_events("quick_reply_click")
            }
        }

        return jsonify(analytics_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
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
