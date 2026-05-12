"""
Módulo Social (Comunicados): procesa un PDF y genera texto + imagen para X
y un mockup vertical para Instagram Stories. También publica el tweet.
"""
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse

from auth import require_auth
from config import UPLOADS_DIR, ASSETS_DIR
from common import PublicarTwitterRequest, publish_to_twitter
from processor import extract_pdf_data, generate_pdf_thumbnail, create_ig_mockup, to_bold_serif


router = APIRouter(prefix="/api/social", dependencies=[Depends(require_auth)])


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
            "pdf_path": pdf_path,
            "preview_url": f"/static/uploads/{thumb_filename}",
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/generar")
async def generar_social(
    session_id: str = Form(...),
    pdf_path: str = Form(...),
    title: str = Form(...),
):
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
    file_path = os.path.join(UPLOADS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=name, media_type='image/jpeg')
    return {"error": "Archivo no encontrado"}


@router.post("/publicar-twitter")
def publicar_social_twitter(req: PublicarTwitterRequest):
    """Publica el comunicado en @BolsaRosario con la imagen (thumbnail del PDF)."""
    return publish_to_twitter(req.texto, req.imagen_url)
