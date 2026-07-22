"""
API del módulo Aapresid 2026. Prefijo /api/aapresid.

Fase 1: login por usuario, estado del tablero (evento + turnos + áreas +
personas + presencias), ABM de áreas y personas, y CRUD de presencias
(crear/editar/borrar/mover/duplicar, sin duplicar persona en el mismo turno).
Todos los endpoints (menos login) requieren usuario autenticado.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from aapresid import models as m
from aapresid.auth import (
    require_user, require_admin, verify_password, make_token,
)


router = APIRouter(prefix="/api/aapresid", tags=["aapresid"])


# ---------------------------------------------------------
# Auth
# ---------------------------------------------------------
@router.post("/auth/login")
def login(payload: m.LoginIn, db: Session = Depends(get_db)):
    email = (payload.email or "").lower().strip()
    user = db.query(m.AapUser).filter(m.AapUser.email == email).first()
    if not user or not user.active or not verify_password(payload.password or "", user.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    return {"token": make_token(user.id), "user": m.UserOut.model_validate(user).model_dump()}


@router.get("/auth/me", response_model=m.UserOut)
def me(user: m.AapUser = Depends(require_user)):
    return user


# ---------------------------------------------------------
# Estado del tablero (una sola llamada; el front la usa también para polling)
# ---------------------------------------------------------
def _active_event(db: Session) -> m.AapEvent:
    ev = db.query(m.AapEvent).filter(m.AapEvent.active == True).first()  # noqa: E712
    if not ev:
        ev = db.query(m.AapEvent).first()
    if not ev:
        raise HTTPException(status_code=404, detail="No hay evento cargado")
    return ev


@router.get("/state")
def get_state(user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    ev = _active_event(db)
    shifts = db.query(m.AapShift).filter(
        m.AapShift.event_id == ev.id, m.AapShift.active == True,  # noqa: E712
    ).order_by(m.AapShift.date, m.AapShift.display_order).all()
    areas = db.query(m.AapArea).order_by(m.AapArea.name).all()
    people = db.query(m.AapPerson).order_by(m.AapPerson.full_name).all()
    attendance = db.query(m.AapAttendance).filter(m.AapAttendance.event_id == ev.id).all()
    return {
        "event": m.EventOut.model_validate(ev).model_dump(),
        "shifts": [m.ShiftOut.model_validate(s).model_dump() for s in shifts],
        "areas": [m.AreaOut.model_validate(a).model_dump() for a in areas],
        "people": [m.PersonOut.model_validate(p).model_dump() for p in people],
        "attendance": [m.AttendanceOut.model_validate(x).model_dump() for x in attendance],
    }


# ---------------------------------------------------------
# Áreas (config — admin)
# ---------------------------------------------------------
@router.post("/areas", response_model=m.AreaOut)
def create_area(payload: m.AreaIn, user: m.AapUser = Depends(require_admin), db: Session = Depends(get_db)):
    area = m.AapArea(**payload.model_dump())
    db.add(area); db.commit(); db.refresh(area)
    return area


@router.put("/areas/{area_id}", response_model=m.AreaOut)
def update_area(area_id: int, payload: m.AreaIn, user: m.AapUser = Depends(require_admin), db: Session = Depends(get_db)):
    area = db.query(m.AapArea).filter(m.AapArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área no encontrada")
    for k, v in payload.model_dump().items():
        setattr(area, k, v)
    db.commit(); db.refresh(area)
    return area


@router.delete("/areas/{area_id}")
def delete_area(area_id: int, user: m.AapUser = Depends(require_admin), db: Session = Depends(get_db)):
    area = db.query(m.AapArea).filter(m.AapArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área no encontrada")
    # No borrar si tiene personas asociadas: sólo se puede desactivar.
    if db.query(m.AapPerson).filter(m.AapPerson.area_id == area_id).count() > 0:
        raise HTTPException(
            status_code=409,
            detail="El área tiene personas asociadas. Desactivala en vez de eliminarla.",
        )
    db.delete(area); db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# Personas
# ---------------------------------------------------------
@router.post("/people", response_model=m.PersonOut)
def create_person(payload: m.PersonIn, user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    person = m.AapPerson(**payload.model_dump())
    db.add(person); db.commit(); db.refresh(person)
    return person


@router.put("/people/{person_id}", response_model=m.PersonOut)
def update_person(person_id: int, payload: m.PersonIn, user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    person = db.query(m.AapPerson).filter(m.AapPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    for k, v in payload.model_dump().items():
        setattr(person, k, v)
    db.commit(); db.refresh(person)
    return person


@router.delete("/people/{person_id}")
def delete_person(person_id: int, user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    person = db.query(m.AapPerson).filter(m.AapPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    refs = db.query(m.AapAttendance).filter(m.AapAttendance.person_id == person_id).count()
    if refs > 0:
        raise HTTPException(
            status_code=409,
            detail="La persona tiene presencias asignadas. Desactivala en vez de eliminarla.",
        )
    db.delete(person); db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# Presencias
# ---------------------------------------------------------
def _dup_exists(db: Session, shift_id: int, person_id: int, exclude_id: Optional[int] = None) -> bool:
    q = db.query(m.AapAttendance).filter(
        m.AapAttendance.shift_id == shift_id, m.AapAttendance.person_id == person_id,
    )
    if exclude_id:
        q = q.filter(m.AapAttendance.id != exclude_id)
    return q.count() > 0


@router.post("/attendance", response_model=m.AttendanceOut)
def create_attendance(payload: m.AttendanceIn, user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    ev = _active_event(db)
    shift = db.query(m.AapShift).filter(m.AapShift.id == payload.shift_id).first()
    if not shift:
        raise HTTPException(status_code=400, detail="Turno inválido")
    if _dup_exists(db, payload.shift_id, payload.person_id):
        raise HTTPException(status_code=409, detail="Esa persona ya está en este turno.")
    att = m.AapAttendance(
        event_id=ev.id, created_by=user.id, updated_by=user.id, **payload.model_dump(),
    )
    db.add(att); db.commit(); db.refresh(att)
    return att


@router.put("/attendance/{att_id}", response_model=m.AttendanceOut)
def update_attendance(att_id: int, payload: m.AttendanceUpdate, user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    att = db.query(m.AapAttendance).filter(m.AapAttendance.id == att_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Presencia no encontrada")
    data = payload.model_dump(exclude_unset=True)
    new_shift = data.get("shift_id", att.shift_id)
    new_person = data.get("person_id", att.person_id)
    if _dup_exists(db, new_shift, new_person, exclude_id=att_id):
        raise HTTPException(status_code=409, detail="Esa persona ya está en ese turno.")
    for k, v in data.items():
        setattr(att, k, v)
    att.updated_by = user.id
    db.commit(); db.refresh(att)
    return att


@router.post("/attendance/{att_id}/duplicate", response_model=m.AttendanceOut)
def duplicate_attendance(att_id: int, payload: dict, user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    att = db.query(m.AapAttendance).filter(m.AapAttendance.id == att_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Presencia no encontrada")
    target_shift = payload.get("shift_id")
    if not target_shift:
        raise HTTPException(status_code=400, detail="Falta el turno destino")
    if _dup_exists(db, target_shift, att.person_id):
        raise HTTPException(status_code=409, detail="Esa persona ya está en el turno destino.")
    copy = m.AapAttendance(
        event_id=att.event_id, shift_id=target_shift, person_id=att.person_id,
        start_time=att.start_time, end_time=att.end_time,
        is_shift_responsible=att.is_shift_responsible, event_role=att.event_role,
        notes=att.notes, created_by=user.id, updated_by=user.id,
    )
    db.add(copy); db.commit(); db.refresh(copy)
    return copy


@router.delete("/attendance/{att_id}")
def delete_attendance(att_id: int, user: m.AapUser = Depends(require_user), db: Session = Depends(get_db)):
    att = db.query(m.AapAttendance).filter(m.AapAttendance.id == att_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Presencia no encontrada")
    db.delete(att); db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# Turnos (config — admin). Listado va incluido en /state.
# ---------------------------------------------------------
@router.post("/shifts", response_model=m.ShiftOut)
def create_shift(payload: m.ShiftIn, user: m.AapUser = Depends(require_admin), db: Session = Depends(get_db)):
    ev = _active_event(db)
    shift = m.AapShift(event_id=ev.id, **payload.model_dump())
    db.add(shift); db.commit(); db.refresh(shift)
    return shift


@router.put("/shifts/{shift_id}", response_model=m.ShiftOut)
def update_shift(shift_id: int, payload: m.ShiftIn, user: m.AapUser = Depends(require_admin), db: Session = Depends(get_db)):
    shift = db.query(m.AapShift).filter(m.AapShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    for k, v in payload.model_dump().items():
        setattr(shift, k, v)
    db.commit(); db.refresh(shift)
    return shift
