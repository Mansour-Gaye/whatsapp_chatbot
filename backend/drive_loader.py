from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import os
from typing import Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DriveLoader:
    def __init__(self, credentials_path: str):
        """Initialise le chargeur de documents Google Drive.
        
        Args:
            credentials_path: Chemin vers le fichier de credentials JSON
        """
        self.credentials_path = credentials_path
        self.service = None
        self._initialize_service()

    def _initialize_service(self):
        """Initialise le service Google Drive."""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            self.service = build('drive', 'v3', credentials=credentials)
            logger.info("Service Google Drive initialisé avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du service: {str(e)}")
            raise

    def get_file_content(self, file_id: str) -> Optional[str]:
        """Récupère le contenu d'un fichier Google Drive.
        
        Args:
            file_id: ID du fichier Google Drive
            
        Returns:
            Contenu du fichier en texte ou None si erreur
        """
        try:
            # Vérifier d'abord si le fichier existe et est accessible
            file = self.service.files().get(fileId=file_id, fields='id, name, mimeType').execute()
            logger.info(f"Fichier trouvé: {file.get('name')} ({file.get('mimeType')})")

            # Télécharger le contenu
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.info(f"Téléchargement: {int(status.progress() * 100)}%")

            # Convertir en texte
            content = fh.getvalue().decode('utf-8')
            logger.info(f"Contenu récupéré avec succès ({len(content)} caractères)")
            return content

        except Exception as e:
            logger.error(f"Erreur lors de la récupération du fichier {file_id}: {str(e)}")
            return None

    def list_files_in_folder(self, folder_id: str) -> List[dict]:
        """Liste les fichiers dans un dossier Google Drive.
        
        Args:
            folder_id: ID du dossier Google Drive
            
        Returns:
            Liste des fichiers avec leurs métadonnées
        """
        try:
            results = self.service.files().list(
                q=f"'{folder_id}' in parents",
                fields="files(id, name, mimeType)",
                pageSize=100
            ).execute()
            
            files = results.get('files', [])
            logger.info(f"Trouvé {len(files)} fichiers dans le dossier {folder_id}")
            return files

        except Exception as e:
            logger.error(f"Erreur lors de la liste des fichiers du dossier {folder_id}: {str(e)}")
            return []

def get_drive_loader() -> Optional[DriveLoader]:
    """Crée une instance de DriveLoader avec les credentials configurés.
    
    Returns:
        Instance de DriveLoader ou None si erreur
    """
    try:
        creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not creds_path:
            logger.error("GOOGLE_APPLICATION_CREDENTIALS non configuré")
            return None
            
        if not os.path.exists(creds_path):
            logger.error(f"Fichier de credentials non trouvé: {creds_path}")
            return None
            
        return DriveLoader(creds_path)
    except Exception as e:
        logger.error(f"Erreur lors de la création du DriveLoader: {str(e)}")
        return None 