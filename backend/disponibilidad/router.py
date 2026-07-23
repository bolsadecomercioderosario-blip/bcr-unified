"""
API del módulo Disponibilidad. Prefijo /api/disponibilidad.

- Carga (POST /responses) y recuperar la propia carga (GET /mine): PÚBLICO, sin
  login. Upsert por nombre: si alguien vuelve con el mismo nombre, actualiza.
- Ver resultados/coincidencias (GET /state) y borrar (DELETE): SOLO ADMIN,
  protegido por contraseña (env DISPONIBILIDAD_ADMIN_PASSWORD). Así los que
  completan la encuesta no ven las respuestas de los demás.
"""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from disponibilidad import models as m


router = APIRouter(prefix="/api/disponibilidad", tags=["disponibilidad"])

# Contraseña de administración (ver resultados). En prod se setea por env var;
# el fallback es solo para desarrollo — conviene setearla en Render.
_ADMIN_PASSWORD = os.environ.get("DISPONIBILIDAD_ADMIN_PASSWORD") or "disponibilidad2026"


def require_admin(authorization: Optional[str] = Header(None)) -> bool:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token != _ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Acceso solo para administración.")
    return True


def _out(r: m.DispResponse) -> dict:
    try:
        slots = json.loads(r.slots or "[]")
    except Exception:
        slots = []
    return {
        "id": r.id,
        "name": r.name,
        "slots": slots if isinstance(slots, list) else [],
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ---------------------------------------------------------
# Público
# ---------------------------------------------------------
@router.post("/responses")
def upsert_response(payload: m.ResponseIn, db: Session = Depends(get_db)):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Poné tu nombre.")
    slots = [s for s in (payload.slots or []) if isinstance(s, str) and s]
    slots = sorted(set(slots))
    existing = db.query(m.DispResponse).filter(
        func.lower(m.DispResponse.name) == name.lower()
    ).first()
    if existing:
        existing.name = name
        existing.slots = json.dumps(slots)
        db.commit(); db.refresh(existing)
        return _out(existing)
    r = m.DispResponse(name=name, slots=json.dumps(slots))
    db.add(r); db.commit(); db.refresh(r)
    return _out(r)


@router.get("/mine")
def get_mine(name: str, db: Session = Depends(get_db)):
    """Devuelve SOLO la carga de la persona con ese nombre (para poder editarla).
    No expone las respuestas de los demás."""
    n = (name or "").strip().lower()
    if not n:
        return {"response": None}
    r = db.query(m.DispResponse).filter(func.lower(m.DispResponse.name) == n).first()
    return {"response": _out(r) if r else None}


# ---------------------------------------------------------
# Admin (resultados / coincidencias)
# ---------------------------------------------------------
@router.post("/admin/login")
def admin_login(payload: m.AdminLogin):
    if (payload.password or "") != _ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    return {"ok": True}


@router.get("/state")
def get_state(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(m.DispResponse).order_by(func.lower(m.DispResponse.name)).all()
    return {"responses": [_out(r) for r in rows]}


@router.delete("/responses/{rid}")
def delete_response(rid: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.query(m.DispResponse).filter(m.DispResponse.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(r); db.commit()
    return {"ok": True}
