"""
API del módulo Canciones (versión B). Prefijo /api/canciones. Mismo diseño que
`corte` pero con la lista de canciones y sin campo `tipo`.

- Nombres (GET /nombres), canciones (GET /bloques) y responder (POST /responder):
  PÚBLICO. Una respuesta por murguista (nombre del roster; reintento → 409).
- Resultados (GET /resultados) y reset (POST /reset): token en la URL (?k=, env
  CANCIONES_TOKEN).
"""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from canciones import data
from canciones import models as m


router = APIRouter(prefix="/api/canciones", tags=["canciones"])

_TOKEN = os.environ.get("CANCIONES_TOKEN") or "canciones2026"


def require_token(k: Optional[str] = Query(None)) -> bool:
    if not k or k != _TOKEN:
        raise HTTPException(status_code=401, detail="Acceso restringido.")
    return True


def _seleccion(r: m.CancionRespuesta):
    try:
        s = json.loads(r.seleccion or "[]")
        return [int(x) for x in s] if isinstance(s, list) else []
    except Exception:
        return []


def _canonico(nombre):
    n = (nombre or "").strip().lower()
    for x in data.NOMBRES:
        if x.lower() == n:
            return x
    return None


# ---------------------------------------------------------
# Público
# ---------------------------------------------------------
@router.get("/bloques")
def get_bloques():
    return {
        "grupos": data.GRUPOS,
        "bloques": data.BLOQUES,
        "objetivo_seg": data.OBJETIVO_SEG,
        "max_seg": data.MAX_SEG,
    }


@router.get("/nombres")
def nombres(db: Session = Depends(get_db)):
    rows = db.query(m.CancionRespuesta.nombre).all()
    tomados = {(r[0] or "").strip().lower() for r in rows}
    return {"nombres": [{"nombre": n, "tomado": n.lower() in tomados} for n in data.NOMBRES]}


@router.post("/responder")
def responder(payload: m.RespuestaIn, db: Session = Depends(get_db)):
    nombre = _canonico(payload.nombre)
    if not nombre:
        raise HTTPException(status_code=400, detail="Elegí tu nombre de la lista.")

    ids = [i for i in dict.fromkeys(payload.seleccion or []) if i in data.BLOQUES_POR_ID]
    if not ids:
        raise HTTPException(status_code=400, detail="Elegí al menos una canción.")

    total = data.duracion_de(ids)
    if total > data.MAX_SEG:
        raise HTTPException(
            status_code=400,
            detail="Tu selección supera el máximo de 35 minutos. Sacá alguna canción.",
        )

    existing = db.query(m.CancionRespuesta).filter(
        func.lower(m.CancionRespuesta.nombre) == nombre.lower()
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ese nombre ya cargó su selección.")

    db.add(m.CancionRespuesta(nombre=nombre, seleccion=json.dumps(ids), total_seg=total))
    db.commit()
    return {"ok": True, "total_seg": total}


# ---------------------------------------------------------
# Resultados (organizador — token en la URL)
# ---------------------------------------------------------
@router.get("/resultados")
def resultados(_: bool = Depends(require_token), db: Session = Depends(get_db)):
    rows = db.query(m.CancionRespuesta).all()
    total_personas = len(rows)

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
    borradas = db.query(m.CancionRespuesta).delete()
    db.commit()
    return {"ok": True, "borradas": borradas}
