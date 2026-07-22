"""
Seed inicial del módulo Aapresid. Idempotente: sólo corre si no hay evento.

Precarga:
- El evento Congreso Aapresid 2026 (Salón Metropolitano, Rosario, 4-6 ago 2026).
- Los 8 turnos (el martes NO tiene Mañana).
- Áreas de referencia de la BCR.
- Un usuario admin inicial (email/pass por env o defaults documentados).
- Datos de ejemplo (personas + presencias) marcados con "[Ejemplo]" para poder
  borrarlos fácil.
"""
import os

from database import SessionLocal
from aapresid.models import (
    AapEvent, AapShift, AapArea, AapPerson, AapAttendance, AapUser,
)
from aapresid.auth import hash_password


EVENT = {
    "name": "Congreso Aapresid 2026",
    "location": "Salón Metropolitano, Rosario",
    "start_date": "2026-08-04",
    "end_date": "2026-08-06",
}

# (date, name, start, end, display_order). Martes sin Mañana.
SHIFTS = [
    ("2026-08-04", "Mediodía", "12:00", "15:00", 1),
    ("2026-08-04", "Tarde", "15:00", "18:00", 2),
    ("2026-08-05", "Mañana", "08:00", "12:00", 1),
    ("2026-08-05", "Mediodía", "12:00", "15:00", 2),
    ("2026-08-05", "Tarde", "15:00", "18:00", 3),
    ("2026-08-06", "Mañana", "08:00", "12:00", 1),
    ("2026-08-06", "Mediodía", "12:00", "15:00", 2),
    ("2026-08-06", "Tarde", "15:00", "18:00", 3),
]

AREAS = [
    ("Comunicación", "Prensa, redes y cobertura institucional"),
    ("Secretaría", "Secretaría / autoridades"),
    ("Estudios Económicos", "Investigación y desarrollo (GEA, informes)"),
    ("Relaciones Institucionales", "Vínculos con instituciones y empresas"),
    ("Capacitación", "BCR Capacita"),
    ("Innova", "BCR Innova / startups"),
]


def seed_aapresid_if_empty():
    db = SessionLocal()
    try:
        if db.query(AapEvent).count() > 0:
            print("Seed Aapresid saltado (ya hay evento cargado).")
            return

        event = AapEvent(**EVENT, active=True)
        db.add(event)
        db.flush()  # para tener event.id

        shift_by_key = {}
        for date, name, start, end, order in SHIFTS:
            s = AapShift(
                event_id=event.id, date=date, name=name,
                start_time=start, end_time=end, display_order=order, active=True,
            )
            db.add(s)
            db.flush()
            shift_by_key[(date, name)] = s.id

        area_by_name = {}
        for name, desc in AREAS:
            a = AapArea(name=name, description=desc, active=True)
            db.add(a)
            db.flush()
            area_by_name[name] = a.id

        # Usuario admin inicial
        admin_email = os.environ.get("AAPRESID_ADMIN_EMAIL", "admin@aapresid.bcr")
        admin_pass = os.environ.get("AAPRESID_ADMIN_PASSWORD", "aapresid2026")
        db.add(AapUser(
            full_name="Administrador Aapresid",
            email=admin_email.lower().strip(),
            password_hash=hash_password(admin_pass),
            role="admin", active=True,
        ))

        # Datos de ejemplo (marcados con [Ejemplo])
        p1 = AapPerson(full_name="[Ejemplo] Ana Pérez", area_id=area_by_name["Comunicación"], role="Prensa", active=True)
        p2 = AapPerson(full_name="[Ejemplo] Luis Gómez", area_id=area_by_name["Secretaría"], role="Coordinación", active=True)
        db.add_all([p1, p2])
        db.flush()

        db.add_all([
            AapAttendance(
                event_id=event.id, shift_id=shift_by_key[("2026-08-04", "Mediodía")],
                person_id=p1.id, is_shift_responsible=True,
                event_role="Cobertura de prensa", notes="[Ejemplo]",
            ),
            AapAttendance(
                event_id=event.id, shift_id=shift_by_key[("2026-08-05", "Mañana")],
                person_id=p2.id, is_shift_responsible=False,
                event_role="Coordinación de stand", notes="[Ejemplo]",
            ),
        ])

        db.commit()
        print(f"Seed Aapresid: evento + {len(SHIFTS)} turnos + {len(AREAS)} áreas + admin ({admin_email}) + ejemplos.")
    except Exception as e:
        print(f"Error en seed Aapresid: {e}")
        db.rollback()
    finally:
        db.close()
