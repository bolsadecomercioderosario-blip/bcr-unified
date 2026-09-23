"""
Usuarios individuales de la app (login por email + contraseña propia).

A diferencia de las ÁREAS —que siguen con contraseña compartida por área (ver
auth.py)—, las personas de Comunicación, Audiovisual y Secretaría tienen un
usuario propio: así hay identidad individual (auditoría: quién hizo qué) y cada
uno con su contraseña privada. Las sesiones se guardan en DB (token opaco) para
poder vencerlas/revocarlas.

Las tablas se crean solas al arrancar (Base.metadata.create_all en app.py), con
tal de importar este módulo antes (side-effect del registro de modelos).
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from database import Base


class AppUser(Base):
    """Una persona con login propio. `role` ∈ comunicacion | audiovisual |
    secretaria (las áreas NO son usuarios; usan la clave compartida del área)."""
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)  # en minúsculas
    name = Column(String, nullable=False, default="")
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    # Fuerza el cambio de contraseña en el primer ingreso (opción A: el admin da
    # una temporal y la persona la cambia por una propia).
    must_change_password = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserSession(Base):
    """Sesión de un usuario: token opaco (guardamos su hash) → user_id, con
    vencimiento. Permite cerrar sesión/expirar sin depender de secretos en el
    token. Las áreas NO usan esto (siguen con token HMAC stateless)."""
    __tablename__ = "user_sessions"

    token_hash = Column(String, primary_key=True)  # sha256 hex del token opaco
    user_id = Column(Integer, index=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
