"""
Autenticación simple para los endpoints API.

Modelo: password compartido por rol. Cada rol tiene su propio password (env
vars) y, al loguearse, recibe un **token de sesión propio del rol** que manda
como `Authorization: Bearer <token>` en cada request. Que el token sea distinto
por rol es lo que permite que el backend sepa QUIÉN sos y aplique permisos
(ej.: un área sólo edita lo suyo; sólo Secretaría edita la Mesa).

Roles:
 - comunicacion  → app de Comunicación (coberturas).
 - secretaria    → administra la Agenda de Compromisos (Mesa Ejecutiva).
 - area:<slug>   → un área interna (DIyEE, Innova, CAC, BCR Digital…) que carga
                   su propia agenda y sugiere actividades a la Mesa.

Los tokens se derivan por HMAC de un secreto base (SESSION_TOKEN): son estables
entre reinicios si SESSION_TOKEN está en el entorno, y no requieren almacenar
sesiones. Si SESSION_TOKEN no está, se genera uno random al arranque (cada
reinicio invalida sesiones — aceptable en dev).
"""
import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException


# --- Passwords por rol ------------------------------------------------------
# Comunicación y Secretaría existen desde siempre. Las áreas se agregan para el
# circuito de "Funcionarios" (cada área carga su agenda y sugiere a la Mesa).
PASSWORD_AGENDA = os.environ.get("AGENDA_PASSWORD", "bcr2024")
PASSWORD_SECGRAL = os.environ.get("SECGRAL_PASSWORD", "secgral2026")

# Áreas internas habilitadas a cargar su propia agenda. Extensible: sumar una
# nueva es agregar acá y setear su env var AREA_<SLUG>_PASSWORD en Render.
AREAS = [
    {"slug": "diyee", "nombre": "DIyEE"},
    {"slug": "innova", "nombre": "Innova"},
    {"slug": "cac", "nombre": "CAC"},
    {"slug": "bcrdigital", "nombre": "BCR Digital"},
    {"slug": "fundacion", "nombre": "Fundación BCR"},
    {"slug": "legales", "nombre": "Legales"},
    {"slug": "bcrlabs", "nombre": "BCRlabs"},
]
AREA_SLUGS = {a["slug"] for a in AREAS}
AREA_NOMBRE = {a["slug"]: a["nombre"] for a in AREAS}


def _area_password(slug: str) -> str:
    """Password del área desde AREA_<SLUG>_PASSWORD; fallback dev '<slug>2026'."""
    return os.environ.get(f"AREA_{slug.upper()}_PASSWORD", f"{slug}2026")


# --- Roles ------------------------------------------------------------------
ROLE_COMUNICACION = "comunicacion"
ROLE_SECRETARIA = "secretaria"


def role_area(slug: str) -> str:
    return f"area:{slug}"


def area_of_role(role: Optional[str]) -> Optional[str]:
    """Si el rol es de un área, devuelve su slug; si no, None."""
    if role and role.startswith("area:"):
        return role[len("area:"):]
    return None


def is_area_role(role: Optional[str]) -> bool:
    return area_of_role(role) in AREA_SLUGS


# Lista completa de roles válidos (para derivar/validar tokens).
ALL_ROLES = [ROLE_COMUNICACION, ROLE_SECRETARIA] + [role_area(s) for s in AREA_SLUGS]


# --- Secreto base y tokens por rol ------------------------------------------
SESSION_SECRET = os.environ.get("SESSION_TOKEN") or secrets.token_urlsafe(32)


def token_for_role(role: str) -> str:
    """Token de sesión determinístico para un rol (HMAC del secreto base)."""
    return hmac.new(SESSION_SECRET.encode(), role.encode(), hashlib.sha256).hexdigest()


# Mapa token→rol precomputado al arranque.
_TOKEN_TO_ROLE = {token_for_role(r): r for r in ALL_ROLES}


def role_for_token(token: Optional[str]) -> Optional[str]:
    """Rol asociado a un token, o None. compare_digest contra cada token conocido
    para no filtrar por timing cuál matcheó."""
    if not token:
        return None
    for tok, role in _TOKEN_TO_ROLE.items():
        if secrets.compare_digest(token, tok):
            return role
    return None


def role_for_password(password: Optional[str]) -> Optional[str]:
    """Rol asociado al password, o None si no matchea. Constant-time: evalúa
    todos los compare_digest para no filtrar por timing cuál se probó."""
    if not password:
        return None
    matched: Optional[str] = None
    if secrets.compare_digest(password, PASSWORD_SECGRAL):
        matched = ROLE_SECRETARIA
    if secrets.compare_digest(password, PASSWORD_AGENDA):
        matched = matched or ROLE_COMUNICACION
    for slug in AREA_SLUGS:
        if secrets.compare_digest(password, _area_password(slug)):
            matched = matched or role_area(slug)
    return matched


def verify_password(password: Optional[str]) -> bool:
    """Acepta cualquier password válido. Compat: usa role_for_password."""
    return role_for_password(password) is not None


# --- Dependencies de FastAPI ------------------------------------------------
def _role_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):].strip()
    return role_for_token(token)


def require_auth(authorization: Optional[str] = Header(None)) -> bool:
    """401 si falta el header o el token no corresponde a ningún rol."""
    if _role_from_header(authorization) is None:
        raise HTTPException(status_code=401, detail="Auth requerida")
    return True


def get_role(authorization: Optional[str] = Header(None)) -> str:
    """Devuelve el rol del token (401 si inválido). Para endpoints que necesitan
    saber quién es (enforcement de permisos)."""
    role = _role_from_header(authorization)
    if role is None:
        raise HTTPException(status_code=401, detail="Auth requerida")
    return role


def require_roles(*allowed_roles: str):
    """Factory de dependency: exige que el token sea de UNO de los roles dados.

    Diferencia con require_auth: require_auth sólo verifica que haya un token
    válido (cualquier rol); require_roles además chequea AUTORIZACIÓN por rol
    (401 si no hay token, 403 si el rol no está permitido). Usar en módulos que
    no son para todos (ej. las herramientas operativas son sólo de Comunicación).
    """
    allowed = set(allowed_roles)

    def _dep(role: str = Depends(get_role)) -> str:
        if role not in allowed:
            raise HTTPException(status_code=403, detail="Tu rol no tiene acceso a esta sección")
        return role

    return _dep
