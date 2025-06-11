import os
from flask import Flask, request, jsonify
from whatsapp_webhook import whatsapp
from lead_graph import structured_llm, collect_lead_from_text, llm, Lead
from functools import wraps

app = Flask(__name__)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')

# ---- Middleware ----
def log_requests(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app.logger.info(f"Requête reçue - {request.path} - Données: {request.get_json()}")
        return f(*args, **kwargs)
    return decorated_function

# ---- Routes API ----
@app.route("/api/chat", methods=["POST"])
@log_requests
def chat():
    """Gère les conversations génériques avec le LLM"""
    data = request.get_json()
    history = data.get("history", [])
    
    if not history:
        return jsonify({
            "status": "error",
            "response": "L'historique de conversation est vide"
        }), 400

    try:
        response = llm.invoke({
            "history": history,
            "question": history[-1].get("content", ""),
            "company_name": "TRANSLAB INTERNATIONAL"
        })
        return jsonify({
            "status": "success",
            "response": response.content
        })
    
    except Exception as e:
        app.logger.error(f"Erreur dans /api/chat: {str(e)}")
        return jsonify({
            "status": "error",
            "response": "Désolé, une erreur s'est produite"
        }), 500

@app.route("/api/lead", methods=["POST"])
@log_requests
def lead():
    """Gère l'extraction et l'enregistrement des leads"""
    data = request.get_json()
    user_input = data.get("input", "")
    save_flag = data.get("save", False)

    try:
        lead = structured_llm.invoke(user_input)
        
        if not any([lead.name, lead.email, lead.phone]):
            return jsonify({
                "status": "error",
                "message": "Informations manquantes. Merci de fournir nom, email ou téléphone."
            }), 400

        if save_flag:
            collect_lead_from_text(user_input)
            # Sauvegarde supplémentaire dans Google Drive
            from gdrive_utils import save_lead_to_drive
            save_lead_to_drive(lead)

        return jsonify({
            "status": "success",
            "lead": lead.model_dump()
        })
    
    except Exception as e:
        app.logger.error(f"Erreur dans /api/lead: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Erreur lors du traitement: {e}"
        }), 500

# ---- Health Check ----
@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=os.environ.get("FLASK_DEBUG", False), 
            host="0.0.0.0", 
            port=port)
