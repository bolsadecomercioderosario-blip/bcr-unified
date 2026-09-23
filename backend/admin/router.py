"""
Panel de administración de usuarios (login por email). SÓLO admin (hoy: Juan).

Todos los endpoints están protegidos por `require_admin` (403 si el token no es
de un usuario administrador). Nunca se devuelve el hash de contraseña. Las
contraseñas temporales (alta / reseteo) se devuelven UNA vez, para que el admin
se las pase a la persona; después la persona la cambia en su primer ingreso.

Las ÁREAS internas no se administran acá: siguen con su clave compartida
(env AREA_<SLUG>_PASSWORD). Ver auth.py.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import user_models
from auth import (Actor, USER_ROLES, generate_temp_password, hash_password,
                  require_admin, revoke_user_sessions)
from database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _dto(u: user_models.AppUser) -> dict:
    """Usuario para el frontend (sin datos sensibles)."""
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_admin": u.is_admin,
        "active": u.active,
        "must_change_password": u.must_change_password,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _get_or_404(db: Session, user_id: int) -> user_models.AppUser:
    u = db.query(user_models.AppUser).filter(user_models.AppUser.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return u


@router.get("/users")
async def list_users(_: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(user_models.AppUser).order_by(user_models.AppUser.email).all()
    return {"users": [_dto(u) for u in users], "roles": sorted(USER_ROLES)}


@router.post("/users")
async def create_user(payload: dict, _: Actor = Depends(require_admin),
                      db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    role = (payload.get("role") or "").strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Email inválido")
    if not name:
        raise HTTPException(status_code=400, detail="Falta el nombre")
    if role not in USER_ROLES:
        raise HTTPException(status_code=400, detail="Rol inválido")
    if db.query(user_models.AppUser).filter(user_models.AppUser.email == email).first():
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")
    temp = generate_temp_password()
    u = user_models.AppUser(
        email=email, name=name, role=role, is_admin=False, active=True,
        must_change_password=True, password_hash=hash_password(temp),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"user": _dto(u), "temp_password": temp}


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, _: Actor = Depends(require_admin),
                         db: Session = Depends(get_db)):
    u = _get_or_404(db, user_id)
    temp = generate_temp_password()
    u.password_hash = hash_password(temp)
    u.must_change_password = True
    db.commit()
    # Lo saca de cualquier sesión abierta: debe reingresar con la temporal.
    revoke_user_sessions(db, u.id)
    return {"user": _dto(u), "temp_password": temp}


@router.post("/users/{user_id}/active")
async def set_active(user_id: int, payload: dict, admin: Actor = Depends(require_admin),
                     db: Session = Depends(get_db)):
    u = _get_or_404(db, user_id)
    active = bool(payload.get("active"))
    if not active:
        # Salvaguardas para no quedarnos sin admin ni bloquearse a uno mismo.
        if admin.user and u.id == admin.user.id:
            raise HTTPException(status_code=400, detail="No podés desactivarte a vos mismo")
        if u.is_admin:
            raise HTTPException(status_code=400, detail="No se puede desactivar a un administrador")
    u.active = active
    db.commit()
    if not active:
        revoke_user_sessions(db, u.id)
    return {"user": _dto(u)}


@router.post("/users/{user_id}/role")
async def set_role(user_id: int, payload: dict, _: Actor = Depends(require_admin),
                   db: Session = Depends(get_db)):
    u = _get_or_404(db, user_id)
    role = (payload.get("role") or "").strip()
    if role not in USER_ROLES:
        raise HTTPException(status_code=400, detail="Rol inválido")
    u.role = role
    db.commit()
    # El rol viejo puede estar cacheado en el front; al revocar, retoma el nuevo
    # al reloguear. (El backend ya lee el rol vivo de la DB en cada request.)
    revoke_user_sessions(db, u.id)
    return {"user": _dto(u)}
