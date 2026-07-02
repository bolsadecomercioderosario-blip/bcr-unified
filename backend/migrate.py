"""
Migraciones idempotentes — corren en cada arranque del server.

OJO con Postgres: si un ALTER TABLE falla dentro de una transaction, la
transaction queda "aborted" y CUALQUIER query posterior en esa misma conexión
falla con "current transaction is aborted, commands ignored until end of
transaction block". Por eso cada operación usa su PROPIA conexión — si una
falla, la siguiente arranca limpia.
"""
from sqlalchemy import text
from database import engine, SessionLocal


def _try_exec(label, sql, expect_rowcount=False):
    """Corre `sql` en una conexión nueva. Si falla, se ignora y se sigue.
    Cada llamada es transactionalmente independiente — no contagia errores
    a las siguientes."""
    try:
        with engine.connect() as conn:
            res = conn.execute(text(sql))
            conn.commit()
            if expect_rowcount:
                print(f"  [OK] {label}: {res.rowcount} fila(s).")
            else:
                print(f"  [OK] {label}.")
    except Exception as e:
        # Truncamos el mensaje porque algunos drivers son verbosos.
        msg = str(e).split('\n')[0][:200]
        print(f"  [SKIP] {label}: ({msg}).")


def migrate():
    print("Iniciando migración de base de datos...")

    # --- Nuevas columnas (idempotente: si ya existen, el ALTER falla y se ignora) ---
    _try_exec(
        "ALTER add image_url",
        "ALTER TABLE activities ADD COLUMN image_url VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add order_index",
        "ALTER TABLE activities ADD COLUMN order_index INTEGER DEFAULT 0",
    )
    _try_exec(
        "ALTER add block_type",
        "ALTER TABLE activities ADD COLUMN block_type VARCHAR DEFAULT NULL",
    )
    _try_exec(
        "ALTER add origen",
        "ALTER TABLE activities ADD COLUMN origen VARCHAR DEFAULT 'comunicacion'",
    )
    _try_exec(
        "ALTER add comunicacion_notes",
        "ALTER TABLE activities ADD COLUMN comunicacion_notes VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add estado",
        "ALTER TABLE activities ADD COLUMN estado VARCHAR DEFAULT 'Pendiente'",
    )
    _try_exec(
        "ALTER add sec_responsible",
        "ALTER TABLE activities ADD COLUMN sec_responsible VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add sec_responsible_other",
        "ALTER TABLE activities ADD COLUMN sec_responsible_other VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add attachment_url",
        "ALTER TABLE activities ADD COLUMN attachment_url VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add attachment_name",
        "ALTER TABLE activities ADD COLUMN attachment_name VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add end_date",
        "ALTER TABLE activities ADD COLUMN end_date VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add end_time",
        "ALTER TABLE activities ADD COLUMN end_time VARCHAR DEFAULT ''",
    )

    # --- Backfill de block_type desde el viejo flag observations='FIXED_BLOCK' ---
    # Idempotente: sólo toca filas que todavía no tengan block_type seteado.
    # is_custom: en SQLite es INTEGER (0/1), en Postgres es BOOLEAN. Usamos
    # comparación contra string para que ambos dialectos lo evalúen bien.
    _try_exec(
        "Backfill bloques 'fixed' (legacy observations=FIXED_BLOCK)",
        "UPDATE activities SET block_type='fixed', observations='' "
        "WHERE is_custom AND observations = 'FIXED_BLOCK' "
        "AND (block_type IS NULL OR block_type = '')",
        expect_rowcount=True,
    )
    _try_exec(
        "Backfill bloques 'variable' (resto de is_custom sin block_type)",
        "UPDATE activities SET block_type='variable' "
        "WHERE is_custom AND (block_type IS NULL OR block_type = '')",
        expect_rowcount=True,
    )

    backfill_origen_from_channel()

    seed_efemerides_if_empty()
    seed_metricas_if_empty()


def backfill_origen_from_channel():
    """Migra el viejo canal "Agenda Compromisos" al nuevo campo `origen`.

    Las actividades que tenían ese canal pasan a origen='secretaria' (son la
    Agenda de Compromisos) y se les saca el canal de la lista, porque el
    casillero se eliminó del formulario. El resto queda en 'comunicacion' (el
    default de la columna). Idempotente: una vez migradas, ninguna tiene el
    canal, así que re-correr no cambia nada.

    Se hace en Python (no en SQL) porque `channels` es JSON y filtrar/editar
    listas JSON es dependiente del dialecto (SQLite vs Postgres)."""
    from agenda_models import Activity

    db = SessionLocal()
    try:
        rows = db.query(Activity).all()
        changed = 0
        for r in rows:
            ch = r.channels if isinstance(r.channels, list) else []
            if "Agenda Compromisos" in ch:
                r.origen = "secretaria"
                # Reasignamos una lista nueva para que SQLAlchemy marque el
                # campo como modificado (mutar in-place no lo detecta en JSON).
                r.channels = [c for c in ch if c != "Agenda Compromisos"]
                changed += 1
        if changed:
            db.commit()
        print(f"Backfill origen: {changed} actividad(es) marcadas como Secretaría.")
    except Exception as e:
        print(f"Error en backfill de origen: {e}")
        db.rollback()
    finally:
        db.close()


def seed_efemerides_if_empty():
    """Inserta el listado inicial de efemérides si la tabla está vacía."""
    from agenda_models import Efemeride
    from seed_efemerides import EFEMERIDES_DATA

    db = SessionLocal()
    try:
        count = db.query(Efemeride).count()
        if count == 0:
            for entry in EFEMERIDES_DATA:
                db.add(Efemeride(**entry))
            db.commit()
            print(f"Seed de efemérides: {len(EFEMERIDES_DATA)} entradas insertadas.")
        else:
            print(f"Seed de efemérides saltado (ya hay {count} entradas).")
    except Exception as e:
        print(f"Error al sembrar efemérides: {e}")
        db.rollback()
    finally:
        db.close()


def seed_metricas_if_empty():
    """Siembra programas + instancias de Métricas FBCR si las tablas están vacías.
    Idempotente: una vez sembrado, las altas se cargan desde el admin."""
    from metricas.models import Instancia, Programa
    from metricas.seed_data import INSTANCIAS, PROGRAMAS

    db = SessionLocal()
    try:
        if db.query(Programa).count() > 0:
            print("Seed de métricas saltado (ya hay programas cargados).")
            return

        slug_to_id = {}
        for p in PROGRAMAS:
            prog = Programa(**p)
            db.add(prog)
            db.flush()  # para tener el id antes del commit
            slug_to_id[prog.slug] = prog.id

        for row in INSTANCIAS:
            data = dict(row)
            slug = data.pop("programa")
            db.add(Instancia(programa_id=slug_to_id[slug], **data))

        db.commit()
        print(f"Seed de métricas: {len(PROGRAMAS)} programas y {len(INSTANCIAS)} instancias insertadas.")
    except Exception as e:
        print(f"Error al sembrar métricas: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
