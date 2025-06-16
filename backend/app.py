import os
from flask import Flask, request, jsonify, session as flask_session # Added flask_session
from supabase import create_client, Client
from flask_cors import CORS
import uuid # For generating session IDs

from whatsapp_webhook import whatsapp # Assuming this is still needed
from functools import wraps

# --- Section d'importation des modules de traitement ---
try:
    # Existing imports for lead_graph (RAG, LLM, Lead model)
    from backend.lead_graph import structured_llm, collect_lead_from_text, llm as lead_llm, Lead
    # New import for the booking graph
    from backend.booking_graph import invoke_booking_graph, BookingGraphState # Assuming BookingGraphState might be useful for typing/context
    ALL_MODULES_IMPORTED = True
    print("[APP_INIT] Successfully imported all necessary modules including booking_graph.")
except ImportError as e:
    print(f"[APP_INIT] ERROR importing modules: {e}. API routes might fail.")
    ALL_MODULES_IMPORTED = False
    structured_llm, collect_lead_from_text, lead_llm, Lead = None, None, None, None
    invoke_booking_graph, BookingGraphState = None, None

# Langchain message types (already in original app.py)
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


app = Flask(__name__)
CORS(app) # Allow all origins for simplicity in dev
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_default_secret_key_for_sessions") # Needed for Flask session
app.register_blueprint(whatsapp, url_prefix='/whatsapp') # Assuming this is still relevant

# Supabase Client Initialization (as before)
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase_client: Client = None

if supabase_url and supabase_key:
    try:
        supabase_client = create_client(supabase_url, supabase_key)
        print("[APP_INIT] Successfully connected to Supabase.")
    except Exception as e:
        print(f"[APP_INIT] ERROR connecting to Supabase: {e}")
else:
    print("[APP_INIT] WARNING: SUPABASE_URL and/or SUPABASE_KEY environment variables not set. Supabase integration will be disabled.")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    history_from_client = data.get("history", []) # This is the client's view of history
    user_input_content = ""

    if not history_from_client:
        return jsonify({"status": "error", "response": "L'historique de conversation est vide"}), 400

    # Extract the last user message for the graph input
    # The graph itself will manage the full history via the checkpointer
    if history_from_client[-1].get("role", "").lower() == "user":
        user_input_content = history_from_client[-1].get("content", "")
    else: # Should ideally not happen if client sends user message last
        return jsonify({"status": "error", "response": "Dernier message non utilisateur."}), 400

    if not user_input_content:
        return jsonify({"status": "error", "response": "Message utilisateur vide."}), 400

    try:
        if not ALL_MODULES_IMPORTED or invoke_booking_graph is None:
            print("[API_CHAT] Booking graph components not available.")
            # Keep original error message format if desired by user
            return jsonify({"status": "error", "response": "TEST DE DEPLOIEMENT REUSSI - ERREUR PERSISTE."}), 500

        # --- Session ID Management ---
        # Try to get session_id from client, otherwise create/get from Flask session
        session_id = data.get("session_id")
        if not session_id:
            if 'chat_session_id' not in flask_session:
                flask_session['chat_session_id'] = str(uuid.uuid4())
                print(f"[API_CHAT] New Flask session ID generated: {flask_session['chat_session_id']}")
            session_id = flask_session['chat_session_id']
        print(f"[API_CHAT] Using session_id: {session_id}")

        # --- Call the Booking Graph ---
        # The booking_graph's invoke_booking_graph function now handles history and state
        # via its checkpointer, keyed by session_id.
        # We just need to pass the latest user_input.
        graph_response_data = invoke_booking_graph(session_id, user_input_content)

        ai_response_from_graph = graph_response_data.get("ai_response", "Error: No AI response from graph.")

        # --- Supabase Logging (Optional - can be adapted or removed) ---
        # The graph state now contains the full history if needed for logging.
        # For simplicity, logging the current exchange.
        if supabase_client:
            try:
                # Log User Message
                supabase_client.table("conversations").insert({
                    "user_id": session_id, "role": "user", "content": user_input_content
                }).execute()
                # Log Assistant Response
                supabase_client.table("conversations").insert({
                    "user_id": session_id, "role": "assistant", "content": ai_response_from_graph
                }).execute()
                print(f"[API_CHAT] Logged exchange to Supabase for session {session_id}.")
            except Exception as e_log:
                print(f"[API_CHAT] ERROR logging to Supabase for session {session_id}: {e_log}")

        return jsonify({"status": "success", "response": ai_response_from_graph, "session_id": session_id})

    except Exception as e:
        print(f"[API_CHAT] Erreur dans /api/chat: {str(e)}")
        # Match original error message format if it was intentional
        return jsonify({"status": "error", "response": "TEST DE DEPLOIEMENT REUSSI - ERREUR PERSISTE."}), 500


@app.route("/api/lead", methods=["POST"])
def lead():
    # This endpoint remains unchanged as per current plan
    data = request.get_json()
    user_input = data.get("input", "")
    save_flag = data.get("save", False) # From chatbot.js
    try:
        if not ALL_MODULES_IMPORTED or structured_llm is None or collect_lead_from_text is None:
            print("[API_LEAD] Lead processing components not available.")
            # This was returning 500 with specific message, let's keep that pattern
            return jsonify({"status": "error", "response": "Lead processing components not available on server."}), 500


        lead_info = structured_llm.invoke(user_input) # Uses the LLM with structured output for Lead

        # The client-side JS seems to handle partial info well by re-asking.
        # This check might be redundant if client manages it, but good for direct API calls.
        # if not lead_info or not any([lead_info.name, lead_info.email, lead_info.phone]):
             # Return lead_info even if partial, client can check missing fields
             # pass # Let client handle missing fields message

        # The actual saving to Supabase is now inside collect_lead_from_text
        if save_flag and lead_info and all([lead_info.name, lead_info.email, lead_info.phone]):
            print(f"[API_LEAD] Attempting to save lead: {lead_info.model_dump_json()}")
            # collect_lead_from_text will re-extract from text then save.
            # This is inefficient. If lead_info is already extracted, we should use a function that saves the Lead object.
            # For now, to stick to the existing structure, we call collect_lead_from_text.
            # TODO: Refactor collect_lead_from_text to optionally accept a Lead object or create a new save_lead(Lead) function.
            collect_lead_from_text(user_input)

        return jsonify({"status": "success", "lead": lead_info.model_dump() if lead_info else {}})

    except Exception as e:
        print(f"[API_LEAD] Erreur dans /api/lead: {str(e)}")
        return jsonify({"status": "error", "message": f"Erreur lors du traitement des informations de lead: {e}"}), 500

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    is_debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    # Ensure GROQ_API_KEY is available for the booking_graph LLM calls
    if not os.getenv("GROQ_API_KEY"):
        print("[APP_MAIN] WARNING: GROQ_API_KEY environment variable not set. LLM calls in booking_graph may fail.")
    app.run(debug=is_debug, host="0.0.0.0", port=port)