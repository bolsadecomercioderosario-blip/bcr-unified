"""
Autenticación simple para los endpoints API.

Modelo: passwords compartidos por todo el equipo (env vars AGENDA_PASSWORD y
SECGRAL_PASSWORD). Cuando el cliente hace login con cualquiera de ellos, recibe
el mismo token de sesión opaco que tiene que mandar como
`Authorization: Bearer <token>` en todos los requests siguientes.

Por qué dos passwords con mismos permisos: el equipo de Secretaría General
también carga actividades (con canal "Agenda Compromisos"), y queremos que
cada equipo tenga su propio password para que si uno se filtra podamos rotarlo
sin romperle el acceso al otro. No hay roles ni granularidad de permisos —
ambos passwords dan acceso completo.

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


# Passwords aceptados. El de Comunicación (AGENDA_PASSWORD) existe desde
# siempre. El de SecGral se agregó para que Secretaría General también pueda
# cargar actividades sin compartir credenciales.
PASSWORD_AGENDA = os.environ.get("AGENDA_PASSWORD", "bcr2024")
PASSWORD_SECGRAL = os.environ.get("SECGRAL_PASSWORD", "secgral2026")

# Token de sesión. Idealmente seteado en Render como env var para sobrevivir
# reinicios.
SESSION_TOKEN = os.environ.get("SESSION_TOKEN") or secrets.token_urlsafe(32)


def verify_password(password: Optional[str]) -> bool:
    """Acepta cualquiera de los dos passwords. Constant-time para no filtrar
    info por timing — siempre evaluamos los dos compare_digest."""
    if not password:
        return False
    matches_agenda = secrets.compare_digest(password, PASSWORD_AGENDA)
    matches_secgral = secrets.compare_digest(password, PASSWORD_SECGRAL)
    return matches_agenda or matches_secgral


def require_auth(authorization: Optional[str] = Header(None)) -> bool:
    """Dependency de FastAPI: 401 si falta el header o no coincide el token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Auth requerida")
    token = authorization[len("Bearer "):].strip()
    if not secrets.compare_digest(token, SESSION_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")
    return True
