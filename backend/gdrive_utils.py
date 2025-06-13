# gdrive_utils.py
from googleapiclient.discovery import build
from get_credentials import get_credentials

from typing import List
from langchain_core.documents import Document
import os

def get_drive_service():
    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds)
    return service

class DriveLoader:
    """Classe pour charger les documents depuis Google Drive."""
    
    def __init__(self):
        """Initialise le loader avec le service Google Drive."""
        self.service = get_drive_service()
        self.doc_id = os.getenv('GOOGLE_DRIVE_DOC_ID')
        if not self.doc_id:
            raise ValueError("GOOGLE_DRIVE_DOC_ID doit être défini dans l'environnement")
    
    def load(self) -> List[Document]:
        """Charge le contenu du document depuis Google Drive.
        
        Returns:
            Liste de documents Langchain
        """
        try:
            # Récupérer le contenu du fichier
            file = self.service.files().get(
                fileId=self.doc_id,
                fields='id, name, mimeType'
            ).execute()
            
            if file['mimeType'] != 'application/vnd.google-apps.document':
                raise ValueError(f"Le fichier doit être un Google Doc, pas {file['mimeType']}")
            
            # Récupérer le contenu en format texte
            content = self.service.files().export(
                fileId=self.doc_id,
                mimeType='text/plain'
            ).execute()
            
            # Créer un document Langchain
            return [Document(
                page_content=content.decode('utf-8'),
                metadata={
                    'source': f"Google Drive - {file['name']}",
                    'file_id': self.doc_id
                }
            )]
            
        except Exception as e:
            print(f"Erreur lors du chargement du document: {str(e)}")
            return []
