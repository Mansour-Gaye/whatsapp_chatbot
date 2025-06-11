import os
from flask import Flask
from whatsapp_webhook import whatsapp

app = Flask(__name__)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # 🔁 important pour Render
    app.run(debug=False, host="0.0.0.0", port=port)
