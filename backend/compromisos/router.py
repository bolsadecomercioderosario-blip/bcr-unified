"""
Vista pública de la Agenda de Compromisos institucionales BCR.

El equipo de Secretaría carga actividades en la app de Agenda. Las que tienen
origen='secretaria' conforman la Agenda de Compromisos y aparecen acá, en una
URL que se les comparte a las autoridades y al ecosistema BCR.

Seguridad: es una vista PÚBLICA e intencional (para que las autoridades no
tengan que loguearse). La respuesta usa CompromisoPublicOut, que expone SÓLO los
Datos Generales (nada operativo ni notas internas), así que ser pública no filtra
nada interno. Ya no hay token: la landing vive en /compromisos.
"""
from typing import List

from fastapi import APIRouter
from sqlalchemy import or_
from sqlalchemy.orm import Session

import agenda_models
from database import SessionLocal


router = APIRouter(prefix="/api/compromisos")


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
    """Endpoint público sin token (la landing vive en /compromisos). Los links
    viejos /compromisos/{token} siguen cargando la página y usan este endpoint."""
    return _query_compromisos(scope)
