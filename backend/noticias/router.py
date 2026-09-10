"""
Módulo Noticias — Más BCR.

Dos routers:
  - `router`  (/api/noticias)  → API JSON del ADMIN (CRUD + subir imágenes), con auth.
  - `site`    (/noticias/...)  → sitio PÚBLICO server-rendered (SEO), sin auth.

El admin (SPA) vive en static/noticias/admin.html y se sirve desde app.py.
"""
from __future__ import annotations

import os
import re
import shutil
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Optional

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import require_auth
from config import CLOUDINARY_ENABLED, UPLOADS_DIR
from database import get_db
from noticias import render
from noticias.models import CATEGORIAS, Noticia, NoticiaIn


# ===========================================================================
# Helpers
# ===========================================================================
def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:80] or "nota"


def _unique_slug(db: Session, base: str, exclude_id: Optional[int] = None) -> str:
    slug = base
    i = 2
    while True:
        q = db.query(Noticia).filter(Noticia.slug == slug)
        if exclude_id is not None:
            q = q.filter(Noticia.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{i}"
        i += 1


def _to_dict(n: Noticia) -> dict[str, Any]:
    return {
        "id": n.id, "slug": n.slug, "titulo": n.titulo, "bajada": n.bajada,
        "cuerpo": n.cuerpo, "imagen_portada": n.imagen_portada, "categoria": n.categoria,
        "estado": n.estado,
        "fecha_pub": n.fecha_pub.isoformat() if n.fecha_pub else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


# ===========================================================================
# API del admin (con auth)
# ===========================================================================
router = APIRouter(prefix="/api/noticias", dependencies=[Depends(require_auth)])


@router.get("")
def listar_admin(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Todas las notas (incluye borradores), más recientes primero."""
    rows = db.query(Noticia).order_by(Noticia.created_at.desc()).all()
    return {"categorias": CATEGORIAS, "noticias": [_to_dict(n) for n in rows]}


@router.get("/{nid}")
def obtener(nid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.query(Noticia).filter(Noticia.id == nid).first()
    if n is None:
        raise HTTPException(404, "Noticia no encontrada")
    return _to_dict(n)


@router.post("")
def crear(payload: NoticiaIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not payload.titulo.strip():
        raise HTTPException(400, "El título es obligatorio")
    n = Noticia(
        slug=_unique_slug(db, _slugify(payload.titulo)),
        titulo=payload.titulo.strip(),
        bajada=payload.bajada,
        cuerpo=payload.cuerpo,
        imagen_portada=payload.imagen_portada,
        categoria=payload.categoria,
        estado=payload.estado or "borrador",
    )
    if n.estado == "publicado":
        n.fecha_pub = datetime.utcnow()
    db.add(n)
    db.commit()
    db.refresh(n)
    return _to_dict(n)


@router.put("/{nid}")
def actualizar(nid: int, payload: NoticiaIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.query(Noticia).filter(Noticia.id == nid).first()
    if n is None:
        raise HTTPException(404, "Noticia no encontrada")
    n.titulo = payload.titulo.strip() or n.titulo
    n.bajada = payload.bajada
    n.cuerpo = payload.cuerpo
    n.imagen_portada = payload.imagen_portada
    n.categoria = payload.categoria
    # El slug se mantiene estable (SEO). Sólo cambia el estado/fecha.
    nuevo_estado = payload.estado or n.estado
    if nuevo_estado == "publicado" and n.fecha_pub is None:
        n.fecha_pub = datetime.utcnow()  # primera publicación
    n.estado = nuevo_estado
    db.commit()
    db.refresh(n)
    return _to_dict(n)


@router.delete("/{nid}")
def borrar(nid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.query(Noticia).filter(Noticia.id == nid).first()
    if n is None:
        raise HTTPException(404, "Noticia no encontrada")
    db.delete(n)
    db.commit()
    return {"ok": True}


_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@router.post("/upload")
async def subir_imagen(file: UploadFile = File(...)) -> dict[str, Any]:
    """Sube una imagen (portada o dentro del cuerpo) a Cloudinary; fallback local."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _IMG_EXT:
        raise HTTPException(400, "Formato no permitido. Subí JPG, PNG, WEBP o GIF.")

    if CLOUDINARY_ENABLED:
        try:
            result = cloudinary.uploader.upload(
                file.file, folder="masbcr-noticias", resource_type="image",
                use_filename=True, unique_filename=True,
            )
            if result.get("secure_url"):
                return {"url": result["secure_url"]}
        except Exception as e:  # noqa: BLE001
            print(f"Error subiendo imagen noticia a Cloudinary, fallback local: {e}")
            try:
                file.file.seek(0)
            except Exception:
                pass

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    filename = f"noticia_{uuid.uuid4()}{ext}"
    with open(os.path.join(UPLOADS_DIR, filename), "wb") as buf:
        shutil.copyfileobj(file.file, buf)
    return {"url": f"/static/uploads/{filename}"}


# ===========================================================================
# Sitio público (server-rendered, sin auth)
# ===========================================================================
site = APIRouter()


def _canonical(request: Request, path: str) -> str:
    return str(request.base_url).rstrip("/") + path


@site.get("/noticias", include_in_schema=False)
async def home_redirect():
    return RedirectResponse(url="/noticias/", status_code=307)


@site.get("/noticias/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(Noticia).filter(Noticia.estado == "publicado")
        .order_by(Noticia.fecha_pub.desc()).limit(13).all()
    )
    title, body = render.render_home(rows)
    html = render.base_page(
        title=title,
        description="Agencia de noticias de la Bolsa de Comercio de Rosario.",
        body=body,
        canonical=_canonical(request, "/noticias/"),
        og_image=rows[0].imagen_portada if rows else None,
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})


@site.get("/noticias/nota/{slug}", response_class=HTMLResponse)
async def nota(slug: str, request: Request, db: Session = Depends(get_db)):
    n = db.query(Noticia).filter(Noticia.slug == slug, Noticia.estado == "publicado").first()
    if n is None:
        raise HTTPException(404, "Nota no encontrada")
    relacionadas = (
        db.query(Noticia)
        .filter(Noticia.estado == "publicado", Noticia.id != n.id)
        .order_by(Noticia.fecha_pub.desc()).limit(5).all()
    )
    canonical = _canonical(request, f"/noticias/nota/{n.slug}")
    body = render.render_article(n, relacionadas, canonical)
    html = render.base_page(
        title=f"{n.titulo} — Más BCR",
        description=(n.bajada or n.titulo)[:200],
        body=body,
        canonical=canonical,
        og_image=n.imagen_portada,
        og_type="article",
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})


@site.get("/noticias/categoria/{categoria}", response_class=HTMLResponse)
async def categoria(categoria: str, request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(Noticia)
        .filter(Noticia.estado == "publicado", Noticia.categoria == categoria)
        .order_by(Noticia.fecha_pub.desc()).limit(60).all()
    )
    body = render.render_lista(categoria, rows)
    html = render.base_page(
        title=f"{categoria} — Más BCR",
        description=f"Noticias de {categoria} — Bolsa de Comercio de Rosario.",
        body=body,
        canonical=_canonical(request, f"/noticias/categoria/{categoria}"),
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})
