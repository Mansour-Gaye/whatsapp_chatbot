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
    
    def find_first_doc(self, folder_id: str) -> str:
        """Trouve le premier document Google Doc dans un dossier.
        
        Args:
            folder_id: ID du dossier Google Drive
            
        Returns:
            ID du premier document Google Doc trouvé
        """
        try:
            # Rechercher les fichiers dans le dossier
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'",
                pageSize=1,
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            if not files:
                raise ValueError(f"Aucun document Google Doc trouvé dans le dossier {folder_id}")
                
            return files[0]['id']
            
        except Exception as e:
            print(f"Erreur lors de la recherche du document: {str(e)}")
            return None
    
    def load(self) -> List[Document]:
        """Charge le contenu du document depuis Google Drive.
        
        Returns:
            Liste de documents Langchain
        """
        try:
            # Vérifier si l'ID est un dossier
            file = self.service.files().get(
                fileId=self.doc_id,
                fields='id, name, mimeType'
            ).execute()
            
            # Si c'est un dossier, chercher le premier document
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                print(f"L'ID {self.doc_id} est un dossier, recherche du premier document...")
                doc_id = self.find_first_doc(self.doc_id)
                if not doc_id:
                    raise ValueError("Aucun document Google Doc trouvé dans le dossier")
                file = self.service.files().get(
                    fileId=doc_id,
                    fields='id, name, mimeType'
                ).execute()
            
            if file['mimeType'] != 'application/vnd.google-apps.document':
                raise ValueError(f"Le fichier doit être un Google Doc, pas {file['mimeType']}")
            
            # Récupérer le contenu en format texte
            content = self.service.files().export(
                fileId=file['id'],
                mimeType='text/plain'
            ).execute()
            
            # Créer un document Langchain
            return [Document(
                page_content=content.decode('utf-8'),
                metadata={
                    'source': f"Google Drive - {file['name']}",
                    'file_id': file['id']
                }
            )]
            
        except Exception as e:
            print(f"Erreur lors du chargement du document: {str(e)}")
            return []
