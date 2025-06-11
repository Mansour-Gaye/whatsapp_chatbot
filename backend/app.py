import os
from flask import Flask
from whatsapp_webhook import whatsapp

app = Flask(__name__)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')
@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    user_input = data.get("input", "")
    try:
        from lead_graph import structured_llm, collect_lead_from_text

        lead = collect_lead_from_text(user_input)

        if not (lead.name and lead.email and lead.phone):
            return jsonify({
                "status": "error",
                "message": "Je n'ai pas bien reçu votre nom, email ou téléphone. Pouvez-vous reformuler ?"
            }), 400

        return jsonify({"status": "ok", "lead": lead.model_dump()})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erreur serveur : {e}"}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # 🔁 important pour Render
    app.run(debug=False, host="0.0.0.0", port=port)
