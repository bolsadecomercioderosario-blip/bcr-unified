import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/drive']
PARENT_FOLDER_ID = '1C9NICdm1iQN82kEEF04tRZQuxTAoN0kA'

# Render places secret files in /etc/secrets or the app root
POSSIBLE_DIRS = [
    "/etc/secrets",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), # backend/
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # repo root
]

def find_file(filename):
    for d in POSSIBLE_DIRS:
        path = os.path.join(d, filename)
        if os.path.exists(path):
            return path
    return os.path.join(POSSIBLE_DIRS[1], filename)

CLIENT_SECRETS_FILE = find_file('client_secret.json')
TOKEN_FILE = find_file('token.json')

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Render's /etc/secrets is read-only, so we catch permission errors
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                print(f"No se pudo guardar el token actualizado (probable sistema de solo lectura): {e}")
        else:
            return None # Must go through auth flow first
            
    return build('drive', 'v3', credentials=creds)

def create_activity_folder(date_iso, title):
    """
    Creates a folder in Drive for the given activity.
    Format: "DD/MM - Título"
    Returns the webViewLink of the created folder.
    """
    service = get_drive_service()
    if not service:
        print("No valid Drive credentials found. Skipping folder creation.")
        return ""
    
    # Format the date from YYYY-MM-DD to DD/MM
    try:
        dt = datetime.datetime.strptime(date_iso, '%Y-%m-%d')
        date_str = dt.strftime('%d/%m')
    except Exception:
        date_str = date_iso
        
    folder_name = f"{date_str} - {title}"
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [PARENT_FOLDER_ID]
    }
    
    try:
        file = service.files().create(
            body=file_metadata,
            fields='id, webViewLink'
        ).execute()
        
        folder_id = file.get('id')
        link = file.get('webViewLink')
        
        # Fallback si por alguna razón no viene el webViewLink
        if not link and folder_id:
            link = f"https://drive.google.com/drive/folders/{folder_id}"
            
        print(f"Carpeta creada exitosamente: {folder_id} - Link: {link}")
        return link
    except HttpError as error:
        print(f"Error de Google API al crear carpeta: {error}")
        return ""
    except Exception as e:
        print(f"Error inesperado al crear carpeta en Drive: {e}")
        return ""
