from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import json
import os

# Les scopes dont tu as besoin
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
]

def get_credentials():
    creds = None
    token_path = 'backend/token.json'
    
    # Vérifie si le token existe déjà
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # Si pas de token valide, on utilise les credentials
    if not creds or not creds.valid:
        if os.path.exists('backend/credentials.json'):
            flow = InstalledAppFlow.from_client_secrets_file(
                'backend/credentials.json',
                SCOPES
            )
            creds = flow.run_local_server(port=0)
            
            # Sauvegarde les credentials dans un nouveau fichier
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            
            print("✅ Token généré avec succès !")
        else:
            raise FileNotFoundError("Le fichier credentials.json est manquant dans le dossier backend")
    
    return creds

if __name__ == '__main__':
    get_credentials()
