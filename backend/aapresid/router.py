"""
API del módulo Aapresid 2026. Prefijo /api/aapresid.

Fase 1: login por usuario, estado del tablero (evento + turnos + áreas +
personas + presencias), ABM de áreas y personas, y CRUD de presencias
(crear/editar/borrar/mover/duplicar, sin duplicar persona en el mismo turno).
Todos los endpoints (menos login) requieren usuario autenticado.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from aapresid import models as m
from aapresid.auth import verify_password, make_token


router = APIRouter(prefix="/api/aapresid", tags=["aapresid"])


# Acceso directo por URL (sin login): los endpoints quedan abiertos. Se usa un
# "usuario anónimo" para no romper created_by/updated_by ni la auditoría.
class _AnonUser:
    id = None
    email = "—"
    role = "editor"


def anon_user() -> "_AnonUser":
    return _AnonUser()


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
def me(user: m.AapUser = Depends(anon_user)):
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


def _shift_for(db: Session, event_id: int, date: str, start_time: str) -> Optional[int]:
    """Turno cuyo rango [inicio, fin) contiene la hora de inicio, ese día.
    Las horas son 'HH:MM' zero-padded, así que la comparación de strings sirve."""
    shifts = db.query(m.AapShift).filter(
        m.AapShift.event_id == event_id, m.AapShift.date == date, m.AapShift.active == True,  # noqa: E712
    ).all()
    for s in shifts:
        if s.start_time <= (start_time or "") < s.end_time:
            return s.id
    return None


def _participant_ids(db: Session, meeting_id: int) -> List[int]:
    rows = db.query(m.AapMeetingParticipant).filter(
        m.AapMeetingParticipant.meeting_id == meeting_id
    ).all()
    return [r.person_id for r in rows]


def _meeting_out(db: Session, mtg: m.AapMeeting) -> dict:
    return m.MeetingOut.model_validate(mtg).model_dump()


def _set_participants(db: Session, meeting_id: int, person_ids: List[int]):
    db.query(m.AapMeetingParticipant).filter(
        m.AapMeetingParticipant.meeting_id == meeting_id
    ).delete()
    for pid in set(person_ids or []):
        db.add(m.AapMeetingParticipant(meeting_id=meeting_id, person_id=pid))


# --- Auditoría (historial simple) ---
def _snap(db: Session, entity_type: str, obj) -> dict:
    """Resumen legible de un registro para el historial."""
    if obj is None:
        return {}
    if entity_type == "attendance":
        p = db.get(m.AapPerson, obj.person_id)
        s = db.get(m.AapShift, obj.shift_id)
        return {"persona": p.full_name if p else obj.person_id,
                "turno": (f"{s.date} {s.name}" if s else obj.shift_id),
                "responsable": bool(obj.is_shift_responsible)}
    if entity_type == "meeting":
        return {"titulo": obj.title, "fecha": obj.date, "inicio": obj.start_time, "estado": obj.status}
    if entity_type == "person":
        return {"nombre": obj.full_name, "area_id": obj.area_id, "activa": bool(obj.active)}
    if entity_type == "area":
        return {"nombre": obj.name, "activa": bool(obj.active)}
    if entity_type == "shift":
        return {"turno": f"{obj.date} {obj.name}", "responsable": obj.responsible_name}
    return {}


def _audit(db: Session, user, entity_type: str, entity_id, action: str, prev=None, new=None):
    """Registra un cambio. No commitea: se persiste con el commit del caller."""
    db.add(m.AapAudit(
        user_id=user.id, user_email=user.email, entity_type=entity_type,
        entity_id=entity_id, action=action,
        previous_data=json.dumps(prev or {}, ensure_ascii=False, default=str),
        new_data=json.dumps(new or {}, ensure_ascii=False, default=str),
    ))


@router.get("/audit")
def get_audit(user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    rows = db.query(m.AapAudit).order_by(m.AapAudit.id.desc()).limit(150).all()
    return [{
        "id": r.id, "user_email": r.user_email, "entity_type": r.entity_type,
        "entity_id": r.entity_id, "action": r.action,
        "previous_data": r.previous_data, "new_data": r.new_data,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.get("/state")
def get_state(user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    ev = _active_event(db)
    shifts = db.query(m.AapShift).filter(
        m.AapShift.event_id == ev.id, m.AapShift.active == True,  # noqa: E712
    ).order_by(m.AapShift.date, m.AapShift.display_order).all()
    areas = db.query(m.AapArea).order_by(m.AapArea.name).all()
    people = db.query(m.AapPerson).order_by(m.AapPerson.full_name).all()
    attendance = db.query(m.AapAttendance).filter(m.AapAttendance.event_id == ev.id).all()
    meetings = db.query(m.AapMeeting).filter(m.AapMeeting.event_id == ev.id).all()
    return {
        "event": m.EventOut.model_validate(ev).model_dump(),
        "shifts": [m.ShiftOut.model_validate(s).model_dump() for s in shifts],
        "areas": [m.AreaOut.model_validate(a).model_dump() for a in areas],
        "people": [m.PersonOut.model_validate(p).model_dump() for p in people],
        "attendance": [m.AttendanceOut.model_validate(x).model_dump() for x in attendance],
        "meetings": [_meeting_out(db, mt) for mt in meetings],
    }


# ---------------------------------------------------------
# Áreas (config — admin)
# ---------------------------------------------------------
@router.post("/areas", response_model=m.AreaOut)
def create_area(payload: m.AreaIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    area = m.AapArea(**payload.model_dump())
    db.add(area); db.commit(); db.refresh(area)
    return area


@router.put("/areas/{area_id}", response_model=m.AreaOut)
def update_area(area_id: int, payload: m.AreaIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    area = db.query(m.AapArea).filter(m.AapArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área no encontrada")
    for k, v in payload.model_dump().items():
        setattr(area, k, v)
    db.commit(); db.refresh(area)
    return area


@router.delete("/areas/{area_id}")
def delete_area(area_id: int, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
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
def create_person(payload: m.PersonIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    person = m.AapPerson(**payload.model_dump())
    db.add(person); db.commit(); db.refresh(person)
    return person


@router.put("/people/{person_id}", response_model=m.PersonOut)
def update_person(person_id: int, payload: m.PersonIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    person = db.query(m.AapPerson).filter(m.AapPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    for k, v in payload.model_dump().items():
        setattr(person, k, v)
    db.commit(); db.refresh(person)
    return person


@router.delete("/people/{person_id}")
def delete_person(person_id: int, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
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
def create_attendance(payload: m.AttendanceIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
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
    _audit(db, user, "attendance", att.id, "create", new=_snap(db, "attendance", att)); db.commit()
    return att


@router.put("/attendance/{att_id}", response_model=m.AttendanceOut)
def update_attendance(att_id: int, payload: m.AttendanceUpdate, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    att = db.query(m.AapAttendance).filter(m.AapAttendance.id == att_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Presencia no encontrada")
    data = payload.model_dump(exclude_unset=True)
    new_shift = data.get("shift_id", att.shift_id)
    new_person = data.get("person_id", att.person_id)
    if _dup_exists(db, new_shift, new_person, exclude_id=att_id):
        raise HTTPException(status_code=409, detail="Esa persona ya está en ese turno.")
    prev = _snap(db, "attendance", att)
    for k, v in data.items():
        setattr(att, k, v)
    att.updated_by = user.id
    db.commit(); db.refresh(att)
    _audit(db, user, "attendance", att.id, "update", prev=prev, new=_snap(db, "attendance", att)); db.commit()
    return att


@router.post("/attendance/{att_id}/duplicate", response_model=m.AttendanceOut)
def duplicate_attendance(att_id: int, payload: dict, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
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
def delete_attendance(att_id: int, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    att = db.query(m.AapAttendance).filter(m.AapAttendance.id == att_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Presencia no encontrada")
    _audit(db, user, "attendance", att.id, "delete", prev=_snap(db, "attendance", att))
    db.delete(att); db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# Turnos (config — admin). Listado va incluido en /state.
# ---------------------------------------------------------
@router.post("/shifts", response_model=m.ShiftOut)
def create_shift(payload: m.ShiftIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    ev = _active_event(db)
    shift = m.AapShift(event_id=ev.id, **payload.model_dump())
    db.add(shift); db.commit(); db.refresh(shift)
    return shift


@router.put("/shifts/{shift_id}", response_model=m.ShiftOut)
def update_shift(shift_id: int, payload: m.ShiftIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    shift = db.query(m.AapShift).filter(m.AapShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    for k, v in payload.model_dump().items():
        setattr(shift, k, v)
    db.commit(); db.refresh(shift)
    return shift


# ---------------------------------------------------------
# Reuniones
# ---------------------------------------------------------
def _validate_meeting(payload: m.MeetingIn):
    if not (payload.title or "").strip():
        raise HTTPException(status_code=400, detail="La reunión necesita una descripción.")
    if payload.status and payload.status not in m.MEETING_STATUSES:
        raise HTTPException(status_code=400, detail="Estado inválido.")


def _apply_meeting(mtg: m.AapMeeting, payload: m.MeetingIn, shift: m.AapShift):
    mtg.shift_id = shift.id
    mtg.date = shift.date
    mtg.title = payload.title.strip()
    mtg.responsible_name = (payload.responsible_name or "").strip()
    mtg.area_name = (payload.area_name or "").strip()
    mtg.location = (payload.location or "").strip()
    mtg.status = payload.status or "Tentativa"


@router.post("/meetings")
def create_meeting(payload: m.MeetingIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    _validate_meeting(payload)
    ev = _active_event(db)
    shift = db.get(m.AapShift, payload.shift_id)
    if not shift:
        raise HTTPException(status_code=400, detail="Turno inválido")
    mtg = m.AapMeeting(event_id=ev.id, created_by=user.id, updated_by=user.id)
    _apply_meeting(mtg, payload, shift)
    db.add(mtg); db.commit(); db.refresh(mtg)
    _audit(db, user, "meeting", mtg.id, "create", new=_snap(db, "meeting", mtg)); db.commit()
    return _meeting_out(db, mtg)


@router.put("/meetings/{meeting_id}")
def update_meeting(meeting_id: int, payload: m.MeetingIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    _validate_meeting(payload)
    mtg = db.query(m.AapMeeting).filter(m.AapMeeting.id == meeting_id).first()
    if not mtg:
        raise HTTPException(status_code=404, detail="Reunión no encontrada")
    shift = db.get(m.AapShift, payload.shift_id)
    if not shift:
        raise HTTPException(status_code=400, detail="Turno inválido")
    prev = _snap(db, "meeting", mtg)
    _apply_meeting(mtg, payload, shift)
    mtg.updated_by = user.id
    db.commit(); db.refresh(mtg)
    _audit(db, user, "meeting", mtg.id, "update", prev=prev, new=_snap(db, "meeting", mtg)); db.commit()
    return _meeting_out(db, mtg)


@router.put("/shifts/{shift_id}/responsible", response_model=m.ShiftOut)
def set_shift_responsible(shift_id: int, payload: m.ShiftResponsibleIn, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    shift = db.get(m.AapShift, shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    prev = shift.responsible_name
    shift.responsible_name = (payload.responsible_name or "").strip()
    db.commit(); db.refresh(shift)
    _audit(db, user, "shift", shift.id, "update", prev={"responsable": prev}, new={"responsable": shift.responsible_name}); db.commit()
    return shift


@router.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: int, user: m.AapUser = Depends(anon_user), db: Session = Depends(get_db)):
    mtg = db.query(m.AapMeeting).filter(m.AapMeeting.id == meeting_id).first()
    if not mtg:
        raise HTTPException(status_code=404, detail="Reunión no encontrada")
    _audit(db, user, "meeting", mtg.id, "delete", prev=_snap(db, "meeting", mtg))
    db.query(m.AapMeetingParticipant).filter(m.AapMeetingParticipant.meeting_id == meeting_id).delete()
    db.delete(mtg); db.commit()
    return {"ok": True}
