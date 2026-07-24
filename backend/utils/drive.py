import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    # YouTube: subir videos, setear thumbnail, agregar a playlists
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube',
]
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
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            # token.json presente pero malformado/ilegible.
            print(f"token.json inválido o malformado: {e}")
            return None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                # Token revocado o vencido: hay que reautorizar (reauth_google.py).
                print(f"No se pudo refrescar el token de Google Drive (¿revocado/vencido?): {e}")
                return None
            # Render's /etc/secrets is read-only, so we catch permission errors
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                print(f"No se pudo guardar el token actualizado (probable sistema de solo lectura): {e}")
        else:
            return None  # Must go through auth flow first

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

def trash_drive_folder(url):
    """
    Envía a la PAPELERA de Drive la carpeta dada por su webViewLink (NO la borra
    definitivamente). Queda recuperable ~30 días desde la papelera de Drive.
    Extrae el ID de la URL y la marca como `trashed`.
    """
    if not url or "drive.google.com" not in url:
        return

    service = get_drive_service()
    if not service:
        return

    try:
        # Extraer ID de la URL
        # Soporta formatos: /folders/ID o ?id=ID
        folder_id = None
        if 'folders/' in url:
            folder_id = url.split('folders/')[-1].split('?')[0]
        elif 'id=' in url:
            folder_id = url.split('id=')[-1].split('&')[0]

        if folder_id:
            service.files().update(fileId=folder_id, body={"trashed": True}).execute()
            print(f"Carpeta de Drive enviada a la papelera: {folder_id}")
    except Exception as e:
        print(f"Error al enviar a la papelera la carpeta de Drive ({url}): {e}")
