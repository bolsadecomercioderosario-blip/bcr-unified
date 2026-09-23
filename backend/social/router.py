"""
Módulo Social (Comunicados): procesa un PDF y genera texto + imagen para X
y un mockup vertical para Instagram Stories. También publica el tweet.
"""
import os
import re
import shutil
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

# session_id seguro: sólo lo que genera pre-procesar (uuid) — evita que el
# cliente mande un path/`..` para que el server abra un archivo arbitrario.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

from auth import require_roles, ROLE_COMUNICACION
from config import UPLOADS_DIR, ASSETS_DIR
from common import PublicarTwitterRequest, publish_to_twitter, require_external_integrations
from processor import extract_pdf_data, generate_pdf_thumbnail, create_ig_mockup, to_bold_serif


router = APIRouter(prefix="/api/social", dependencies=[Depends(require_roles(ROLE_COMUNICACION))])


@router.post("/pre-procesar")
async def pre_procesar(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    pdf_path = os.path.join(UPLOADS_DIR, f"{session_id}_pre.pdf")
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    try:
        data = extract_pdf_data(pdf_path)
        thumb_filename = f"pre_{session_id}.jpg"
        thumb_path = os.path.join(UPLOADS_DIR, thumb_filename)
        generate_pdf_thumbnail(pdf_path, thumb_path)

        return {
            "session_id": session_id,
            "title": data["title"],
            "preview_url": f"/static/uploads/{thumb_filename}",
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/generar")
async def generar_social(
    session_id: str = Form(...),
    title: str = Form(...),
):
    # El path del PDF NO se recibe del cliente: se reconstruye server-side desde
    # el session_id (que pre-procesar generó). Antes venía como Form y se abría
    # tal cual → un cliente podía apuntar a cualquier archivo del server.
    if not _SAFE_ID.match(session_id or ""):
        raise HTTPException(status_code=400, detail="session_id inválido")
    pdf_path = os.path.join(UPLOADS_DIR, f"{session_id}_pre.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Sesión no encontrada. Volvé a subir el PDF.")
    try:
        data = extract_pdf_data(pdf_path)
        data["title"] = title

        twitter_text = f"{to_bold_serif(data['title'])}\n\n{data['intro']}"

        thumb_filename = f"comunicado_{session_id}.jpg"
        thumb_path = os.path.join(UPLOADS_DIR, thumb_filename)
        generate_pdf_thumbnail(pdf_path, thumb_path)

        story_filename = f"story_instagram_{session_id}.jpg"
        story_path = os.path.join(UPLOADS_DIR, story_filename)
        create_ig_mockup(data, thumb_path, ASSETS_DIR, story_path)

        return {
            "twitter_text": twitter_text,
            "comunicado_url": f"/api/social/descargar/{thumb_filename}?name=comunicado.jpg",
            "story_url": f"/api/social/descargar/{story_filename}?name=story_instagram.jpg",
            "comunicado_img": f"/static/uploads/{thumb_filename}",
            "story_img": f"/static/uploads/{story_filename}",
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/descargar/{filename}")
async def descargar(filename: str, name: str):
    filename = os.path.basename(filename)  # nunca salir de UPLOADS_DIR
    file_path = os.path.join(UPLOADS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=name, media_type='image/jpeg')
    return {"error": "Archivo no encontrado"}


@router.post("/publicar-twitter")
def publicar_social_twitter(req: PublicarTwitterRequest):
    """Publica el comunicado en @BolsaRosario con la imagen (thumbnail del PDF)."""
    require_external_integrations()
    return publish_to_twitter(req.texto, req.imagen_url)
