"""
Router del módulo Métricas FBCR.

Público (lo consume el dashboard):
  - GET /api/metricas/programas           → catálogo + mini-agregados por programa
  - GET /api/metricas/instancias          → instancias (filtrable por ?programa=slug)
  - GET /api/metricas/kpis                → KPIs de impacto acumulado

Admin (require_auth — lo consume el formulario):
  - POST   /api/metricas/instancias       → alta
  - PUT    /api/metricas/instancias/{id}  → edición
  - DELETE /api/metricas/instancias/{id}  → baja
  - GET    /api/metricas/export.csv       → descarga CSV
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db

from . import source
from .models import Instancia, Programa


router = APIRouter(prefix="/api/metricas", tags=["metricas"])


# --- Schemas --------------------------------------------------------------
class InstanciaIn(BaseModel):
    programa_id: int
    titulo: str = Field(..., min_length=1, max_length=300)
    anio: Optional[int] = None
    fecha: Optional[date] = None
    fecha_texto: Optional[str] = Field("", max_length=120)
    modalidad: Optional[str] = Field("", max_length=120)
    localidades: Optional[str] = ""
    personas: Optional[int] = None
    proyectos: Optional[int] = None
    osc: Optional[int] = None
    escuelas: Optional[int] = None
    mentores: Optional[int] = None
    monto: Optional[float] = None
    ganadores: Optional[str] = ""
    reconocimiento: Optional[str] = ""
    notas: Optional[str] = ""
    orden: Optional[int] = 0


class InstanciaOut(BaseModel):
    id: int
    programa_id: int
    titulo: str
    anio: Optional[int]
    fecha: Optional[date]
    fecha_texto: str
    modalidad: str
    localidades: str
    personas: Optional[int]
    proyectos: Optional[int]
    osc: Optional[int]
    escuelas: Optional[int]
    mentores: Optional[int]
    monto: Optional[float]
    ganadores: str
    reconocimiento: str
    notas: str
    orden: int

    class Config:
        from_attributes = True


class ProgramaOut(BaseModel):
    id: int
    slug: str
    nombre: str
    descripcion: str
    icono: str
    color: str
    orden: int
    # Agregados calculados
    total_instancias: int = 0
    total_personas: int = 0
    anio_min: Optional[int] = None
    anio_max: Optional[int] = None


# --- Endpoints públicos ---------------------------------------------------
# Leen de source.load(): Google Sheet publicado (si está configurado) o la DB.
@router.get("/config")
def config() -> dict:
    """Le dice al frontend de dónde salen los datos y dónde se editan."""
    return {
        "read_only": source.sheet_configured(),
        "source": "sheet" if source.sheet_configured() else "db",
        "edit_url": source.SHEET_EDIT_URL,
    }


@router.get("/programas", response_model=list[ProgramaOut])
def listar_programas(
    fresh: bool = False,
    db: Session = Depends(get_db),
) -> list[ProgramaOut]:
    data = source.load(db, fresh=fresh)
    # Agregados por programa.
    agg: dict[int, dict] = {}
    for i in data["instancias"]:
        a = agg.setdefault(i["programa_id"], {"cnt": 0, "personas": 0, "amin": None, "amax": None})
        a["cnt"] += 1
        a["personas"] += i.get("personas") or 0
        anio = i.get("anio")
        if anio is not None:
            a["amin"] = anio if a["amin"] is None else min(a["amin"], anio)
            a["amax"] = anio if a["amax"] is None else max(a["amax"], anio)

    out: list[ProgramaOut] = []
    for p in data["programas"]:
        a = agg.get(p["id"], {"cnt": 0, "personas": 0, "amin": None, "amax": None})
        out.append(ProgramaOut(
            id=p["id"], slug=p["slug"], nombre=p["nombre"], descripcion=p.get("descripcion", ""),
            icono=p.get("icono", ""), color=p.get("color", "#0ea5e9"), orden=p.get("orden", 0),
            total_instancias=a["cnt"], total_personas=a["personas"],
            anio_min=a["amin"], anio_max=a["amax"],
        ))
    return out


@router.get("/instancias", response_model=list[InstanciaOut])
def listar_instancias(
    programa: Optional[str] = None,
    fresh: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    data = source.load(db, fresh=fresh)
    insts = data["instancias"]
    if programa:
        prog = next((p for p in data["programas"] if p["slug"] == programa), None)
        if not prog:
            raise HTTPException(status_code=404, detail="Programa no encontrado")
        insts = [i for i in insts if i["programa_id"] == prog["id"]]
    return sorted(insts, key=lambda i: (i.get("anio") or 0, i.get("orden") or 0, i["id"]))


@router.get("/kpis")
def kpis(fresh: bool = False, db: Session = Depends(get_db)) -> dict:
    data = source.load(db, fresh=fresh)
    insts = data["instancias"]

    def total(field):
        return sum(i.get(field) or 0 for i in insts)

    anios = [i["anio"] for i in insts if i.get("anio") is not None]
    anio_min = min(anios) if anios else None
    anio_max = max(anios) if anios else None
    anios_trayectoria = (anio_max - anio_min + 1) if (anio_min and anio_max) else 0

    por_anio_map: dict[int, int] = {}
    for i in insts:
        if i.get("anio") is not None:
            por_anio_map[i["anio"]] = por_anio_map.get(i["anio"], 0) + (i.get("personas") or 0)
    por_anio = [{"anio": a, "personas": por_anio_map[a]} for a in sorted(por_anio_map)]

    return {
        "total_personas": total("personas"),
        "total_proyectos": total("proyectos"),
        "total_osc": total("osc"),
        "total_escuelas": total("escuelas"),
        "total_instancias": len(insts),
        "anio_min": anio_min,
        "anio_max": anio_max,
        "anios_trayectoria": anios_trayectoria,
        "por_anio": por_anio,
        "data_source": data["source"],
    }


# --- Endpoints admin ------------------------------------------------------
def _guard_writable() -> None:
    """Cuando el Google Sheet es la fuente, la edición va por el Sheet, no por acá."""
    if source.sheet_configured():
        raise HTTPException(
            status_code=409,
            detail="La fuente de datos es el Google Sheet. Editá ahí; el formulario está deshabilitado.",
        )


@router.post("/instancias", response_model=InstanciaOut, status_code=201)
def crear_instancia(
    payload: InstanciaIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> Instancia:
    _guard_writable()
    if not db.get(Programa, payload.programa_id):
        raise HTTPException(status_code=400, detail="programa_id inválido")
    inst = Instancia(**payload.model_dump())
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.put("/instancias/{inst_id}", response_model=InstanciaOut)
def editar_instancia(
    inst_id: int,
    payload: InstanciaIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> Instancia:
    _guard_writable()
    inst = db.get(Instancia, inst_id)
    if not inst:
        raise HTTPException(status_code=404, detail="No encontrada")
    if not db.get(Programa, payload.programa_id):
        raise HTTPException(status_code=400, detail="programa_id inválido")
    for k, v in payload.model_dump().items():
        setattr(inst, k, v)
    db.commit()
    db.refresh(inst)
    return inst


@router.delete("/instancias/{inst_id}", status_code=204)
def borrar_instancia(
    inst_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> None:
    _guard_writable()
    inst = db.get(Instancia, inst_id)
    if not inst:
        raise HTTPException(status_code=404, detail="No encontrada")
    db.delete(inst)
    db.commit()


@router.get("/export.csv")
def exportar_csv(
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> StreamingResponse:
    # Exporta lo que se está mostrando (Sheet si está configurado, o la DB).
    data = source.load(db)
    prog_nombre = {p["id"]: p["nombre"] for p in data["programas"]}
    prog_orden = {p["id"]: p.get("orden", 0) for p in data["programas"]}
    rows = sorted(
        data["instancias"],
        key=lambda i: (prog_orden.get(i["programa_id"], 0), i.get("anio") or 0, i.get("orden") or 0),
    )

    def cell(v):
        return "" if v is None else v

    buf = io.StringIO()
    buf.write("﻿")  # BOM para que Excel abra UTF-8 sin romper acentos
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "programa", "titulo", "anio", "fecha", "fecha_texto", "modalidad",
        "localidades", "personas", "proyectos", "osc", "escuelas", "mentores",
        "monto", "ganadores", "reconocimiento", "notas",
    ])
    for i in rows:
        writer.writerow([
            prog_nombre.get(i["programa_id"], ""), i["titulo"], cell(i.get("anio")),
            cell(i.get("fecha")), i.get("fecha_texto", ""),
            i.get("modalidad", ""), i.get("localidades", ""),
            cell(i.get("personas")), cell(i.get("proyectos")), cell(i.get("osc")),
            cell(i.get("escuelas")), cell(i.get("mentores")), cell(i.get("monto")),
            i.get("ganadores", ""), i.get("reconocimiento", ""), i.get("notas", ""),
        ])
    buf.seek(0)
    fname = f"metricas-fbcr-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
