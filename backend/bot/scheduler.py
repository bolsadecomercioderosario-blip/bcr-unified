"""
Scheduler in-process del bot BCR (APScheduler).

Asumimos un único worker — el plan Starter de Render no se duerme y corre
con 1 worker, así que esta forma es la más simple y barata. Si en el futuro
escalamos a múltiples workers, conviene mover los crons a Render Cron Jobs
separados (un servicio por scraper) en vez de meter locking distribuido acá.

Trigger horario: hora local Argentina (UTC-3).

Catch-up al arrancar
--------------------
APScheduler default NO recupera jobs perdidos cuando el proceso se cae y
reinicia (job store no es persistente, y misfire_grace_time = 1s). Render
reinicia el servicio Starter cada cierta cantidad de tiempo / por límite
de RAM. Para que no nos queden ingestas perdidas, en `start()` corremos
una rutina de catch-up que ve en la DB cuándo fue la última ingesta de
cada fuente y, si está stale, dispara el scraper en el momento.

Además seteamos misfire_grace_time generoso (1h en diarios, 1d en
semanales) para que cuando el cron sí cae cerca de la hora pero un
restart lo desplaza unos minutos, igual se ejecute en lugar de
silenciosamente quedar para mañana.

Cómo registrar un job nuevo:
1. Importar la función pura (que recibe db: Session).
2. Envolverla en un wrapper que abra una Session fresh (no se pueden
   compartir sesiones entre threads/jobs).
3. Llamar scheduler.add_job(wrapper, CronTrigger(...), id="...",
   replace_existing=True).
4. Sumarla a `_CATCHUP_SOURCES` para que un restart la ponga al día.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from database import SessionLocal


_TZ = "America/Argentina/Buenos_Aires"

# Tope para que un cron levemente atrasado (por restart, GC pause, lo que sea)
# igual se ejecute en lugar de quedarse en "missed". Generosos a propósito:
# preferimos correr un scraper idempotente de más, no perder una ingesta.
_DAILY_GRACE_S = 3600  # 1 hora
_WEEKLY_GRACE_S = 86400  # 1 día

scheduler = BackgroundScheduler(timezone=_TZ)


# Catálogo de fuentes que pueden hacer catch-up al arrancar. Cada entrada
# define cómo medir si está stale (qué tabla mirar) y qué job correr.
# Se popula dentro de start() porque necesita acceso a los wrappers.
_CATCHUP_SOURCES: list[dict] = []


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


def _startup_catchup() -> None:
    """Mira en la DB cuándo fue la última ingesta de cada fuente. Si está
    stale (más vieja que el umbral correspondiente), agenda un job one-shot
    en unos segundos para correr el scraper. Idempotente: los scrapers no
    duplican, y si una fuente está fresh no se hace nada.

    El one-shot va al scheduler en lugar de correrlo inline para no
    bloquear el arranque de uvicorn.
    """
    from bot import db_models

    db = SessionLocal()
    try:
        # (último timestamp encontrado, umbral, función a correr, id del job catchup)
        sources = [
            (
                db.query(db_models.PrecioPizarra.scraped_at)
                .order_by(db_models.PrecioPizarra.scraped_at.desc()).first(),
                timedelta(hours=30),  # diario
                _run_scrape_precios_pizarra,
                "catchup_precios_pizarra",
                "precios_pizarra",
            ),
            (
                db.query(db_models.IngestedComentario.ingested_at)
                .order_by(db_models.IngestedComentario.ingested_at.desc()).first(),
                timedelta(hours=30),  # diario
                _run_scrape_comentarios,
                "catchup_comentarios",
                "comentarios",
            ),
            (
                db.query(db_models.IngestedInformativoArticle.ingested_at)
                .order_by(db_models.IngestedInformativoArticle.ingested_at.desc()).first(),
                timedelta(days=8),  # semanal — un poco más de 7 para tolerar restart
                _run_scrape_informativo,
                "catchup_informativo",
                "informativo",
            ),
            (
                db.query(db_models.EstimacionGea.scraped_at)
                .order_by(db_models.EstimacionGea.scraped_at.desc()).first(),
                timedelta(hours=30),  # diario
                _run_scrape_gea_panel,
                "catchup_gea_panel",
                "gea_panel",
            ),
            (
                db.query(db_models.IngestedGeaReport.ingested_at)
                .order_by(db_models.IngestedGeaReport.ingested_at.desc()).first(),
                timedelta(days=8),  # semanal
                _run_scrape_gea_informes,
                "catchup_gea_informes",
                "gea_informes",
            ),
        ]

        now = datetime.utcnow()
        # Espaciamos los catchups de a 30 segundos para no martillar BCR ni
        # OpenAI con cinco scrapers paralelos arrancando juntos al boot.
        offset = 10
        scheduled: list[str] = []
        skipped: list[str] = []
        for last_row, threshold, job_fn, job_id, label in sources:
            last_at = last_row[0] if last_row else None
            is_stale = last_at is None or (now - last_at) > threshold
            if not is_stale:
                skipped.append(label)
                continue
            run_at = now + timedelta(seconds=offset)
            scheduler.add_job(
                job_fn,
                trigger=DateTrigger(run_date=run_at),
                id=job_id,
                replace_existing=True,
                misfire_grace_time=600,
            )
            scheduled.append(f"{label} (run_at={run_at.isoformat()})")
            offset += 30

        if scheduled:
            print(f"[bot.scheduler] catch-up al arrancar: {scheduled}")
        if skipped:
            print(f"[bot.scheduler] fresh (sin catch-up): {skipped}")
    except Exception as exc:  # noqa: BLE001 — el catch-up nunca debe romper el arranque
        print(f"[bot.scheduler] catch-up falló (no crítico): "
              f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def start() -> None:
    """Arranca el scheduler con los jobs registrados. Idempotente — si ya
    está corriendo (ej. uvicorn --reload), no hace nada."""
    if scheduler.running:
        return

    # Precios pizarra: tres firings al día (10:30, 13:00, 17:00 ART).
    # La BCR publica el card "del día" a las ~10:00 pero la tabla histórica
    # debajo tarda más; varios firings cubren la ventana sin tener que
    # adivinar el horario exacto. Scraper idempotente y barato (1 request,
    # 20-25 upserts), así que correr de más no molesta.
    scheduler.add_job(
        _run_scrape_precios_pizarra,
        CronTrigger(hour="10,13,17", minute=30),
        id="scrape_precios_pizarra",
        replace_existing=True,
        max_instances=1,  # No dejar arrancar otro tick si el anterior aún corre
        coalesce=True,    # Si nos perdimos ticks (por restart), correr UNO solo
        misfire_grace_time=_DAILY_GRACE_S,
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
        misfire_grace_time=_DAILY_GRACE_S,
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
        misfire_grace_time=_WEEKLY_GRACE_S,
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
        misfire_grace_time=_DAILY_GRACE_S,
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
        misfire_grace_time=_WEEKLY_GRACE_S,
    )

    scheduler.start()
    print(f"[bot.scheduler] arrancado en TZ={_TZ}. Jobs:")
    for job in scheduler.get_jobs():
        print(f"  - {job.id}: next run = {job.next_run_time}")

    # Catch-up de fuentes stale. Esto es lo que cubre los restarts de Render
    # que harían perder firings semanales o diarios silenciosamente.
    _startup_catchup()
