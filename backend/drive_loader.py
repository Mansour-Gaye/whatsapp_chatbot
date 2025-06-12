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

    def get_file_content(self, file_id: str) -> str:
        """Récupère le contenu d'un fichier Google Drive."""
        try:
            # Vérifier si c'est un dossier
            file_metadata = self.service.files().get(fileId=file_id, fields='mimeType').execute()
            mime_type = file_metadata.get('mimeType', '')
            
            if mime_type == 'application/vnd.google-apps.folder':
                # Si c'est un dossier, lister et récupérer le contenu de tous les fichiers
                results = self.service.files().list(
                    q=f"'{file_id}' in parents and trashed=false",
                    fields="files(id, name, mimeType)"
                ).execute()
                files = results.get('files', [])
                
                if not files:
                    logger.warning(f"Aucun fichier trouvé dans le dossier {file_id}")
                    return ""
                
                content = []
                for file in files:
                    file_content = self.get_file_content(file['id'])
                    if file_content:
                        content.append(f"=== {file['name']} ===\n{file_content}\n")
                
                return "\n".join(content)
            
            # Si c'est un document Google (Docs, Sheets, etc.)
            elif mime_type.startswith('application/vnd.google-apps.'):
                request = self.service.files().export_media(
                    fileId=file_id,
                    mimeType='text/plain'
                )
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                return fh.getvalue().decode('utf-8', errors='replace')
            
            # Si c'est un fichier normal
            else:
                request = self.service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                
                # Essayer différents encodages
                content = fh.getvalue()
                encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
                
                for encoding in encodings:
                    try:
                        return content.decode(encoding)
                    except UnicodeDecodeError:
                        continue
                
                # Si aucun encodage ne fonctionne, utiliser 'replace' pour ignorer les caractères problématiques
                return content.decode('utf-8', errors='replace')
                
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du fichier {file_id}: {e}")
            return ""

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