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
from sqlalchemy import or_
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


def _query_compromisos(scope: str):
    """Actividades de la Agenda de Compromisos.
    scope='mesa' (default): Secretaría + áreas aprobadas.
    scope='completa': suma toda la agenda de las áreas (Funcionarios)."""
    db = SessionLocal()
    try:
        A = agenda_models.Activity
        q = db.query(A).filter(
            A.is_custom == False,  # noqa: E712 — SQLAlchemy
            A.archived == False,   # noqa: E712 — no mostrar archivadas
        )
        if scope == "completa":
            q = q.filter(A.origen.in_(["secretaria", "area"]))
        else:
            q = q.filter(or_(A.origen == "secretaria", A.me_estado == "aprobada"))
        return q.all()
    finally:
        db.close()


@router.get("", response_model=List[agenda_models.CompromisoPublicOut])
def list_compromisos_public(scope: str = "mesa"):
    """Endpoint público sin token (la landing vive en /compromisos)."""
    return _query_compromisos(scope)


@router.get("/{token}", response_model=List[agenda_models.CompromisoPublicOut])
def list_compromisos(token: str, scope: str = "mesa"):
    """Compat: links viejos con token en la URL (/compromisos/{token})."""
    _check_token(token)
    return _query_compromisos(scope)
