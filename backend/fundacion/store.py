"""
Helpers de datos de la Agenda de la Fundación, compartidos por el router (web)
y el writer de WhatsApp (bot). Centraliza el alta para que ambos caminos creen
las actividades igual (mismo id, timestamps, auditoría).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from .models import FundacionActividad


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def listar(db: Session, incluir_archivadas: bool = False):
    q = db.query(FundacionActividad)
    if not incluir_archivadas:
        q = q.filter(FundacionActividad.archived.is_(False))
    # Orden cronológico ascendente; la fecha vacía al final.
    return q.order_by(FundacionActividad.fecha.asc(), FundacionActividad.hora.asc()).all()


def crear(db: Session, data: dict, origen: str = "web", created_by: str = "") -> FundacionActividad:
    """Crea una actividad. `data` acepta: fecha, hora, evento, equipo, metricas."""
    now = _now_iso()
    act = FundacionActividad(
        id=uuid.uuid4().hex,
        fecha=(data.get("fecha") or "").strip(),
        hora=(data.get("hora") or "").strip(),
        evento=(data.get("evento") or "").strip(),
        equipo=(data.get("equipo") or "").strip(),
        metricas=(data.get("metricas") or "").strip(),
        origen=origen,
        created_by=created_by,
        created_at=now,
        updated_at=now,
        archived=False,
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act
