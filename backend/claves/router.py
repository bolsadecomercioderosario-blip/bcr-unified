"""
Router del módulo "Claves — recortes" (Fase C).

Endpoints de EQUIPO (rol Comunicación, vía auth.js):
  GET  /api/claves/programas              → programas + candidatos + estado de renders
  POST /api/claves/render                 → pide generar un recorte (crea pedido)

Endpoints de WORKER (la PC local; auth por header X-Claves-Worker):
  POST /api/claves/worker/publish         → publica/actualiza un programa + candidatos
  GET  /api/claves/worker/pending         → toma pedidos pendientes (los marca 'procesando')
  POST /api/claves/worker/done            → marca un pedido 'listo' con la URL del MP4
  POST /api/claves/worker/error           → marca un pedido 'error'

El worker corre en la PC de Comunicación: descarga, transcribe, renderiza y sube
el MP4 a Cloudinary; Render solo guarda estado y sirve la UI.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_roles, get_actor, Actor, ROLE_COMUNICACION
from database import get_db

from .models import ClavesPrograma, ClavesRender


router = APIRouter(prefix="/api/claves", tags=["claves"])


# --- Auth del worker local --------------------------------------------------
# Fail-closed: si no está seteado CLAVES_WORKER_TOKEN en el entorno, los
# endpoints del worker quedan deshabilitados (503). Nunca un default adivinable.
_WORKER_TOKEN = os.environ.get("CLAVES_WORKER_TOKEN", "")


def require_worker(x_claves_worker: Optional[str] = Header(None)) -> bool:
    if not _WORKER_TOKEN:
        raise HTTPException(status_code=503, detail="Worker no configurado (falta CLAVES_WORKER_TOKEN).")
    if not x_claves_worker or not secrets.compare_digest(x_claves_worker, _WORKER_TOKEN):
        raise HTTPException(status_code=401, detail="Token de worker inválido.")
    return True


# --- Schemas ----------------------------------------------------------------
class CandidatoIn(BaseModel):
    cid: str = Field(..., max_length=16)
    topic: str = Field("otro", max_length=16)
    start: float
    end: float
    dur: float
    text: str = ""
    thumb_url: str = ""


class PublishIn(BaseModel):
    video_id: str = Field(..., max_length=32)
    title: str = Field("", max_length=300)
    fecha: str = Field("", max_length=20)
    candidatos: List[CandidatoIn] = Field(default_factory=list)


class RenderIn(BaseModel):
    video_id: str = Field(..., max_length=32)
    cid: str = Field(..., max_length=16)
    zoom: bool = False


class DoneIn(BaseModel):
    id: int
    video_url: str = Field(..., max_length=500)


class ErrorIn(BaseModel):
    id: int
    error: str = ""


# --- Helpers ----------------------------------------------------------------
def _programa_dict(p: ClavesPrograma, renders: List[ClavesRender]) -> dict:
    try:
        cands = json.loads(p.candidatos or "[]")
    except (ValueError, TypeError):
        cands = []
    # índice de renders por (cid, zoom) — mostramos el más reciente por candidato
    by_cid: dict = {}
    for r in renders:
        prev = by_cid.get(r.cid)
        if prev is None or r.updated_at > prev.updated_at:
            by_cid[r.cid] = r
    for c in cands:
        r = by_cid.get(c.get("cid"))
        c["render"] = None if r is None else {
            "id": r.id, "estado": r.estado, "video_url": r.video_url or "",
            "zoom": bool(r.zoom), "error": r.error or "",
        }
    return {"video_id": p.video_id, "title": p.title or "", "fecha": p.fecha or "",
            "created_at": p.created_at.isoformat() if p.created_at else "",
            "candidatos": cands}


# --- Endpoints de EQUIPO ----------------------------------------------------
@router.get("/programas")
def listar_programas(
    db: Session = Depends(get_db),
    _: str = Depends(require_roles(ROLE_COMUNICACION)),
) -> dict:
    progs = db.query(ClavesPrograma).order_by(ClavesPrograma.created_at.desc()).all()
    vids = [p.video_id for p in progs]
    renders = (db.query(ClavesRender).filter(ClavesRender.video_id.in_(vids)).all()
               if vids else [])
    by_vid: dict = {}
    for r in renders:
        by_vid.setdefault(r.video_id, []).append(r)
    return {"programas": [_programa_dict(p, by_vid.get(p.video_id, [])) for p in progs]}


@router.post("/render")
def pedir_render(
    payload: RenderIn,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
    _: str = Depends(require_roles(ROLE_COMUNICACION)),
) -> dict:
    prog = db.query(ClavesPrograma).filter(ClavesPrograma.video_id == payload.video_id).first()
    if not prog:
        raise HTTPException(status_code=404, detail="Programa no encontrado")
    try:
        cands = json.loads(prog.candidatos or "[]")
    except (ValueError, TypeError):
        cands = []
    if payload.cid not in {c.get("cid") for c in cands}:
        raise HTTPException(status_code=404, detail="Candidato no encontrado")
    # Dedupe: si ya hay un pedido vivo (pendiente/procesando/listo) con el mismo
    # candidato y zoom, lo reusamos (no encolamos de nuevo).
    existing = (db.query(ClavesRender)
                .filter(ClavesRender.video_id == payload.video_id,
                        ClavesRender.cid == payload.cid,
                        ClavesRender.zoom.is_(bool(payload.zoom)),
                        ClavesRender.estado.in_(["pendiente", "procesando", "listo"]))
                .order_by(ClavesRender.updated_at.desc()).first())
    if existing:
        return {"id": existing.id, "estado": existing.estado}
    r = ClavesRender(video_id=payload.video_id, cid=payload.cid, zoom=bool(payload.zoom),
                     estado="pendiente", requested_by=actor.email or "",
                     created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "estado": r.estado}


# --- Endpoints de WORKER ----------------------------------------------------
@router.post("/worker/publish")
def worker_publish(
    payload: PublishIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_worker),
) -> dict:
    cands = [c.model_dump() for c in payload.candidatos]
    prog = db.query(ClavesPrograma).filter(ClavesPrograma.video_id == payload.video_id).first()
    if prog is None:
        prog = ClavesPrograma(video_id=payload.video_id, created_at=datetime.utcnow())
        db.add(prog)
    prog.title = payload.title or prog.title or ""
    prog.fecha = payload.fecha or prog.fecha or ""
    prog.candidatos = json.dumps(cands, ensure_ascii=False)
    db.commit()
    return {"ok": True, "video_id": payload.video_id, "candidatos": len(cands)}


# Un pedido en 'procesando' más viejo que esto se considera colgado (el worker se
# reinició o crasheó a mitad del render) y se vuelve a tomar en el próximo poll.
_STALE = timedelta(minutes=3)


@router.get("/worker/pending")
def worker_pending(
    db: Session = Depends(get_db),
    _: bool = Depends(require_worker),
) -> dict:
    stale_before = datetime.utcnow() - _STALE
    rows = (db.query(ClavesRender)
            .filter((ClavesRender.estado == "pendiente")
                    | ((ClavesRender.estado == "procesando")
                       & (ClavesRender.updated_at < stale_before)))
            .order_by(ClavesRender.created_at.asc()).all())
    claimed = []
    for r in rows:
        r.estado = "procesando"
        r.updated_at = datetime.utcnow()
        claimed.append({"id": r.id, "video_id": r.video_id, "cid": r.cid, "zoom": bool(r.zoom)})
    if rows:
        db.commit()
    return {"pedidos": claimed}


@router.post("/worker/done")
def worker_done(
    payload: DoneIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_worker),
) -> dict:
    r = db.get(ClavesRender, payload.id)
    if not r:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    r.estado = "listo"
    r.video_url = payload.video_url
    r.error = ""
    r.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/worker/error")
def worker_error(
    payload: ErrorIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_worker),
) -> dict:
    r = db.get(ClavesRender, payload.id)
    if not r:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    r.estado = "error"
    r.error = (payload.error or "")[:2000]
    r.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
