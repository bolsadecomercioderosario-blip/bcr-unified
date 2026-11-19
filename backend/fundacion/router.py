"""
API de la Agenda de la Fundación BCR.

- GET  /api/fundacion/actividades?token=…   → lista pública PROTEGIDA POR TOKEN
  (la vista /fundacion/{token} la consume). Token inválido → 401.
- POST/PUT/DELETE                            → mantenimiento, sólo rol Comunicación.

La carga habitual de actividades NO pasa por acá: entra por el seed (importación
única) y por WhatsApp (bot/fundacion_writer, que escribe vía store.crear).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import require_roles, ROLE_COMUNICACION
from config import FUNDACION_TOKEN
from database import get_db

from . import store
from .models import ActividadIn, ActividadOut, FundacionActividad

router = APIRouter(prefix="/api/fundacion", tags=["fundacion"])


def _check_token(token: str):
    if not FUNDACION_TOKEN or token != FUNDACION_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")


@router.get("/actividades", response_model=List[ActividadOut])
def listar_actividades(token: str = Query(default=""), db: Session = Depends(get_db)):
    """Lista pública (solo lectura) protegida por el token del link."""
    _check_token(token)
    return store.listar(db)


@router.post("/actividades", response_model=ActividadOut, status_code=201)
def crear_actividad(
    payload: ActividadIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_roles(ROLE_COMUNICACION)),
):
    if not (payload.evento or "").strip():
        raise HTTPException(status_code=400, detail="El evento no puede estar vacío")
    act = store.crear(db, payload.dict(), origen="web", created_by="web")
    return act


@router.put("/actividades/{act_id}", response_model=ActividadOut)
def editar_actividad(
    act_id: str,
    payload: ActividadIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_roles(ROLE_COMUNICACION)),
):
    act = db.query(FundacionActividad).filter(FundacionActividad.id == act_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    from datetime import datetime
    for f in ("fecha", "hora", "evento", "equipo", "metricas"):
        setattr(act, f, (getattr(payload, f) or "").strip())
    act.updated_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(act)
    return act


@router.delete("/actividades/{act_id}", status_code=204)
def archivar_actividad(
    act_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(require_roles(ROLE_COMUNICACION)),
):
    """Soft-delete: marca como archivada (nunca borra físicamente)."""
    act = db.query(FundacionActividad).filter(FundacionActividad.id == act_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    from datetime import datetime
    act.archived = True
    act.archived_at = datetime.utcnow().isoformat()
    db.commit()
    return None
