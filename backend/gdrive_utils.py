# gdrive_utils.py
from googleapiclient.discovery import build
from get_credentials import get_credentials  # Importez votre fonction existante

def get_drive_service():
    creds = get_credentials()  # Utilise la fonction qui charge les credentials depuis Render
    service = build('drive', 'v3', credentials=creds)
    return service
