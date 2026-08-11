"""
API del módulo Corte — encuesta de la versión reducida. Prefijo /api/corte.

- Bloques (GET /bloques) y responder (POST /responder) + recuperar la propia
  respuesta (GET /mine): PÚBLICO, sin login. Upsert por nombre.
- Resultados (GET /resultados): protegido por token en la URL (?k=, env
  CORTE_TOKEN), para que solo el organizador vea el ranking.

El total de duración se calcula SIEMPRE server-side (data.duracion_de) contra
las duraciones reales; nunca se confía en lo que manda el cliente. Si la
selección supera el máximo (35'), se rechaza con 400.
"""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from corte import data
from corte import models as m


router = APIRouter(prefix="/api/corte", tags=["corte"])

# Token para ver resultados. En prod se setea por env var; el fallback es solo
# para desarrollo local.
_TOKEN = os.environ.get("CORTE_TOKEN") or "corte2026"


def require_token(k: Optional[str] = Query(None)) -> bool:
    if not k or k != _TOKEN:
        raise HTTPException(status_code=401, detail="Acceso restringido.")
    return True


def _seleccion(r: m.CorteRespuesta):
    try:
        s = json.loads(r.seleccion or "[]")
        return [int(x) for x in s] if isinstance(s, list) else []
    except Exception:
        return []


# ---------------------------------------------------------
# Público
# ---------------------------------------------------------
@router.get("/bloques")
def get_bloques():
    """Bloques del espectáculo + objetivo/máximo, para armar la encuesta."""
    return {
        "grupos": data.GRUPOS,
        "bloques": data.BLOQUES,
        "objetivo_seg": data.OBJETIVO_SEG,
        "max_seg": data.MAX_SEG,
    }


@router.get("/nombres")
def nombres(db: Session = Depends(get_db)):
    """Roster de murguistas + cuáles ya respondieron (para deshabilitarlos)."""
    rows = db.query(m.CorteRespuesta.nombre).all()
    tomados = {(r[0] or "").strip().lower() for r in rows}
    return {"nombres": [{"nombre": n, "tomado": n.lower() in tomados} for n in data.NOMBRES]}


def _canonico(nombre):
    """Devuelve el nombre del roster que coincide (case-insensitive), o None."""
    n = (nombre or "").strip().lower()
    for x in data.NOMBRES:
        if x.lower() == n:
            return x
    return None


@router.post("/responder")
def responder(payload: m.RespuestaIn, db: Session = Depends(get_db)):
    nombre = _canonico(payload.nombre)
    if not nombre:
        raise HTTPException(status_code=400, detail="Elegí tu nombre de la lista.")

    # Ids válidos, sin duplicados, preservando sólo los que existen.
    ids = [i for i in dict.fromkeys(payload.seleccion or []) if i in data.BLOQUES_POR_ID]
    if not ids:
        raise HTTPException(status_code=400, detail="Elegí al menos una parte.")

    total = data.duracion_de(ids)
    if total > data.MAX_SEG:
        raise HTTPException(
            status_code=400,
            detail="Tu selección supera el máximo de 35 minutos. Sacá alguna parte.",
        )

    # Una sola respuesta por murguista: si el nombre ya cargó, se rechaza.
    existing = db.query(m.CorteRespuesta).filter(
        func.lower(m.CorteRespuesta.nombre) == nombre.lower()
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ese nombre ya cargó su selección.")

    db.add(m.CorteRespuesta(nombre=nombre, seleccion=json.dumps(ids), total_seg=total))
    db.commit()
    return {"ok": True, "total_seg": total}


@router.get("/mine")
def get_mine(name: str, db: Session = Depends(get_db)):
    """Devuelve SÓLO la selección previa de esa persona, para poder editarla."""
    n = (name or "").strip().lower()
    if not n:
        return {"seleccion": [], "total_seg": 0, "existe": False}
    r = db.query(m.CorteRespuesta).filter(func.lower(m.CorteRespuesta.nombre) == n).first()
    if not r:
        return {"seleccion": [], "total_seg": 0, "existe": False}
    return {"seleccion": _seleccion(r), "total_seg": r.total_seg or 0, "existe": True}


# ---------------------------------------------------------
# Resultados (organizador — token en la URL)
# ---------------------------------------------------------
@router.get("/resultados")
def resultados(_: bool = Depends(require_token), db: Session = Depends(get_db)):
    rows = db.query(m.CorteRespuesta).all()
    total_personas = len(rows)

    # Conteo de votos por bloque.
    votos = {b["id"]: 0 for b in data.BLOQUES}
    for r in rows:
        for i in _seleccion(r):
            if i in votos:
                votos[i] += 1

    bloques = []
    for b in data.BLOQUES:
        v = votos[b["id"]]
        pct = round(100 * v / total_personas) if total_personas else 0
        bloques.append({
            "id": b["id"],
            "nombre": b["nombre"],
            "tipo": b["tipo"],
            "grupo": b["grupo"],
            "dur": b["dur"],
            "votos": v,
            "pct": pct,
        })

    return {
        "total_personas": total_personas,
        "grupos": data.GRUPOS,
        "objetivo_seg": data.OBJETIVO_SEG,
        "max_seg": data.MAX_SEG,
        "bloques": bloques,
    }


@router.post("/reset")
def reset(_: bool = Depends(require_token), db: Session = Depends(get_db)):
    """Borra TODAS las respuestas de la encuesta (limpiar pruebas / resetear).
    Irreversible — el frontend pide confirmación antes de llamarlo."""
    borradas = db.query(m.CorteRespuesta).delete()
    db.commit()
    return {"ok": True, "borradas": borradas}
