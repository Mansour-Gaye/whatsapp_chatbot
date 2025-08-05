from google.oauth2 import service_account
import os
import logging

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/drive.file',
]

def get_credentials():
    credentials_path = '/etc/secrets/credentials.json'
    if not os.path.exists(credentials_path):
        logging.warning(f"[CREDENTIALS] Fichier non trouvé à {credentials_path}, tentative fallback .env ou local.")
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'service_account.json')
    if not os.path.exists(credentials_path):
        logging.error(f"[CREDENTIALS] Fichier de credentials introuvable à {credentials_path}")
        raise FileNotFoundError(f"Fichier de credentials introuvable à {credentials_path}")
    logging.info(f"[CREDENTIALS] Utilisation du fichier credentials: {credentials_path}")
    return service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
