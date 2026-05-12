"""
Autenticación simple para los endpoints API.

Modelo: un único password compartido por todo el equipo (env var AGENDA_PASSWORD
con fallback "bcr2024" — mismo que ya usaba el módulo Agenda). Cuando el cliente
hace login con ese password, recibe un token de sesión opaco que tiene que
mandar como `Authorization: Bearer <token>` en todos los requests siguientes.

El token es un único string fijo por proceso:
 - Si SESSION_TOKEN está en env vars, lo usa (recomendado en producción para
   que reinicios de Render no invaliden sesiones).
 - Si no, se genera uno random al arranque (cada reinicio invalida sesiones
   activas — aceptable en dev).
"""
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException


# Password compartido — misma env var que usaba el viejo /api/agenda/auth para
# no romper deployments existentes.
PASSWORD = os.environ.get("AGENDA_PASSWORD", "bcr2024")

# Token de sesión. Idealmente seteado en Render como env var para sobrevivir
# reinicios.
SESSION_TOKEN = os.environ.get("SESSION_TOKEN") or secrets.token_urlsafe(32)


def verify_password(password: Optional[str]) -> bool:
    """Compara el password de manera constant-time para no filtrar info via timing."""
    if not password:
        return False
    return secrets.compare_digest(password, PASSWORD)


def require_auth(authorization: Optional[str] = Header(None)) -> bool:
    """Dependency de FastAPI: 401 si falta el header o no coincide el token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Auth requerida")
    token = authorization[len("Bearer "):].strip()
    if not secrets.compare_digest(token, SESSION_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")
    return True
