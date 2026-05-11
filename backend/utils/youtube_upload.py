"""
Descarga de archivos de Google Drive y upload a YouTube.

El flujo completo (ver upload_program_to_youtube) hace:
  1. Descarga el archivo de Drive a un archivo temporal en disco.
  2. Sube el video a YouTube con título, descripción y status=public.
  3. Setea el thumbnail (la portada generada por semana_datos.py).
  4. Agrega el video a la playlist de "La Semana en Datos".
  5. Borra el temporal.

Reutiliza las credenciales de Google OAuth ya configuradas para Drive
(con scopes ampliados a youtube.upload + youtube). Ver utils/drive.py.
"""
import io
import os
import re
import tempfile
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

from utils.drive import SCOPES, TOKEN_FILE


# Playlist "La Semana en Datos"
SEMANA_DATOS_PLAYLIST_ID = "PLwvqUh9Mo3Ql2Z2WvnQpUoA3CAeVuiHl5"

# YouTube acepta thumbnails hasta 2 MB
THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# Auth — credenciales compartidas con Drive
# ---------------------------------------------------------------------------

def _get_credentials() -> Optional[Credentials]:
    if not os.path.exists(TOKEN_FILE):
        return None
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            try:
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
            except Exception:
                pass  # Render /etc/secrets es read-only
        else:
            return None
    return creds


def _get_drive_service():
    creds = _get_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)


def _get_youtube_service():
    creds = _get_credentials()
    if not creds:
        return None
    return build("youtube", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Drive — extracción de ID y descarga
# ---------------------------------------------------------------------------

DRIVE_FILE_PATTERNS = [
    re.compile(r"/file/d/([a-zA-Z0-9_-]+)"),          # /file/d/{id}/view
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),           # ?id={id}
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),          # folder (no debería pasar, pero por las dudas)
]


def extract_drive_file_id(url_or_id: str) -> Optional[str]:
    """Acepta una URL completa de Drive o un ID pelado. Devuelve el ID."""
    if not url_or_id:
        return None
    s = url_or_id.strip()
    # Si parece un ID directo (no es URL), devolverlo
    if "/" not in s and "?" not in s and len(s) >= 20:
        return s
    for pattern in DRIVE_FILE_PATTERNS:
        m = pattern.search(s)
        if m:
            return m.group(1)
    return None


def get_drive_file_metadata(file_id: str) -> dict:
    """Devuelve metadata básica del archivo (name, size, mimeType)."""
    service = _get_drive_service()
    if not service:
        raise RuntimeError("Drive credentials missing or invalid")
    return service.files().get(
        fileId=file_id, fields="id, name, size, mimeType"
    ).execute()


def download_drive_file(file_id: str, dest_path: str, progress_cb=None) -> None:
    """Descarga un archivo de Drive a `dest_path`.
    progress_cb opcional: recibe (bytes_downloaded, total_bytes_or_None)."""
    service = _get_drive_service()
    if not service:
        raise RuntimeError("Drive credentials missing or invalid")

    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request, chunksize=10 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if progress_cb and status:
                progress_cb(status.resumable_progress, status.total_size)


# ---------------------------------------------------------------------------
# Thumbnail — comprimir si supera el límite de YouTube
# ---------------------------------------------------------------------------

def thumbnail_for_youtube(png_bytes: bytes) -> tuple[bytes, str]:
    """YouTube acepta thumbnails ≤ 2 MB. Si el PNG es más grande, lo
    convierte a JPEG con calidad razonable. Retorna (bytes, mimetype)."""
    if len(png_bytes) <= THUMBNAIL_MAX_BYTES:
        return png_bytes, "image/png"

    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    # Bajar calidad hasta que entre
    for quality in (92, 88, 84, 80, 75, 70, 65):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= THUMBNAIL_MAX_BYTES:
            return buf.getvalue(), "image/jpeg"
    # Último recurso: peor calidad
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60, optimize=True)
    return buf.getvalue(), "image/jpeg"


# ---------------------------------------------------------------------------
# YouTube — upload + thumbnail + playlist
# ---------------------------------------------------------------------------

def upload_video_to_youtube(
    video_path: str,
    title: str,
    description: str,
    thumbnail_bytes: bytes,
    privacy: str = "public",
    playlist_id: Optional[str] = SEMANA_DATOS_PLAYLIST_ID,
    category_id: str = "25",  # 25 = News & Politics; podríamos usar 28 (Science) o 22 (People)
) -> dict:
    """Sube un video a YouTube + setea thumbnail + agrega a playlist.

    Returns:
        dict con {video_id, url, playlist_added}
    Raises:
        RuntimeError si la auth falla.
        HttpError si la API devuelve error.
    """
    service = _get_youtube_service()
    if not service:
        raise RuntimeError("YouTube credentials missing or invalid")

    # 1) Upload del video (resumable)
    body = {
        "snippet": {
            "title": title[:100],  # YouTube hard-limit a 100 chars
            "description": description[:5000],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    video_id = response["id"]

    # 2) Thumbnail
    try:
        thumb, mime = thumbnail_for_youtube(thumbnail_bytes)
        thumb_media = MediaIoBaseUpload(io.BytesIO(thumb), mimetype=mime, resumable=False)
        service.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
    except HttpError as e:
        # Si falla el thumbnail (cuenta no verificada, etc.) seguimos con default
        print(f"Warning: no se pudo setear thumbnail: {e}")

    # 3) Agregar a playlist
    playlist_added = False
    if playlist_id:
        try:
            service.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
            playlist_added = True
        except HttpError as e:
            print(f"Warning: no se pudo agregar a playlist {playlist_id}: {e}")

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "playlist_added": playlist_added,
    }


# ---------------------------------------------------------------------------
# Flujo combinado: Drive → YouTube
# ---------------------------------------------------------------------------

def upload_program_to_youtube(
    drive_file_id: str,
    title: str,
    description: str,
    thumbnail_bytes: bytes,
    privacy: str = "public",
    playlist_id: Optional[str] = SEMANA_DATOS_PLAYLIST_ID,
) -> dict:
    """Descarga el archivo de Drive a un temp file y lo sube a YouTube.
    El temp file se borra siempre, incluso si falla el upload."""
    # Validar metadata antes de descargar (te avisa rápido si la URL es errada)
    meta = get_drive_file_metadata(drive_file_id)
    name = meta.get("name", "video.mp4")
    mime = meta.get("mimeType", "")
    if not mime.startswith("video/"):
        raise ValueError(f"El archivo de Drive no es un video (mimeType: {mime})")

    suffix = os.path.splitext(name)[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    tmp.close()

    try:
        download_drive_file(drive_file_id, tmp_path)
        result = upload_video_to_youtube(
            video_path=tmp_path,
            title=title,
            description=description,
            thumbnail_bytes=thumbnail_bytes,
            privacy=privacy,
            playlist_id=playlist_id,
        )
        result["drive_file_name"] = name
        return result
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
