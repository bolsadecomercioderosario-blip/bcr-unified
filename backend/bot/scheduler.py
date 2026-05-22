"""
Scheduler in-process del bot BCR (APScheduler).

Asumimos un único worker — el plan Starter de Render no se duerme y corre
con 1 worker, así que esta forma es la más simple y barata. Si en el futuro
escalamos a múltiples workers, conviene mover los crons a Render Cron Jobs
separados (un servicio por scraper) en vez de meter locking distribuido acá.

Trigger horario: hora local Argentina (UTC-3).

Cómo registrar un job nuevo:
1. Importar la función pura (que recibe db: Session).
2. Envolverla en un wrapper que abra una Session fresh (no se pueden
   compartir sesiones entre threads/jobs).
3. Llamar scheduler.add_job(wrapper, CronTrigger(...), id="...",
   replace_existing=True).
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal


_TZ = "America/Argentina/Buenos_Aires"

scheduler = BackgroundScheduler(timezone=_TZ)


def _run_scrape_precios_pizarra() -> None:
    """Wrapper para el job diario de precios. Abre Session fresh, corre el
    scraper, loguea el resultado, cierra Session."""
    # Import local para evitar cargar scraper_pizarra (y por ende beautifulsoup)
    # antes de tiempo si el bot no se usa.
    from bot.scraper_pizarra import scrape_precios_pizarra

    db = SessionLocal()
    try:
        result = scrape_precios_pizarra(db)
        print(f"[bot.scheduler] scrape_precios_pizarra → {result}")
    except Exception as exc:  # noqa: BLE001 — no queremos que un fallo mate el scheduler
        print(f"[bot.scheduler] scrape_precios_pizarra falló: {type(exc).__name__}: {exc}")
    finally:
        db.close()


def _run_scrape_comentarios() -> None:
    """Wrapper para el job diario de comentarios. Corre LOCAL y CHICAGO
    secuencialmente."""
    from bot.scraper_comentarios import scrape_comentarios

    db = SessionLocal()
    try:
        for source in ("local", "chicago"):
            try:
                result = scrape_comentarios(db, source=source)
                print(f"[bot.scheduler] scrape_comentarios({source}) → "
                      f"new={result.get('new_found', 0)} "
                      f"uploaded={len(result.get('uploaded', []))} "
                      f"failed={len(result.get('failed', []))}")
            except Exception as exc:  # noqa: BLE001
                print(f"[bot.scheduler] scrape_comentarios({source}) falló: "
                      f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def _run_scrape_informativo() -> None:
    """Wrapper para el job del viernes del informativo semanal."""
    from bot.scraper_informativo import scrape_current_edition

    db = SessionLocal()
    try:
        result = scrape_current_edition(db)
        print(f"[bot.scheduler] scrape_current_edition → "
              f"edicion={result.get('edicion', {}).get('numero')} "
              f"in_page={result.get('in_page', 0)} "
              f"new_found={result.get('new_found', 0)} "
              f"uploaded={len(result.get('uploaded', []))} "
              f"failed={len(result.get('failed', []))}")
    except Exception as exc:  # noqa: BLE001
        print(f"[bot.scheduler] scrape_current_edition falló: "
              f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def _run_scrape_gea_panel() -> None:
    """Wrapper para el job diario del panel GEA (table de estimaciones)."""
    from bot.scraper_gea import scrape_gea_panel

    db = SessionLocal()
    try:
        result = scrape_gea_panel(db)
        print(f"[bot.scheduler] scrape_gea_panel → status={result.get('status')} "
              f"upserted={result.get('upserted', 0)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[bot.scheduler] scrape_gea_panel falló: "
              f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def _run_scrape_gea_informes() -> None:
    """Wrapper para el job semanal de informes mensuales GEA."""
    from bot.scraper_gea import scrape_gea_informes

    db = SessionLocal()
    try:
        result = scrape_gea_informes(db)
        print(f"[bot.scheduler] scrape_gea_informes → "
              f"new_found={result.get('new_found', 0)} "
              f"uploaded={len(result.get('uploaded', []))} "
              f"failed={len(result.get('failed', []))}")
    except Exception as exc:  # noqa: BLE001
        print(f"[bot.scheduler] scrape_gea_informes falló: "
              f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def start() -> None:
    """Arranca el scheduler con los jobs registrados. Idempotente — si ya
    está corriendo (ej. uvicorn --reload), no hace nada."""
    if scheduler.running:
        return

    # Precios pizarra: todos los días a las 10:30 ART. El sitio actualiza a
    # las 10:00, dejamos margen para que esté disponible.
    scheduler.add_job(
        _run_scrape_precios_pizarra,
        CronTrigger(hour=10, minute=30),
        id="scrape_precios_pizarra",
        replace_existing=True,
        max_instances=1,  # No dejar arrancar otro tick si el anterior aún corre
        coalesce=True,    # Si nos perdimos ticks (por restart), correr UNO solo
    )

    # Comentarios diarios: 17:00 ART. La BCR suele publicar a la tarde —
    # dejamos margen para que ya esté el del día.
    scheduler.add_job(
        _run_scrape_comentarios,
        CronTrigger(hour=17, minute=0),
        id="scrape_comentarios_diarios",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Informativo semanal: viernes 13:00 y 18:00 ART. La edición sale al
    # mediodía pero el horario varía — dos pasadas cubren el rango sin
    # quedar muy atrás del corte.
    scheduler.add_job(
        _run_scrape_informativo,
        CronTrigger(day_of_week="fri", hour="13,18", minute=0),
        id="scrape_informativo_viernes",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Panel GEA (estimaciones de producción): el sitio actualiza esporádicamente
    # — corremos diario a las 9:00 ART. Idempotente, no hace daño correr de más.
    scheduler.add_job(
        _run_scrape_gea_panel,
        CronTrigger(hour=9, minute=0),
        id="scrape_gea_panel_diario",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Informes GEA (estimaciones nacionales mensuales): semanal los lunes
    # a las 9:30 ART. Idempotente — sólo sube los slugs nuevos.
    scheduler.add_job(
        _run_scrape_gea_informes,
        CronTrigger(day_of_week="mon", hour=9, minute=30),
        id="scrape_gea_informes_semanal",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    print(f"[bot.scheduler] arrancado en TZ={_TZ}. Jobs:")
    for job in scheduler.get_jobs():
        print(f"  - {job.id}: next run = {job.next_run_time}")
