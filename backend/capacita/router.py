"""
Router del módulo "BCR Capacita — captación de leads".

- POST   /api/capacita/leads             → público, lo usa el formulario de
  campaña. Rate limit por IP para evitar spam.
- GET    /api/capacita/leads             → admin, lista todos los leads.
- DELETE /api/capacita/leads/{id}        → admin, borra un lead.
- GET    /api/capacita/leads/export.csv  → admin, descarga CSV.

Validaciones del lead (espejo de las del front, porque nunca se confía en el
cliente):
  * Al menos uno de email / whatsapp.
  * Email con formato válido si viene.
  * WhatsApp con dígitos suficientes si viene.
  * Al menos un área de interés.
  * autorizacion == True.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import deque
from datetime import datetime
from threading import Lock
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db

from .models import CapacitaLead


router = APIRouter(prefix="/api/capacita", tags=["capacita"])


# --- Áreas de interés válidas (whitelist) ---------------------------------
# Se valida contra esta lista para no guardar basura inyectada por el cliente.
AREAS_VALIDAS = {
    "Mercado de Capitales y Finanzas",
    "Mercado de Granos",
    "Futuros y Opciones",
    "Logística y Operaciones Agroindustriales",
    "Innovación, Tecnología y Datos",
    "Aspectos Legales, Normativos y Compliance",
    "Gestión de las organizaciones y habilidades blandas",
}


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


# --- Validadores ----------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _whatsapp_digits(raw: str) -> str:
    """Devuelve solo los dígitos del whatsapp (sin +, espacios ni guiones)."""
    return re.sub(r"\D", "", raw or "")


# --- Schemas --------------------------------------------------------------
class LeadIn(BaseModel):
    email: Optional[str] = Field("", max_length=200)
    whatsapp: Optional[str] = Field("", max_length=40)
    intereses: List[str] = Field(default_factory=list)
    autorizacion: bool = True
    origen: Optional[str] = Field("", max_length=64)


class LeadOut(BaseModel):
    id: int
    created_at: datetime
    email: str
    whatsapp: str
    intereses: List[str]
    autorizacion: bool
    origen: str

    class Config:
        from_attributes = True


# --- Endpoint público (form de campaña) -----------------------------------
@router.post("/leads", status_code=201)
def crear_lead(
    payload: LeadIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(
            status_code=429,
            detail="Recibimos varios registros desde tu conexión en los últimos segundos. Esperá un momento e intentá de nuevo.",
        )

    email = (payload.email or "").strip()
    whatsapp_raw = (payload.whatsapp or "").strip()
    whatsapp_digits = _whatsapp_digits(whatsapp_raw)

    # Al menos un dato de contacto.
    if not email and not whatsapp_digits:
        raise HTTPException(
            status_code=400,
            detail="Dejanos al menos un dato de contacto: email o WhatsApp.",
        )

    # Formato de email (si vino).
    if email and not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="El email no tiene un formato válido.")

    # Formato de whatsapp (si vino): entre 8 y 15 dígitos, según E.164.
    if whatsapp_raw and not (8 <= len(whatsapp_digits) <= 15):
        raise HTTPException(status_code=400, detail="El número de WhatsApp no parece válido.")

    # Áreas de interés: al menos una, todas dentro de la whitelist.
    intereses = [i for i in (payload.intereses or []) if i in AREAS_VALIDAS]
    if not intereses:
        raise HTTPException(
            status_code=400,
            detail="Elegí al menos un área de interés.",
        )

    # Consentimiento obligatorio.
    if not payload.autorizacion:
        raise HTTPException(
            status_code=400,
            detail="Necesitamos tu autorización para poder contactarte.",
        )

    lead = CapacitaLead(
        email=email,
        whatsapp=whatsapp_raw,
        intereses=json.dumps(intereses, ensure_ascii=False),
        autorizacion=True,
        origen=(payload.origen or "").strip()[:64],
        ip=ip,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return {"ok": True, "id": lead.id}


# --- Helpers admin --------------------------------------------------------
def _to_out(lead: CapacitaLead) -> LeadOut:
    try:
        intereses = json.loads(lead.intereses or "[]")
    except (ValueError, TypeError):
        intereses = []
    return LeadOut(
        id=lead.id,
        created_at=lead.created_at,
        email=lead.email or "",
        whatsapp=lead.whatsapp or "",
        intereses=intereses,
        autorizacion=bool(lead.autorizacion),
        origen=lead.origen or "",
    )


# --- Endpoints admin ------------------------------------------------------
@router.get("/leads", response_model=list[LeadOut])
def listar_leads(
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> list[LeadOut]:
    leads = db.query(CapacitaLead).order_by(CapacitaLead.created_at.desc()).all()
    return [_to_out(l) for l in leads]


@router.delete("/leads/{lead_id}", status_code=204)
def borrar_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> None:
    lead = db.get(CapacitaLead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(lead)
    db.commit()


@router.get("/leads/export.csv")
def exportar_csv(
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> StreamingResponse:
    leads = db.query(CapacitaLead).order_by(CapacitaLead.created_at.desc()).all()

    buf = io.StringIO()
    buf.write("﻿")  # BOM para que Excel abra UTF-8 sin romper acentos
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["id", "fecha", "email", "whatsapp", "intereses", "autorizacion", "origen"])
    for l in leads:
        out = _to_out(l)
        writer.writerow([
            out.id,
            out.created_at.strftime("%Y-%m-%d %H:%M") if out.created_at else "",
            out.email,
            out.whatsapp,
            " | ".join(out.intereses),
            "sí" if out.autorizacion else "no",
            out.origen,
        ])

    buf.seek(0)
    fname = f"capacita-leads-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
