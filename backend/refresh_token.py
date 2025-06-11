from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import json
import logging
from datetime import datetime, timedelta

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
]

def is_token_expired(creds):
    """Vérifie si le token est expiré ou va bientôt expirer"""
    if not creds or not creds.valid:
        return True
    if creds.expiry:
        # Rafraîchir si le token expire dans moins de 5 minutes
        return creds.expiry - datetime.utcnow() < timedelta(minutes=5)
    return False

def refresh_token():
    """Rafraîchit le token Google et gère les erreurs"""
    creds = None
    token_path = 'token.json'
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Vérifier si le token existe
            if os.path.exists(token_path):
                try:
                    creds = Credentials.from_authorized_user_info(
                        json.loads(open(token_path).read()), SCOPES)
                except Exception as e:
                    logger.error(f"Erreur lors du chargement du token : {e}")
                    creds = None

            # Si pas de credentials valides ou expirés, rafraîchir
            if not creds or is_token_expired(creds):
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        logger.error(f"Erreur lors du rafraîchissement du token : {e}")
                        creds = None
                
                if not creds:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Sauvegarder les credentials
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"✅ Nouveau token sauvegardé dans {token_path}")
                return creds

            return creds

        except Exception as e:
            retry_count += 1
            logger.error(f"Tentative {retry_count}/{max_retries} échouée : {e}")
            if retry_count == max_retries:
                logger.error("Échec du rafraîchissement du token après plusieurs tentatives")
                raise

def ensure_valid_token():
    """Fonction à appeler avant chaque opération nécessitant l'authentification"""
    try:
        return refresh_token()
    except Exception as e:
        logger.error(f"Impossible d'obtenir un token valide : {e}")
        raise

if __name__ == '__main__':
    ensure_valid_token() 