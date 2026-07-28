"""
API del módulo Murga — sorteo del estreno. Prefijo /api/murga.

- Inscripción (POST /registrar): PÚBLICO, sin login. Es lo que manda el
  formulario al que apunta el QR.
- Vistas del presentador (voluntades / participantes / excluir): protegidas por
  un token simple que viaja en la URL como ?k=TOKEN, validado contra la env var
  SORTEO_TOKEN. Sin roles ni login — es una app de una sola noche.

El sorteo en sí (elegir al azar + animación de ruleta) se hace en el frontend a
partir de la lista de /participantes; acá sólo servimos los datos y persistimos
la exclusión del que ya ganó.
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from murga import models as m


router = APIRouter(prefix="/api/murga", tags=["murga"])

# Token de acceso a las vistas del presentador. En prod se setea por env var en
# Render; el fallback es sólo para desarrollo local. Cambialo antes del estreno.
_TOKEN = os.environ.get("SORTEO_TOKEN") or "abuela2026"


def require_token(k: Optional[str] = Query(None)) -> bool:
    """Valida el token que viaja en la query string (?k=...)."""
    if not k or k != _TOKEN:
        raise HTTPException(status_code=401, detail="Acceso restringido.")
    return True


def _full(p: m.Participante) -> dict:
    return {
        "id": p.id,
        "nombre": p.nombre,
        "celular": p.celular,
        "voluntad": p.voluntad,
        "excluido": bool(p.excluido),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ---------------------------------------------------------
# Público — inscripción desde el formulario (QR)
# ---------------------------------------------------------
@router.post("/registrar")
def registrar(payload: m.ParticipanteIn, db: Session = Depends(get_db)):
    nombre = (payload.nombre or "").strip()
    celular = (payload.celular or "").strip()
    voluntad = (payload.voluntad or "").strip()
    if not nombre or not celular or not voluntad:
        raise HTTPException(status_code=400, detail="Completá los tres campos.")
    p = m.Participante(nombre=nombre, celular=celular, voluntad=voluntad)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"ok": True, "nombre": p.nombre}


# ---------------------------------------------------------
# Presentador (token en la URL)
# ---------------------------------------------------------
@router.get("/voluntades")
def listar_voluntades(_: bool = Depends(require_token), db: Session = Depends(get_db)):
    """Para proyectar en vivo: SÓLO nombre + última voluntad (nunca el celular),
    de la más reciente a la más vieja."""
    rows = (
        db.query(m.Participante)
        .order_by(m.Participante.created_at.desc(), m.Participante.id.desc())
        .all()
    )
    return {
        "total": len(rows),
        "voluntades": [{"nombre": r.nombre, "voluntad": r.voluntad} for r in rows],
    }


@router.get("/participantes")
def listar_participantes(_: bool = Depends(require_token), db: Session = Depends(get_db)):
    """Datos completos para el sorteo y el export (incluye celular)."""
    rows = (
        db.query(m.Participante)
        .order_by(m.Participante.created_at.asc(), m.Participante.id.asc())
        .all()
    )
    return {"total": len(rows), "participantes": [_full(r) for r in rows]}


@router.post("/participantes/{pid}/excluir")
def excluir(
    pid: int,
    payload: m.ExcluirIn,
    _: bool = Depends(require_token),
    db: Session = Depends(get_db),
):
    """Marca (o desmarca) a un participante como ya sorteado, para sacarlo de un
    re-sorteo. Se persiste para que sobreviva a un refresh de la página."""
    p = db.query(m.Participante).filter(m.Participante.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="No encontrado")
    p.excluido = bool(payload.excluido)
    db.commit()
    return {"ok": True, "id": p.id, "excluido": p.excluido}


@router.post("/reset")
def reset(_: bool = Depends(require_token), db: Session = Depends(get_db)):
    """Borra TODOS los inscriptos. Sirve para limpiar los datos de prueba antes
    del estreno (y para vaciar todo después). Irreversible — el frontend pide
    confirmación antes de llamarlo."""
    borrados = db.query(m.Participante).delete()
    db.commit()
    return {"ok": True, "borrados": borrados}
