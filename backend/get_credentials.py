from google.oauth2 import service_account
import os

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
    'https://www.googleapis.com/auth/drive.file',
]

def get_credentials():
    # Chemin Render standard pour les secrets
    credentials_path = '/etc/secrets/credentials.json'
    
    # Fallback pour le développement local
    if not os.path.exists(credentials_path):
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
    
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"Fichier de credentials introuvable à {credentials_path}")
    
    return service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
