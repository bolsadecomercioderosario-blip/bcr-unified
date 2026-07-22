"""
Auth por usuario del módulo Aapresid.

A diferencia del hub (password compartido), acá necesitamos identidad individual
para la auditoría (created_by / updated_by / audit_log). Implementación
autocontenida, sin dependencias nuevas:

- Contraseñas: PBKDF2-SHA256 (hashlib de la stdlib), formato
  `pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>`.
- Token de sesión: HMAC firmado sin estado (`<user_id>.<sig>`), así sobrevive
  reinicios de Render sin tabla de sesiones. Secreto en env AAPRESID_SECRET.

Roles: "admin" (config: usuarios, áreas, evento, turnos) y "editor" (carga y
edición de presencias/reuniones). Ambos ven toda la info.
"""
import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException

from database import SessionLocal
from aapresid.models import AapUser


_SECRET = os.environ.get("AAPRESID_SECRET") or "aapresid-dev-secret-cambiar-en-prod"
_PBKDF2_ITERS = 200_000


# ---- Password hashing ----
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---- Token (HMAC sin estado) ----
def make_token(user_id: int) -> str:
    sig = hmac.new(_SECRET.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"


def _parse_token(token: str) -> Optional[int]:
    try:
        user_id_str, sig = token.split(".", 1)
        expected = hmac.new(_SECRET.encode(), user_id_str.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return int(user_id_str)
    except Exception:
        pass
    return None


# ---- Dependencias FastAPI ----
def require_user(authorization: Optional[str] = Header(None)) -> AapUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Auth requerida")
    token = authorization[len("Bearer "):].strip()
    user_id = _parse_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token inválido")
    db = SessionLocal()
    try:
        user = db.query(AapUser).filter(AapUser.id == user_id).first()
        if not user or not user.active:
            raise HTTPException(status_code=401, detail="Usuario inactivo o inexistente")
        return user
    finally:
        db.close()


def require_admin(user: AapUser = Depends(require_user)) -> AapUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Requiere permisos de administrador")
    return user
