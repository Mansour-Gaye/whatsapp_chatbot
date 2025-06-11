from google.oauth2 import service_account

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly'
]

def get_credentials():
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not credentials_path or not os.path.exists(credentials_path):
        raise FileNotFoundError("Fichier de credentials du compte de service non trouvé.")
    creds = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return creds


if __name__ == '__main__':
    get_credentials()
