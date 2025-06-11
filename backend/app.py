import os
from flask import Flask, request, jsonify
from whatsapp_webhook import whatsapp
from lead_graph import structured_llm, collect_lead_from_text

app = Flask(__name__)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    history = data.get("history", [])
    if not history:
        return jsonify({"response": "Désolé, je n'ai pas compris votre message."})
    try:
        from lead_graph import llm
        response = llm.invoke(history)
        return jsonify({"response": response.content})
    except Exception as e:
        return jsonify({"response": f"Erreur serveur : {e}"})

@app.route("/api/lead", methods=["POST"])
def lead():
    data = request.get_json()
    user_input = data.get("input", "")
    save_flag = data.get("save", False)

    try:
        lead = structured_llm.invoke(user_input)
        if not (lead.name or lead.email or lead.phone):
            return jsonify({
                "status": "error",
                "message": "Je n’ai pas bien compris vos informations. Pouvez-vous reformuler ?"
            }), 400

        if save_flag:
            collect_lead_from_text(user_input)

        return jsonify({"status": "ok", "lead": lead.model_dump()})
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de l’enregistrement : {e}"
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
