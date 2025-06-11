from flask import Flask
from whatsapp_webhook import whatsapp

app = Flask(__name__)
app.register_blueprint(whatsapp, url_prefix='/whatsapp')

if __name__ == '__main__':
    app.run(debug=True)
