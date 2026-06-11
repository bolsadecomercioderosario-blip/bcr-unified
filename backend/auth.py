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


# Roles. Las dos passwords dan el mismo token de sesión (mismo acceso a la API),
# pero el login devuelve además QUÉ rol entró para que el frontend ajuste la
# interfaz. v1: la separación de roles es sólo de UI (frontend), el backend no
# la enforcea todavía — ver blueprint del rediseño de Agenda.
ROLE_COMUNICACION = "comunicacion"
ROLE_SECRETARIA = "secretaria"


def role_for_password(password: Optional[str]) -> Optional[str]:
    """Devuelve el rol asociado al password, o None si no matchea ninguno.
    Constant-time: siempre evalúa los dos compare_digest para no filtrar por
    timing cuál de las dos passwords se probó."""
    if not password:
        return None
    matches_agenda = secrets.compare_digest(password, PASSWORD_AGENDA)
    matches_secgral = secrets.compare_digest(password, PASSWORD_SECGRAL)
    if matches_secgral:
        return ROLE_SECRETARIA
    if matches_agenda:
        return ROLE_COMUNICACION
    return None


def verify_password(password: Optional[str]) -> bool:
    """Acepta cualquiera de los dos passwords. Se mantiene por compatibilidad;
    internamente usa role_for_password (que ya es constant-time)."""
    return role_for_password(password) is not None


def require_auth(authorization: Optional[str] = Header(None)) -> bool:
    """Dependency de FastAPI: 401 si falta el header o no coincide el token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Auth requerida")
    token = authorization[len("Bearer "):].strip()
    if not secrets.compare_digest(token, SESSION_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")
    return True
