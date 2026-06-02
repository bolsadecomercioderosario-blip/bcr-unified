"""
Router del módulo "Conversatorio a la carta".

- POST /api/conversatorio/sugerencias  → público, lo usa el formulario que ven
  los socios. Rate limit por IP para evitar spam.
- GET  /api/conversatorio/sugerencias  → admin, lista todas las sugerencias.
- DELETE /api/conversatorio/sugerencias/{id} → admin, borra una sugerencia.
- GET  /api/conversatorio/sugerencias/export.csv → admin, descarga CSV.
"""
from __future__ import annotations

import csv
import io
import time
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db

from .models import Sugerencia


router = APIRouter(prefix="/api/conversatorio", tags=["conversatorio"])


# --- Rate limit: 5 envíos por minuto por IP -------------------------------
RATE_LIMIT = 5
RATE_WINDOW = 60
_rate: dict[str, deque[float]] = {}
_rate_lock = Lock()


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        dq = _rate.setdefault(ip, deque())
        while dq and dq[0] < now - RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            return True
        dq.append(now)
        return False


# --- Schemas --------------------------------------------------------------
class SugerenciaIn(BaseModel):
    tema: str = Field(..., min_length=3, max_length=500)
    nombre: Optional[str] = Field("", max_length=120)
    email: Optional[str] = Field("", max_length=200)
    comentarios: Optional[str] = Field("", max_length=2000)


class SugerenciaOut(BaseModel):
    id: int
    created_at: datetime
    nombre: str
    email: str
    tema: str
    comentarios: str

    class Config:
        from_attributes = True


# --- Endpoint público (form de socios) ------------------------------------
@router.post("/sugerencias", status_code=201)
def crear_sugerencia(
    payload: SugerenciaIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(
            status_code=429,
            detail="Recibimos varios mensajes desde tu conexión en los últimos segundos. Esperá un momento e intentá de nuevo.",
        )

    tema = (payload.tema or "").strip()
    if not tema:
        raise HTTPException(status_code=400, detail="El tema es obligatorio.")

    sug = Sugerencia(
        tema=tema,
        nombre=(payload.nombre or "").strip(),
        email=(payload.email or "").strip(),
        comentarios=(payload.comentarios or "").strip(),
        ip=ip,
    )
    db.add(sug)
    db.commit()
    db.refresh(sug)
    return {"ok": True, "id": sug.id}


# --- Endpoints admin ------------------------------------------------------
@router.get("/sugerencias", response_model=list[SugerenciaOut])
def listar_sugerencias(
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> list[Sugerencia]:
    return (
        db.query(Sugerencia)
        .order_by(Sugerencia.created_at.desc())
        .all()
    )


@router.delete("/sugerencias/{sug_id}", status_code=204)
def borrar_sugerencia(
    sug_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> None:
    sug = db.get(Sugerencia, sug_id)
    if not sug:
        raise HTTPException(status_code=404, detail="No encontrada")
    db.delete(sug)
    db.commit()


@router.get("/sugerencias/export.csv")
def exportar_csv(
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> StreamingResponse:
    sugs = (
        db.query(Sugerencia)
        .order_by(Sugerencia.created_at.desc())
        .all()
    )

    buf = io.StringIO()
    buf.write("﻿")  # BOM para que Excel abra UTF-8 sin romper acentos
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["id", "fecha", "nombre", "email", "tema", "comentarios"])
    for s in sugs:
        writer.writerow([
            s.id,
            s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
            s.nombre or "",
            s.email or "",
            s.tema or "",
            s.comentarios or "",
        ])

    buf.seek(0)
    fname = f"conversatorio-sugerencias-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
