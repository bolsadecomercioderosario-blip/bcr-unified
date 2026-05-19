from sqlalchemy import text
from database import engine, SessionLocal

def migrate():
    print("Iniciando migración de base de datos...")
    with engine.connect() as conn:
        # SQLite y Postgres tienen sintaxis similar para esto
        try:
            # Intentamos agregar la columna image_url
            conn.execute(text("ALTER TABLE activities ADD COLUMN image_url VARCHAR DEFAULT ''"))
            conn.commit()
            print("Columna 'image_url' agregada con éxito.")
        except Exception as e:
            # Si falla es porque probablemente ya existe
            print(f"Nota: La migración de 'image_url' se saltó (posiblemente ya existe).")

        try:
            # Por las dudas, chequeamos otras columnas que agregamos recientemente
            conn.execute(text("ALTER TABLE activities ADD COLUMN order_index INTEGER DEFAULT 0"))
            conn.commit()
            print("Columna 'order_index' agregada con éxito.")
        except:
            pass

        # block_type: reemplaza al viejo flag observations='FIXED_BLOCK' con una
        # columna propia. Es idempotente: el ALTER falla silencioso si ya existe,
        # y los UPDATE de backfill sólo tocan filas que todavía tengan el flag viejo.
        try:
            conn.execute(text("ALTER TABLE activities ADD COLUMN block_type VARCHAR DEFAULT NULL"))
            conn.commit()
            print("Columna 'block_type' agregada con éxito.")
        except Exception:
            pass

        try:
            # Backfill: bloques fijos viejos → block_type='fixed' y se limpia el
            # observations contaminado.
            res = conn.execute(text(
                "UPDATE activities SET block_type='fixed', observations='' "
                "WHERE is_custom = 1 AND observations = 'FIXED_BLOCK' "
                "AND (block_type IS NULL OR block_type = '')"
            ))
            conn.commit()
            print(f"Backfill block_type='fixed': {res.rowcount} fila(s) actualizada(s).")
        except Exception as e:
            print(f"Nota: backfill de fixed se saltó ({e}).")

        try:
            # Bloques variables viejos: cualquier is_custom que no era fijo ni
            # ya tiene block_type → variable.
            res = conn.execute(text(
                "UPDATE activities SET block_type='variable' "
                "WHERE is_custom = 1 AND (block_type IS NULL OR block_type = '')"
            ))
            conn.commit()
            print(f"Backfill block_type='variable': {res.rowcount} fila(s) actualizada(s).")
        except Exception as e:
            print(f"Nota: backfill de variable se saltó ({e}).")

    seed_efemerides_if_empty()


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


if __name__ == "__main__":
    migrate()
