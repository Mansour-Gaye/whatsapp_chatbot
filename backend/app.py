import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from whatsapp_webhook import whatsapp
from functools import wraps

# --- Section d'importation des modules de traitement ---
# On utilise un bloc try-except pour gérer les erreurs si les modules ne sont pas trouvés
try:
    from lead_graph import structured_llm, collect_lead_from_text, llm, Lead
    from langchain_core.messages import HumanMessage, AIMessage # Ajout crucial pour la conversion de l'historique
    LEAD_GRAPH_FOR_APP_IMPORTED = True
    print("[APP_INIT] Successfully imported all necessary modules.")
except ImportError as e:
    print(f"[APP_INIT] ERROR importing modules: {e}. API routes might fail.")
    LEAD_GRAPH_FOR_APP_IMPORTED = False
    # On définit les variables à None pour éviter des erreurs si l'import échoue
    structured_llm, collect_lead_from_text, llm, Lead, HumanMessage, AIMessage = None, None, None, None, None, None

app = Flask(__name__)
CORS(app)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')

def log_requests(f):
    """Un décorateur simple pour logger les requêtes (désactivé par défaut)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Décommentez la ligne suivante pour un débogage détaillé dans les logs
        # print(f"[DEBUG] Request to {request.path}: {request.get_json(silent=True)}")
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/chat", methods=["POST"])
@log_requests
def chat():
    data = request.get_json()
    history = data.get("history", [])  # 'history' est une liste de dictionnaires
    if not history:
        return jsonify({"status": "error", "response": "L'historique de conversation est vide"}), 400

    try:
        if not LEAD_GRAPH_FOR_APP_IMPORTED or llm is None or HumanMessage is None:
            print("[API_CHAT] LLM or message components not available.")
            raise Exception("LLM not configured for chat API")

        # --- Transformation de l'historique pour être compatible avec LangChain ---
        processed_history = []
        for msg_data in history:
            role = msg_data.get("role", "").lower()
            content = msg_data.get("content", "")
            if role == "user":
                processed_history.append(HumanMessage(content=content))
            elif role in ("assistant", "ai"):
                processed_history.append(AIMessage(content=content))
        # --- Fin de la transformation ---

        # La question est le contenu du dernier message de l'historique initial
        question = history[-1].get("content", "") if history else ""

        # On utilise l'historique traité ('processed_history') dans l'appel au modèle
        
           
            
           
       
        print(f"[API_CHAT_DEBUG] Type of processed_history: {type(processed_history)}")
            if processed_history:
        print(f"[API_CHAT_DEBUG] Type of first element in processed_history: {type(processed_history[0])}")
        print(f"[API_CHAT_DEBUG] Content of processed_history: {processed_history}")
            else:
        print("[API_CHAT_DEBUG] processed_history is empty.")

        print(f"[API_CHAT_DEBUG] Value of question: {question}")
        print(f"[API_CHAT_DEBUG] Type of question: {type(question)}")
        response = llm.invoke({
             "history": processed_history,
             "question": question,
             "company_name": "TRANSLAB INTERNATIONAL"
             })
        return jsonify({"status": "success", "response": response.content})

    except Exception as e:
        # Cette ligne est la plus importante pour le débogage : elle affichera l'erreur exacte dans vos logs Render
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
        return jsonify({"status": "error", "response": "TEST DE DEPLOIEMENT REUSSI - ERREUR PERSISTE."}), 500

@app.route("/health")
def health():
    """Route pour vérifier que le service est en ligne."""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # Le mode debug doit être désactivé en production
    is_debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=is_debug, host="0.0.0.0", port=port)


