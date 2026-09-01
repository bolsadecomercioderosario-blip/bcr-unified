"""
API del panel interno de la murga. Prefijo /api/abuela.

Todo requiere contraseña (env ABUELA_PASSWORD; el cliente la manda como
Authorization: Bearer <password>). Es uso interno, sin roles.
Secciones: caja, remeras, ensayos, toques, roster.
"""
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from abuela import models as m


router = APIRouter(prefix="/api/abuela", tags=["abuela"])

_PASSWORD = os.environ.get("ABUELA_PASSWORD") or "laabuela2026"


def require_auth(authorization: Optional[str] = Header(None)) -> bool:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token != _PASSWORD:
        raise HTTPException(status_code=401, detail="Acceso restringido.")
    return True


A = Depends(require_auth)


# ---------------------------------------------------------
# Auth
# ---------------------------------------------------------
@router.post("/login")
def login(payload: dict):
    if (payload.get("password") or "") != _PASSWORD:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    return {"ok": True, "token": _PASSWORD}


# ---------------------------------------------------------
# Roster
# ---------------------------------------------------------
@router.get("/roster")
def roster(_: bool = A, db: Session = Depends(get_db)):
    rows = db.query(m.Murguista).order_by(m.Murguista.activo.desc(), m.Murguista.orden).all()
    return {"murguistas": [
        {"id": r.id, "nombre": r.nombre, "nombre_completo": r.nombre_completo, "activo": bool(r.activo)}
        for r in rows
    ]}


# ---------------------------------------------------------
# Caja
# ---------------------------------------------------------
@router.get("/caja")
def caja_resumen(_: bool = A, db: Session = Depends(get_db)):
    real = db.query(m.CajaMov).filter(m.CajaMov.proyectado == False).all()  # noqa: E712
    cuentas = {}
    for mv in real:
        c = cuentas.setdefault(mv.cuenta or "—", {"cuenta": mv.cuenta or "—", "ingresos": 0.0, "egresos": 0.0})
        if (mv.tipo or "").lower() == "ingreso":
            c["ingresos"] += mv.monto
        else:
            c["egresos"] += mv.monto
    for c in cuentas.values():
        c["saldo"] = c["ingresos"] - c["egresos"]
    ingresos = sum(c["ingresos"] for c in cuentas.values())
    egresos = sum(c["egresos"] for c in cuentas.values())

    proj = db.query(m.CajaMov).filter(m.CajaMov.proyectado == True).all()  # noqa: E712
    p_ing = sum(x.monto for x in proj if (x.tipo or "").lower() == "ingreso")
    p_egr = sum(x.monto for x in proj if (x.tipo or "").lower() == "egreso")
    saldo = ingresos - egresos
    return {
        "cuentas": sorted(cuentas.values(), key=lambda c: -c["saldo"]),
        "ingresos": ingresos, "egresos": egresos, "saldo": saldo,
        "proy_ingresos": p_ing, "proy_egresos": p_egr,
        "saldo_proyectado": saldo + p_ing - p_egr,
    }


def _mov_out(mv):
    return {"id": mv.id, "fecha": mv.fecha, "cuenta": mv.cuenta, "tipo": mv.tipo,
            "monto": mv.monto, "concepto": mv.concepto, "proyectado": bool(mv.proyectado)}


@router.get("/caja/movimientos")
def caja_movimientos(proyectado: bool = False, _: bool = A, db: Session = Depends(get_db)):
    q = db.query(m.CajaMov).filter(m.CajaMov.proyectado == proyectado)
    q = q.order_by(m.CajaMov.fecha.desc(), m.CajaMov.id.desc())
    return {"movimientos": [_mov_out(x) for x in q.all()]}


@router.post("/caja/movimientos")
def caja_add(payload: m.MovIn, _: bool = A, db: Session = Depends(get_db)):
    if payload.monto is None or payload.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto tiene que ser mayor a 0.")
    tipo = "Ingreso" if (payload.tipo or "").lower().startswith("ing") else "Egreso"
    mv = m.CajaMov(fecha=(payload.fecha or "")[:10], cuenta=payload.cuenta.strip(),
                   tipo=tipo, monto=float(payload.monto), concepto=payload.concepto.strip(),
                   proyectado=bool(payload.proyectado))
    db.add(mv); db.commit(); db.refresh(mv)
    return _mov_out(mv)


@router.delete("/caja/movimientos/{mid}")
def caja_del(mid: int, _: bool = A, db: Session = Depends(get_db)):
    mv = db.query(m.CajaMov).filter(m.CajaMov.id == mid).first()
    if not mv:
        raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(mv); db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# Remeras
# ---------------------------------------------------------
@router.get("/remeras")
def remeras(_: bool = A, db: Session = Depends(get_db)):
    rows = db.query(m.Remera).order_by(m.Remera.pago, func.lower(m.Remera.nombre)).all()
    pagas = [r for r in rows if r.pago]
    return {
        "remeras": [{"id": r.id, "nombre": r.nombre, "pago": bool(r.pago), "monto": r.monto, "nota": r.nota} for r in rows],
        "pagas": len(pagas), "deben": len(rows) - len(pagas),
        "recaudado": sum(r.monto for r in pagas),
    }


@router.post("/remeras")
def remera_add(payload: m.RemeraIn, _: bool = A, db: Session = Depends(get_db)):
    nombre = (payload.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Falta el nombre.")
    r = m.Remera(nombre=nombre, pago=bool(payload.pago), monto=float(payload.monto or 20000), nota=payload.nota.strip())
    db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id, "nombre": r.nombre, "pago": bool(r.pago), "monto": r.monto, "nota": r.nota}


@router.post("/remeras/{rid}/toggle")
def remera_toggle(rid: int, _: bool = A, db: Session = Depends(get_db)):
    r = db.query(m.Remera).filter(m.Remera.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="No encontrado")
    r.pago = not r.pago; db.commit()
    return {"id": r.id, "pago": bool(r.pago)}


@router.delete("/remeras/{rid}")
def remera_del(rid: int, _: bool = A, db: Session = Depends(get_db)):
    r = db.query(m.Remera).filter(m.Remera.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(r); db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# Ensayos (asistencia)
# ---------------------------------------------------------
@router.get("/ensayos/periodos")
def ensayo_periodos(_: bool = A, db: Session = Depends(get_db)):
    rows = db.query(m.Ensayo.periodo, func.count(m.Ensayo.id)).group_by(m.Ensayo.periodo).all()
    # ordenar por nombre de periodo descendente (los más nuevos primero)
    periodos = sorted([{"periodo": p, "ensayos": n} for p, n in rows], key=lambda x: x["periodo"], reverse=True)
    return {"periodos": periodos}


@router.get("/ensayos")
def ensayo_lista(periodo: str, _: bool = A, db: Session = Depends(get_db)):
    rows = db.query(m.Ensayo).filter(m.Ensayo.periodo == periodo).order_by(m.Ensayo.orden, m.Ensayo.fecha).all()
    ids = [e.id for e in rows]
    counts = {}
    if ids:
        for eid, n in db.query(m.EnsayoAsist.ensayo_id, func.count(m.EnsayoAsist.id)).filter(
                m.EnsayoAsist.ensayo_id.in_(ids)).group_by(m.EnsayoAsist.ensayo_id).all():
            counts[eid] = n
    return {"ensayos": [{"id": e.id, "fecha": e.fecha, "marcas": counts.get(e.id, 0)} for e in rows]}


@router.get("/ensayos/id/{eid}")
def ensayo_detalle(eid: int, _: bool = A, db: Session = Depends(get_db)):
    e = db.query(m.Ensayo).filter(m.Ensayo.id == eid).first()
    if not e:
        raise HTTPException(status_code=404, detail="No encontrado")
    marcas = {a.nombre: a.codigo for a in db.query(m.EnsayoAsist).filter(m.EnsayoAsist.ensayo_id == eid).all()}
    return {"id": e.id, "periodo": e.periodo, "fecha": e.fecha, "marcas": marcas}


_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _sortkey(e):
    """Ordena por fecha: las ISO cronológicamente, las no-ISO (viejas raras) al fondo."""
    f = e.fecha or ""
    return f if _ISO.match(f) else "0000-00-00"


@router.post("/ensayos")
def ensayo_crear(payload: m.EnsayoIn, _: bool = A, db: Session = Depends(get_db)):
    fecha = (payload.fecha or "").strip()
    if not fecha:
        raise HTTPException(status_code=400, detail="Elegí una fecha.")
    # El período ya no se usa para agrupar (registro histórico único); se guarda
    # el año como etiqueta interna nomás.
    periodo = (payload.periodo or "").strip() or (fecha[:4] if _ISO.match(fecha) else "Registro")
    maxo = db.query(func.max(m.Ensayo.orden)).scalar() or 0
    e = m.Ensayo(periodo=periodo, fecha=fecha, orden=maxo + 1)
    db.add(e); db.commit(); db.refresh(e)
    return {"id": e.id, "fecha": e.fecha}


@router.get("/ensayos/todos")
def ensayo_todos(_: bool = A, db: Session = Depends(get_db)):
    """Todos los ensayos (registro histórico), del más nuevo al más viejo."""
    rows = sorted(db.query(m.Ensayo).all(), key=_sortkey, reverse=True)
    ids = [e.id for e in rows]
    counts = {}
    if ids:
        for eid, n in db.query(m.EnsayoAsist.ensayo_id, func.count(m.EnsayoAsist.id)).filter(
                m.EnsayoAsist.ensayo_id.in_(ids)).group_by(m.EnsayoAsist.ensayo_id).all():
            counts[eid] = n
    return {"ensayos": [{"id": e.id, "fecha": e.fecha, "marcas": counts.get(e.id, 0)} for e in rows]}


@router.get("/ensayos/puntaje")
def ensayo_puntaje(desde: str = "", _: bool = A, db: Session = Depends(get_db)):
    """Ranking de puntaje sobre los ensayos con fecha >= desde (ISO). Sin desde = todo."""
    ens = db.query(m.Ensayo).all()

    def en_rango(e):
        f = e.fecha or ""
        if not _ISO.match(f):
            return not desde       # las no-ISO solo entran en "Todo"
        return (not desde) or (f[:10] >= desde)

    eids = [e.id for e in ens if en_rango(e)]
    activos = {r.nombre for r in db.query(m.Murguista).filter(m.Murguista.activo == True).all()}  # noqa: E712
    agg = {}
    if eids:
        for a in db.query(m.EnsayoAsist).filter(m.EnsayoAsist.ensayo_id.in_(eids)).all():
            d = agg.setdefault(a.nombre, {"nombre": a.nombre, "puntaje": 0.0, "P": 0, "T": 0, "M": 0, "A": 0, "X": 0})
            d["puntaje"] += m.PUNTAJE.get(a.codigo, 0)
            if a.codigo in d:
                d[a.codigo] += 1
    # incluir activos sin marcas en el rango (puntaje 0)
    for nom in activos:
        agg.setdefault(nom, {"nombre": nom, "puntaje": 0.0, "P": 0, "T": 0, "M": 0, "A": 0, "X": 0})
    filas = sorted(agg.values(), key=lambda d: -d["puntaje"])
    for f in filas:
        f["puntaje"] = round(f["puntaje"], 1)
        f["activo"] = f["nombre"] in activos
    return {"desde": desde, "ensayos": len(eids), "ranking": filas}


@router.get("/ensayos/murguista")
def ensayo_murguista(nombre: str, limit: int = 16, _: bool = A, db: Session = Depends(get_db)):
    """Evolución reciente de un murguista: sus últimos N ensayos con el código."""
    ens = sorted(db.query(m.Ensayo).all(), key=_sortkey, reverse=True)[:max(1, min(limit, 40))]
    ids = [e.id for e in ens]
    marcas = {}
    if ids:
        for a in db.query(m.EnsayoAsist).filter(
                m.EnsayoAsist.nombre == nombre, m.EnsayoAsist.ensayo_id.in_(ids)).all():
            marcas[a.ensayo_id] = a.codigo
    evo = [{"fecha": e.fecha, "codigo": marcas.get(e.id, "")} for e in ens]
    pts = round(sum(m.PUNTAJE.get(x["codigo"], 0) for x in evo), 1)
    return {"nombre": nombre, "evolucion": evo, "puntaje": pts}


@router.post("/ensayos/marca")
def ensayo_marca(payload: m.MarcaIn, _: bool = A, db: Session = Depends(get_db)):
    cod = (payload.codigo or "").strip().upper()
    if cod == "MT":
        cod = "M"
    existing = db.query(m.EnsayoAsist).filter(
        m.EnsayoAsist.ensayo_id == payload.ensayo_id, m.EnsayoAsist.nombre == payload.nombre).first()
    if not cod:  # borrar marca
        if existing:
            db.delete(existing); db.commit()
        return {"ok": True, "codigo": ""}
    if cod not in m.PUNTAJE:
        raise HTTPException(status_code=400, detail="Código inválido.")
    if existing:
        existing.codigo = cod
    else:
        db.add(m.EnsayoAsist(ensayo_id=payload.ensayo_id, nombre=payload.nombre, codigo=cod))
    db.commit()
    return {"ok": True, "codigo": cod}


@router.delete("/ensayos/id/{eid}")
def ensayo_del(eid: int, _: bool = A, db: Session = Depends(get_db)):
    db.query(m.EnsayoAsist).filter(m.EnsayoAsist.ensayo_id == eid).delete()
    db.query(m.Ensayo).filter(m.Ensayo.id == eid).delete()
    db.commit()
    return {"ok": True}


@router.get("/ensayos/ranking/{periodo}")
def ensayo_ranking(periodo: str, _: bool = A, db: Session = Depends(get_db)):
    eids = [e.id for e in db.query(m.Ensayo.id).filter(m.Ensayo.periodo == periodo).all()]
    activos = {r.nombre for r in db.query(m.Murguista).filter(m.Murguista.activo == True).all()}  # noqa: E712
    agg = {}
    if eids:
        for a in db.query(m.EnsayoAsist).filter(m.EnsayoAsist.ensayo_id.in_(eids)).all():
            d = agg.setdefault(a.nombre, {"nombre": a.nombre, "puntaje": 0.0, "P": 0, "T": 0, "M": 0, "A": 0, "X": 0})
            d["puntaje"] += m.PUNTAJE.get(a.codigo, 0)
            if a.codigo in d:
                d[a.codigo] += 1
    filas = sorted(agg.values(), key=lambda d: -d["puntaje"])
    for f in filas:
        f["puntaje"] = round(f["puntaje"], 1)
        f["activo"] = f["nombre"] in activos
    return {"periodo": periodo, "ranking": filas}


# ---------------------------------------------------------
# Toques
# ---------------------------------------------------------
def _toque_out(t, full=False):
    d = {"id": t.id, "nombre": t.nombre, "fecha": t.fecha, "lugar": t.lugar,
         "evento": t.evento, "condicion_eco": t.condicion_eco, "orden": t.orden}
    if full:
        d.update({
            "duracion": t.duracion, "horario": t.horario, "sonido": t.sonido,
            "prueba_sonido": t.prueba_sonido, "camarin": t.camarin, "cachet": t.cachet,
            "factura": t.factura, "entradas": t.entradas, "viaticos": t.viaticos,
            "comida": t.comida, "bebida": t.bebida, "otros": t.otros, "contacto": t.contacto,
            "encargado": t.encargado, "repertorio": t.repertorio,
        })
    return d


@router.get("/toques")
def toque_lista(_: bool = A, db: Session = Depends(get_db)):
    rows = db.query(m.Toque).order_by(m.Toque.orden.desc(), m.Toque.id.desc()).all()
    return {"toques": [_toque_out(t) for t in rows]}


@router.get("/toques/{tid}")
def toque_detalle(tid: int, _: bool = A, db: Session = Depends(get_db)):
    t = db.query(m.Toque).filter(m.Toque.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="No encontrado")
    asist = {a.nombre: bool(a.subio) for a in db.query(m.ToqueAsist).filter(m.ToqueAsist.toque_id == tid).all()}
    out = _toque_out(t, full=True)
    out["asistencia"] = asist
    return out


@router.post("/toques")
def toque_crear(payload: m.ToqueIn, _: bool = A, db: Session = Depends(get_db)):
    nombre = (payload.nombre or payload.lugar or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Poné al menos el nombre o lugar del toque.")
    maxo = db.query(func.max(m.Toque.orden)).scalar() or 0
    data = payload.dict()
    data["nombre"] = nombre
    t = m.Toque(orden=maxo + 1, **data)
    db.add(t); db.commit(); db.refresh(t)
    return _toque_out(t, full=True)


@router.put("/toques/{tid}")
def toque_editar(tid: int, payload: m.ToqueIn, _: bool = A, db: Session = Depends(get_db)):
    t = db.query(m.Toque).filter(m.Toque.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="No encontrado")
    for k, v in payload.dict().items():
        setattr(t, k, v)
    if not t.nombre:
        t.nombre = t.lugar or "Toque"
    db.commit()
    return _toque_out(t, full=True)


@router.post("/toques/subio")
def toque_subio(payload: m.ToqueSubioIn, _: bool = A, db: Session = Depends(get_db)):
    a = db.query(m.ToqueAsist).filter(
        m.ToqueAsist.toque_id == payload.toque_id, m.ToqueAsist.nombre == payload.nombre).first()
    if a:
        a.subio = bool(payload.subio)
    else:
        db.add(m.ToqueAsist(toque_id=payload.toque_id, nombre=payload.nombre, subio=bool(payload.subio)))
    db.commit()
    return {"ok": True, "subio": bool(payload.subio)}


@router.delete("/toques/{tid}")
def toque_del(tid: int, _: bool = A, db: Session = Depends(get_db)):
    db.query(m.ToqueAsist).filter(m.ToqueAsist.toque_id == tid).delete()
    db.query(m.Toque).filter(m.Toque.id == tid).delete()
    db.commit()
    return {"ok": True}
