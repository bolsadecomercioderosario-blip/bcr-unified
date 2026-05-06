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
