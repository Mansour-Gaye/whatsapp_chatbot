import os
from flask import Flask, request, jsonify
from whatsapp_webhook import whatsapp
# Ensure these can be imported AFTER lead_graph is confirmed to be importable
# We might need to wrap these imports in a try-except too if lead_graph still has issues
# For now, assuming lead_graph will be fine with lazy RAG
try:
    from lead_graph import structured_llm, collect_lead_from_text, llm, Lead
    LEAD_GRAPH_FOR_APP_IMPORTED = True
    print("[APP_INIT] Successfully imported structured_llm, collect_lead_from_text, llm, Lead from lead_graph.")
except ImportError as e:
    print(f"[APP_INIT] ERROR importing from lead_graph for app routes: {e}. API routes for lead/chat might fail.")
    LEAD_GRAPH_FOR_APP_IMPORTED = False
    structured_llm, collect_lead_from_text, llm, Lead = None, None, None, None

from functools import wraps

app = Flask(__name__)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')

def log_requests(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # print(f"[DEBUG] Request: {request.path}, Data: {request.get_json(silent=True)}") 
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/chat", methods=["POST"])
@log_requests
def chat():
    data = request.get_json()
    history = data.get("history", [])
    if not history: return jsonify({"status": "error", "response": "L'historique de conversation est vide"}), 400
    try:
        if not LEAD_GRAPH_FOR_APP_IMPORTED or llm is None: 
            print("[API_CHAT] LLM not available for app route.")
            raise Exception("LLM not configured for chat API")
        response = llm.invoke({"history": history, "question": history[-1].get("content", ""), "company_name": "TRANSLAB INTERNATIONAL"})
        return jsonify({"status": "success", "response": response.content})
    except Exception as e:
        print(f"[API_CHAT] Erreur dans /api/chat: {str(e)}")
        return jsonify({"status": "error", "response": "Désolé, une erreur s'est produite pendant la conversation."}), 500

@app.route("/api/lead", methods=["POST"])
@log_requests
def lead():
    data = request.get_json()
    user_input = data.get("input", "")
    save_flag = data.get("save", False)
    try:
        if not LEAD_GRAPH_FOR_APP_IMPORTED or structured_llm is None or collect_lead_from_text is None: 
            print("[API_LEAD] Lead processing components not available for app route.")
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
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=os.environ.get("FLASK_DEBUG", False), host="0.0.0.0", port=port)
