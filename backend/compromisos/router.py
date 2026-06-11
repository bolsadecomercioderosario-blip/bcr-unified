"""
Vista pública de la Agenda de Compromisos institucionales BCR.

El equipo de Secretaría carga actividades en la app de Agenda. Las que tienen
origen='secretaria' conforman la Agenda de Compromisos y aparecen acá, en una
URL que se les comparte a las autoridades y al ecosistema BCR.

Seguridad: la URL incluye un token (env var COMPROMISOS_PUBLIC_TOKEN). Si el
token cambia, los links viejos dejan de funcionar — útil si se filtra. No hay
auth fuerte, es "security through obscurity" intencional para que las
autoridades no tengan que loguearse. La respuesta usa CompromisoPublicOut, que
expone SÓLO los Datos Generales (nada operativo ni notas internas).
"""
import os
import secrets
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

import agenda_models
from database import SessionLocal


router = APIRouter(prefix="/api/compromisos")


# Token público que valida los GET. Default razonable para dev — en Render
# se setea COMPROMISOS_PUBLIC_TOKEN con un valor real (largo, random).
PUBLIC_TOKEN = os.environ.get("COMPROMISOS_PUBLIC_TOKEN", "bcr-agenda-x9k7m2")


def _check_token(token: str) -> None:
    """compare_digest para no filtrar el token via timing attack."""
    if not token or not secrets.compare_digest(token, PUBLIC_TOKEN):
        raise HTTPException(status_code=404, detail="No encontrado")


@router.get("/{token}", response_model=List[agenda_models.CompromisoPublicOut])
def list_compromisos(token: str):
    """Devuelve las actividades de la Agenda de Compromisos (origen='secretaria').

    Sin auth bearer — valida sólo por el token de la URL. Si el token es
    inválido, devuelve 404 (no 401/403) para no leak info de existencia.
    """
    _check_token(token)
    db = SessionLocal()
    try:
        return db.query(agenda_models.Activity).filter(
            agenda_models.Activity.is_custom == False,  # noqa: E712 — SQLAlchemy
            agenda_models.Activity.origen == "secretaria",
        ).all()
    finally:
        db.close()
