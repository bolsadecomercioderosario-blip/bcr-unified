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
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from user_models import AppUser, UserSession


# --- Fail-closed de secretos ------------------------------------------------
# En PRODUCCIÓN (Render = hay DATABASE_URL) nunca caemos a un password por
# defecto conocido: si falta la env var, usamos un valor aleatorio inutilizable
# (esa credencial no funciona hasta configurarla) y avisamos por log. Así un
# secreto sin setear NO deja una puerta abierta con clave adivinable, y a la vez
# no tiramos abajo toda la app ni rompemos a los demás roles. En dev local
# (SQLite, sin DATABASE_URL) se usa el default de conveniencia de siempre.
_IS_PROD = bool(os.environ.get("DATABASE_URL"))


def _secret(env_name: str, dev_default: str) -> str:
    val = os.environ.get(env_name)
    if val:
        return val
    if _IS_PROD:
        print(f"[auth] ADVERTENCIA: falta {env_name} en producción → esa credencial "
              f"queda DESHABILITADA (valor aleatorio, no el default del código).")
        return secrets.token_urlsafe(32)
    return dev_default


# --- Passwords por rol ------------------------------------------------------
# Comunicación y Secretaría existen desde siempre. Las áreas se agregan para el
# circuito de "Funcionarios" (cada área carga su agenda y sugiere a la Mesa).
PASSWORD_AGENDA = _secret("AGENDA_PASSWORD", "bcr2024")
PASSWORD_SECGRAL = _secret("SECGRAL_PASSWORD", "secgral2026")

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
    """Password del área desde AREA_<SLUG>_PASSWORD; en dev cae a '<slug>2026',
    en prod (sin la env var) queda deshabilitado (ver _secret)."""
    return _secret(f"AREA_{slug.upper()}_PASSWORD", f"{slug}2026")


# --- Roles ------------------------------------------------------------------
ROLE_COMUNICACION = "comunicacion"
ROLE_SECRETARIA = "secretaria"
# Rol restringido (Santiago, Editor AV): ve sólo su pestaña y edita sólo el link
# de video. Sólo existe como usuario individual (no hay clave compartida AV).
ROLE_AUDIOVISUAL = "audiovisual"

# Roles válidos para un USUARIO individual (login por email). Las áreas NO son
# usuarios: usan la clave compartida del área (role_area).
USER_ROLES = {ROLE_COMUNICACION, ROLE_SECRETARIA, ROLE_AUDIOVISUAL}


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
# Si falta SESSION_TOKEN: en dev se genera uno al vuelo; en prod también, pero
# eso rota los tokens en cada deploy (todos deben re-loguear) → conviene setearlo.
SESSION_SECRET = os.environ.get("SESSION_TOKEN") or secrets.token_urlsafe(32)
if not os.environ.get("SESSION_TOKEN") and _IS_PROD:
    print("[auth] ADVERTENCIA: falta SESSION_TOKEN en producción → las sesiones se "
          "invalidan en cada deploy. Setealo en Render.")


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


# ===========================================================================
# Usuarios individuales (login por email + contraseña propia) — DB-backed.
# Coexiste con lo de arriba: las áreas y las claves compartidas siguen igual.
# ===========================================================================
_PBKDF2_ITERS = 200_000
_SESSION_TTL = timedelta(days=30)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt.hex()}${dk.hex()}"


def verify_password_hash(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:  # noqa: BLE001 — hash malformado = no matchea
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate_user(db: Session, email: str, password: str) -> Optional[AppUser]:
    """Devuelve el usuario si el email existe, está activo y la contraseña matchea."""
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    user = db.query(AppUser).filter(AppUser.email == email, AppUser.active.is_(True)).first()
    if not user or not verify_password_hash(password, user.password_hash):
        return None
    return user


def create_session(db: Session, user: AppUser) -> str:
    """Crea una sesión y devuelve el token opaco (se guarda sólo su hash)."""
    raw = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(UserSession(token_hash=_hash_token(raw), user_id=user.id,
                       created_at=now, expires_at=now + _SESSION_TTL))
    db.commit()
    return raw


def resolve_user_token(db: Session, token: str) -> Optional[AppUser]:
    """Usuario detrás de un token de sesión, o None (vencido/ inexistente/inactivo)."""
    if not token:
        return None
    sess = db.query(UserSession).filter(UserSession.token_hash == _hash_token(token)).first()
    if not sess:
        return None
    if sess.expires_at < datetime.utcnow():
        db.delete(sess)
        db.commit()
        return None
    return db.query(AppUser).filter(AppUser.id == sess.user_id, AppUser.active.is_(True)).first()


# Set inicial de usuarios (emails/roles NO son secretos, como la lista de AREAS).
# El admin es Juan. Santiago es Audiovisual (Gmail, no @bcr.com.ar).
_SEED_USERS = [
    ("adallavalle@bcr.com.ar", "Anaclara Dalla Valle", ROLE_COMUNICACION, False),
    ("jchiummiento@bcr.com.ar", "Juan Chiummiento", ROLE_COMUNICACION, True),
    ("gdurando@bcr.com.ar", "Guillermina Durando", ROLE_COMUNICACION, False),
    ("arodriguez@bcr.com.ar", "Agustín Rodríguez", ROLE_COMUNICACION, False),
    ("npawlusiak@bcr.com.ar", "Nicolás Pawlusiak", ROLE_COMUNICACION, False),
    ("santiagoivangarcia95@gmail.com", "Santiago García", ROLE_AUDIOVISUAL, False),
    ("jmagarinos@bcr.com.ar", "Jorge Magariños", ROLE_SECRETARIA, False),
    ("dvicente@bcr.com.ar", "Daniel Vicente", ROLE_SECRETARIA, False),
]


def seed_users_if_empty(db: Session) -> None:
    """Crea los 8 usuarios la primera vez, con una contraseña TEMPORAL común
    (env USERS_BOOTSTRAP_PASSWORD) y must_change_password=True → cada uno la
    cambia en su primer ingreso. Si no hay tabla vacía o falta el env, no hace
    nada (login compartido sigue funcionando; no se rompe nada)."""
    boot = os.environ.get("USERS_BOOTSTRAP_PASSWORD")
    if not boot:
        return
    if db.query(AppUser).first() is not None:
        return
    pwd = hash_password(boot)
    for email, name, role, is_admin in _SEED_USERS:
        db.add(AppUser(email=email.lower(), name=name, role=role, is_admin=is_admin,
                       active=True, must_change_password=True, password_hash=pwd))
    db.commit()
    print(f"[auth] Seed de usuarios: creados {len(_SEED_USERS)} usuarios (contraseña temporal, deben cambiarla).")


# --- Dependencies de FastAPI ------------------------------------------------
class Actor:
    """Quién hace el request. `role` siempre; `user` sólo si es un usuario
    individual (login por email) — None para áreas/claves compartidas."""
    __slots__ = ("role", "user")

    def __init__(self, role: str, user: Optional[AppUser] = None):
        self.role = role
        self.user = user

    @property
    def email(self) -> Optional[str]:
        return self.user.email if self.user else None

    @property
    def is_admin(self) -> bool:
        return bool(self.user and self.user.is_admin)


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer "):].strip()


def _resolve_actor(authorization: Optional[str], db: Session) -> Optional[Actor]:
    """Resuelve el token a un Actor. Primero prueba el token stateless de rol
    (áreas + claves compartidas de Comunicación/Secretaría); si no, un token de
    sesión de usuario (DB). None si no es válido."""
    token = _extract_token(authorization)
    if not token:
        return None
    role = role_for_token(token)  # stateless (áreas + compartidas)
    if role is not None:
        return Actor(role=role, user=None)
    user = resolve_user_token(db, token)  # sesión de usuario
    if user is not None:
        return Actor(role=user.role, user=user)
    return None


def get_actor(authorization: Optional[str] = Header(None),
              db: Session = Depends(get_db)) -> Actor:
    """Actor del request (rol + identidad si es usuario). 401 si el token no vale."""
    actor = _resolve_actor(authorization, db)
    if actor is None:
        raise HTTPException(status_code=401, detail="Auth requerida")
    return actor


def require_auth(authorization: Optional[str] = Header(None),
                 db: Session = Depends(get_db)) -> bool:
    """401 si falta el header o el token no corresponde a ningún rol/usuario."""
    if _resolve_actor(authorization, db) is None:
        raise HTTPException(status_code=401, detail="Auth requerida")
    return True


def get_role(authorization: Optional[str] = Header(None),
             db: Session = Depends(get_db)) -> str:
    """Devuelve el rol del token (401 si inválido). Sirve para áreas/compartidas
    (stateless) y para usuarios individuales (sesión en DB)."""
    actor = _resolve_actor(authorization, db)
    if actor is None:
        raise HTTPException(status_code=401, detail="Auth requerida")
    return actor.role


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
