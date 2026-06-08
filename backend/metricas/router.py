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
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db

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


# --- Helpers --------------------------------------------------------------
def _sum(db: Session, column, **filters) -> int:
    q = db.query(func.coalesce(func.sum(column), 0))
    if filters.get("programa_id"):
        q = q.filter(Instancia.programa_id == filters["programa_id"])
    return int(q.scalar() or 0)


# --- Endpoints públicos ---------------------------------------------------
@router.get("/programas", response_model=list[ProgramaOut])
def listar_programas(db: Session = Depends(get_db)) -> list[ProgramaOut]:
    programas = (
        db.query(Programa)
        .filter(Programa.activo == 1)
        .order_by(Programa.orden, Programa.id)
        .all()
    )

    # Agregados por programa en una sola query.
    agg = dict(
        (row[0], row)
        for row in db.query(
            Instancia.programa_id,
            func.count(Instancia.id),
            func.coalesce(func.sum(Instancia.personas), 0),
            func.min(Instancia.anio),
            func.max(Instancia.anio),
        ).group_by(Instancia.programa_id).all()
    )

    out: list[ProgramaOut] = []
    for p in programas:
        _, cnt, personas, amin, amax = agg.get(p.id, (p.id, 0, 0, None, None))
        out.append(ProgramaOut(
            id=p.id, slug=p.slug, nombre=p.nombre, descripcion=p.descripcion or "",
            icono=p.icono or "", color=p.color or "#0ea5e9", orden=p.orden or 0,
            total_instancias=int(cnt), total_personas=int(personas or 0),
            anio_min=amin, anio_max=amax,
        ))
    return out


@router.get("/instancias", response_model=list[InstanciaOut])
def listar_instancias(
    programa: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[Instancia]:
    q = db.query(Instancia)
    if programa:
        prog = db.query(Programa).filter(Programa.slug == programa).first()
        if not prog:
            raise HTTPException(status_code=404, detail="Programa no encontrado")
        q = q.filter(Instancia.programa_id == prog.id)
    return q.order_by(
        Instancia.anio.asc().nullslast(),
        Instancia.orden.asc(),
        Instancia.id.asc(),
    ).all()


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)) -> dict:
    total_personas = _sum(db, Instancia.personas)
    total_proyectos = _sum(db, Instancia.proyectos)
    total_osc = _sum(db, Instancia.osc)
    total_escuelas = _sum(db, Instancia.escuelas)
    total_instancias = db.query(func.count(Instancia.id)).scalar() or 0

    anio_min = db.query(func.min(Instancia.anio)).scalar()
    anio_max = db.query(func.max(Instancia.anio)).scalar()
    anios_trayectoria = (anio_max - anio_min + 1) if (anio_min and anio_max) else 0

    # Personas por año (para el gráfico de evolución).
    por_anio = [
        {"anio": row[0], "personas": int(row[1] or 0)}
        for row in db.query(
            Instancia.anio, func.coalesce(func.sum(Instancia.personas), 0)
        ).filter(Instancia.anio.isnot(None)).group_by(Instancia.anio).order_by(Instancia.anio).all()
    ]

    return {
        "total_personas": total_personas,
        "total_proyectos": total_proyectos,
        "total_osc": total_osc,
        "total_escuelas": total_escuelas,
        "total_instancias": int(total_instancias),
        "anio_min": anio_min,
        "anio_max": anio_max,
        "anios_trayectoria": anios_trayectoria,
        "por_anio": por_anio,
    }


# --- Endpoints admin ------------------------------------------------------
@router.post("/instancias", response_model=InstanciaOut, status_code=201)
def crear_instancia(
    payload: InstanciaIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
) -> Instancia:
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
    rows = (
        db.query(Instancia, Programa)
        .join(Programa, Instancia.programa_id == Programa.id)
        .order_by(Programa.orden, Instancia.anio, Instancia.orden)
        .all()
    )
    buf = io.StringIO()
    buf.write("﻿")  # BOM para que Excel abra UTF-8 sin romper acentos
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "programa", "titulo", "anio", "fecha", "fecha_texto", "modalidad",
        "localidades", "personas", "proyectos", "osc", "escuelas", "mentores",
        "monto", "ganadores", "reconocimiento", "notas",
    ])
    for inst, prog in rows:
        writer.writerow([
            prog.nombre, inst.titulo, inst.anio or "",
            inst.fecha.isoformat() if inst.fecha else "", inst.fecha_texto or "",
            inst.modalidad or "", inst.localidades or "",
            inst.personas if inst.personas is not None else "",
            inst.proyectos if inst.proyectos is not None else "",
            inst.osc if inst.osc is not None else "",
            inst.escuelas if inst.escuelas is not None else "",
            inst.mentores if inst.mentores is not None else "",
            inst.monto if inst.monto is not None else "",
            inst.ganadores or "", inst.reconocimiento or "", inst.notas or "",
        ])
    buf.seek(0)
    fname = f"metricas-fbcr-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
