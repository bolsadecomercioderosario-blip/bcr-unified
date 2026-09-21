"""
Módulo Bot BCR: agente conversacional con tools.

Tools enchufadas:
  - consultar_agenda (chunk 2.2) — lee tabla activities
  - buscar_institucional / buscar_informativo / buscar_comentario_diario /
    buscar_informe_gea (chunks 2.3 + GEA) — file_search sobre vector stores OpenAI
  - get_precios_pizarra / get_estimaciones_gea (chunk 2.4 + GEA) — placeholders
    hasta que los scrapers del chunk 3.x los llenen

Endpoints:
  - /api/bot/twilio-webhook — público (firmado por Twilio); recibe WhatsApp
  - /api/bot/admin/* — protegidos por auth bearer (debug/admin)

Nota: el chat web /api/bot/test se eliminó — el bot está 100% en WhatsApp. Era
público y exponía el agente (costo OpenAI + material interno) a cualquiera con
el link, así que se sacó por seguridad.
"""
from __future__ import annotations

import re
import traceback
import unicodedata
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_roles, ROLE_COMUNICACION
from config import BOT_WHATSAPP_WHITELIST
from database import get_db, SessionLocal

from bot import agent, agenda_writer, db_models, menu_handlers, models, twilio_client


# ---------------------------------------------------------------------------
# Whitelist: sólo estos números pueden hablarle al bot. Vacío = abierto.
# Se normaliza a dígitos para comparar sin importar 'whatsapp:', '+', espacios.
# ---------------------------------------------------------------------------
def _normalize_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    # Argentina: colapsar el "9" de celular que va después del código país 54,
    # porque Meta/Twilio mandan el número a veces CON y a veces SIN ese 9. Así
    # "+54 9 341 ..." y "+54 341 ..." matchean igual (whitelist y writers).
    if d.startswith("549"):
        d = "54" + d[3:]
    return d


_WHITELIST = {_normalize_phone(x) for x in BOT_WHATSAPP_WHITELIST.split(",") if x.strip()}


def _phone_allowed(from_phone: str) -> bool:
    """True si el número puede usar el bot. Whitelist vacía = abierto a todos."""
    if not _WHITELIST:
        return True
    return _normalize_phone(from_phone) in _WHITELIST


# ---------------------------------------------------------------------------
# Diagnóstico: registro en memoria de los últimos webhooks recibidos, para poder
# ver desde /admin/health por qué el bot contesta o no (sin depender de los logs
# de Render). No guarda el texto del mensaje, sólo metadatos.
# ---------------------------------------------------------------------------
_LAST_WEBHOOKS: deque = deque(maxlen=25)

# Anti-replay: MessageSid ya procesados (en memoria, acotado). Twilio reintenta
# el webhook si no contestamos a tiempo, y un request firmado capturado podría
# reenviarse → deduplicamos para no correr el agente (ni gastar OpenAI) dos veces
# por el mismo mensaje. Se resetea en cada reinicio (aceptable: cubre la ventana
# de reintentos, que es de minutos).
_SEEN_SIDS: deque = deque(maxlen=500)
_SEEN_SIDS_SET: set = set()


def _already_processed(message_sid: str) -> bool:
    """True si este MessageSid ya se procesó (y lo registra si es nuevo)."""
    if not message_sid:
        return False
    if message_sid in _SEEN_SIDS_SET:
        return True
    if len(_SEEN_SIDS) >= _SEEN_SIDS.maxlen:
        _SEEN_SIDS_SET.discard(_SEEN_SIDS.popleft())
    _SEEN_SIDS.append(message_sid)
    _SEEN_SIDS_SET.add(message_sid)
    return False


def _candidate_urls(request: Request) -> list[str]:
    """URLs posibles sobre las que Twilio pudo firmar. En Render (detrás de
    proxy) str(request.url) puede venir http en vez de https, o con otro host;
    probamos varias variantes para que la firma valide igual."""
    cands: list[str] = []
    xfu = request.headers.get("X-Forwarded-Url")
    if xfu:
        cands.append(xfu)
    raw = str(request.url)
    cands.append(raw)
    if raw.startswith("http://"):
        cands.append("https://" + raw[len("http://"):])
    proto = (request.headers.get("X-Forwarded-Proto") or "https").split(",")[0].strip()
    host = (request.headers.get("X-Forwarded-Host")
            or request.headers.get("Host") or request.url.netloc)
    path = request.url.path
    q = request.url.query
    built = f"{proto}://{host}{path}" + (f"?{q}" if q else "")
    cands.append(built)
    # dedup preservando orden
    out: list[str] = []
    for c in cands:
        if c and c not in out:
            out.append(c)
    return out


# /api/bot/test y /admin/* requieren bearer auth (consistente con el resto
# del API). /twilio-webhook se valida con X-Twilio-Signature en el endpoint
# mismo, así que NO va por require_roles.
router = APIRouter(prefix="/api/bot")


# El chat web /api/bot/test se eliminó: el bot está 100% en WhatsApp y ese
# endpoint era público (exponía el agente y el material interno a cualquiera con
# el link). El flujo entrante ahora es sólo /twilio-webhook.


# ---------------------------------------------------------------------------
# Webhook de Twilio WhatsApp (público, validado por firma).
# ---------------------------------------------------------------------------
def _get_or_create_session(db: Session, from_phone: str) -> tuple[db_models.BotSession, Optional[str]]:
    """Recupera la sesión del usuario; devuelve (session, previous_response_id_aplicable).

    Si la última actividad pasó el TTL, ignoramos el previous_response_id y
    arrancamos conversación nueva.
    """
    session = db.query(db_models.BotSession).filter(
        db_models.BotSession.from_phone == from_phone
    ).first()

    if session is None:
        session = db_models.BotSession(from_phone=from_phone, last_response_id=None)
        db.add(session)
        return session, None

    age = (datetime.utcnow() - session.last_message_at).total_seconds()
    if age > db_models.SESSION_TTL_SECONDS:
        # Sesión expirada — reseteamos memoria.
        session.last_response_id = None
        return session, None

    return session, session.last_response_id


# ---------------------------------------------------------------------------
# Menú inicial (list-picker de WhatsApp): ante un saludo o pedido de menú, en
# vez de correr el agente, mandamos el saludo + la lista de 6 opciones.
# ---------------------------------------------------------------------------
_MENU_GREETINGS = {
    "hola", "holaa", "holis", "buenas", "buenass", "buen dia", "buenos dias",
    "buenas tardes", "buenas noches", "menu", "menu principal", "opciones",
    "inicio", "empezar", "comenzar", "start", "ayuda", "hi", "hello",
}


def _norm_txt(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _is_menu_request(text: str) -> bool:
    t = _norm_txt(text)
    if t in _MENU_GREETINGS:
        return True
    return bool(re.match(r"^(hola|buenas|buen dia|buenos dias|buenas tardes|buenas noches)\b", t))


def ensure_menu_content_sid(db: Session, force: bool = False) -> str:
    """Devuelve el ContentSid del menú, creándolo (Content API) y persistiéndolo
    en bot_config la primera vez. force=True recrea el template (para iterar)."""
    from bot.db_models import BotConfig
    row = db.query(BotConfig).filter(BotConfig.key == "menu_content_sid").first()
    if row and row.value and not force:
        return row.value
    sid = twilio_client.create_menu_content_sid()
    if row:
        row.value = sid
        row.updated_at = datetime.utcnow()
    else:
        db.add(BotConfig(key="menu_content_sid", value=sid))
    db.commit()
    return sid


def _process_message(from_phone: str, body: str, ev: dict | None = None) -> None:
    """Corre el agente y manda la respuesta por REST. Va en SEGUNDO PLANO
    (BackgroundTask) para no colgar el webhook de Twilio, que corta a los ~15s
    — el ciclo de herramientas (varias llamadas a OpenAI + DB) puede pasarse de
    ahí. Usa su PROPIA sesión de DB porque la del request ya está cerrada."""
    ev = ev if ev is not None else {}
    db = SessionLocal()
    try:
        # Saludo / pedido de menú → mostramos la lista interactiva (no corre el agente).
        if _is_menu_request(body):
            try:
                sid = ensure_menu_content_sid(db)
                twilio_client.send_whatsapp_content(from_phone, sid)
                ev["menu"] = True
                ev["envio_ok"] = True
            except Exception as exc:  # noqa: BLE001 — fallback a texto si el menú falla
                print(f"[bot.twilio-webhook] Falló menú interactivo: {type(exc).__name__}: {exc}")
                ev["menu"] = True
                ev["error"] = f"menu: {type(exc).__name__}: {exc}"
                try:
                    twilio_client.send_whatsapp(from_phone, twilio_client.MENU_SALUDO)
                    ev["envio_ok"] = True
                except Exception:  # noqa: BLE001
                    ev["envio_ok"] = False
            return

        # Opción del menú tocada → handler propio (rápido, formato consistente),
        # sin correr el agente.
        opt = menu_handlers.match_option(body)
        if opt:
            try:
                reply = menu_handlers.handle(opt, db)
                twilio_client.send_whatsapp(from_phone, reply)
                ev["opcion"] = opt
                ev["envio_ok"] = True
            except Exception as exc:  # noqa: BLE001
                print(f"[bot.twilio-webhook] Falló opción '{opt}': {type(exc).__name__}: {exc}")
                ev["opcion"] = opt
                ev["error"] = f"opcion: {type(exc).__name__}: {exc}"
                try:
                    twilio_client.send_whatsapp(from_phone, "Tuve un problema con esa opción. Probá de nuevo en un momento.")
                    ev["envio_ok"] = True
                except Exception:  # noqa: BLE001
                    ev["envio_ok"] = False
            return

        session, previous_response_id = _get_or_create_session(db, from_phone)

        exchange = db_models.BotExchange(from_phone=from_phone, message=body, reply="")
        db.add(exchange)

        try:
            result = agent.run_agent(
                message=body,
                from_phone=from_phone,
                db=db,
                previous_response_id=previous_response_id,
            )
            reply_text = result.reply
            exchange.reply = reply_text
            exchange.response_id = result.response_id
            exchange.tools_used = list(result.tools_used)
            exchange.iterations = result.iterations
            exchange.success = True
            session.last_response_id = result.response_id
            session.last_message_at = datetime.utcnow()
            ev["agente_ok"] = True
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            print(f"[bot.twilio-webhook] Agente falló: {exc}\n{tb}")
            reply_text = (
                "Disculpá, tuve un problema procesando tu consulta. Intentá de "
                "nuevo en un momento."
            )
            exchange.reply = reply_text
            exchange.success = False
            exchange.error = f"{type(exc).__name__}: {exc}"
            ev["agente_ok"] = False
            ev["error"] = f"agente: {type(exc).__name__}: {exc}"

        db.commit()

        try:
            twilio_client.send_whatsapp(to=from_phone, body=reply_text)
            ev["envio_ok"] = True
        except twilio_client.TwilioNotConfigured:
            print("[bot.twilio-webhook] Twilio no configurado; no se mandó respuesta.")
            ev["envio_ok"] = False
            ev["error"] = "twilio no configurado"
        except Exception as exc:  # noqa: BLE001
            print(f"[bot.twilio-webhook] Falló envío Twilio: {exc}")
            ev["envio_ok"] = False
            ev["error"] = f"envio: {type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 — un background task nunca debe reventar
        print(f"[bot.twilio-webhook] _process_message falló: {type(exc).__name__}: {exc}")
        ev["error"] = f"proceso: {type(exc).__name__}: {exc}"
    finally:
        db.close()


@router.post("/twilio-webhook", include_in_schema=False)
async def twilio_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    """Recibe un POST de Twilio cuando llega un WhatsApp. Le contesta a Twilio
    AL INSTANTE (TwiML vacío) y procesa el agente en segundo plano, mandando la
    respuesta por REST cuando termina. Así el ciclo de herramientas puede tardar
    sin que Twilio corte el webhook (~15s) y deje al usuario sin respuesta."""
    form = await request.form()
    params = {k: str(form[k]) for k in form.keys()}

    from_phone = params.get("From", "").strip()
    body = (params.get("Body") or "").strip()

    # Registro de diagnóstico (visible en /admin/health).
    ev: dict = {
        "at": datetime.utcnow().isoformat(),
        "from": from_phone,
        "body_len": len(body),
    }
    _LAST_WEBHOOKS.appendleft(ev)

    # Validación de firma — sin esto cualquiera con la URL podría hacernos gastar
    # tokens de OpenAI. Probamos varias variantes de URL (Render está detrás de
    # proxy y puede reconstruir http en vez de https).
    signature = request.headers.get("X-Twilio-Signature", "")
    urls = _candidate_urls(request)
    sig_ok = any(twilio_client.verify_signature(u, params, signature) for u in urls)
    ev["firma_ok"] = sig_ok
    if not sig_ok:
        ev["outcome"] = "firma_invalida"
        ev["urls_probadas"] = urls
        print(f"[bot.twilio-webhook] Firma inválida; rechazando. urls={urls}")
        return Response(status_code=403)

    # Whitelist: si el número no está habilitado se ignora en silencio. Los
    # "writers" (habilitados a CARGAR actividades) pasan aunque no estén en la
    # whitelist de lectura.
    w_role = agenda_writer.writer_role(from_phone)
    if from_phone and not _phone_allowed(from_phone) and not w_role:
        ev["outcome"] = "no_whitelist"
        print(f"[bot.twilio-webhook] Número no habilitado, ignorado: {from_phone}")
        return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")

    # Anti-replay: si ya procesamos este MessageSid (reintento de Twilio o replay
    # de un request firmado), no lo corremos de nuevo. Aplica a todo (incl. audios).
    if _already_processed(params.get("MessageSid", "")):
        ev["outcome"] = "duplicado"
        return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")

    # Writers: carga de actividades por voz + confirmación (única acción de
    # ESCRITURA del bot). Un audio arranca el flujo; un SÍ/NO confirma un borrador.
    if w_role:
        num_media = int(params.get("NumMedia", "0") or 0)
        media_url = params.get("MediaUrl0")
        media_type = params.get("MediaContentType0", "")
        if num_media and media_url and media_type.startswith("audio"):
            ev["outcome"] = "writer_voz"
            background_tasks.add_task(agenda_writer.handle_voice, from_phone, w_role, media_url, media_type, ev)
            return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")
        if body and agenda_writer.has_pending(from_phone):
            ev["outcome"] = "writer_confirm"
            background_tasks.add_task(agenda_writer.handle_confirmation, from_phone, body, w_role, ev)
            return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")
        # writer sin audio ni borrador pendiente → sigue como consulta normal (lectura).

    if not from_phone or not body:
        ev["outcome"] = "sin_texto"
        # Mensaje sin texto (media, sticker, etc.) — respondemos amable.
        if from_phone and twilio_client.is_configured():
            try:
                twilio_client.send_whatsapp(
                    to=from_phone,
                    body="Por ahora sólo entiendo mensajes de texto. ¿Me lo escribís?",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[bot.twilio-webhook] Falló mandar respuesta no-text: {exc}")
        return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")

    # Procesamos en segundo plano y le contestamos a Twilio YA.
    ev["outcome"] = "procesando"
    background_tasks.add_task(_process_message, from_phone, body, ev)
    return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")


# ---------------------------------------------------------------------------
# Admin: ver los últimos exchanges (debug).
# ---------------------------------------------------------------------------
@router.get(
    "/admin/exchanges",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def list_recent_exchanges(
    limit: int = 50,
    from_phone: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Devuelve los últimos N exchanges del log. Útil para ver qué le están
    preguntando al bot y qué responde, sin entrar a la DB a mano."""
    limit = max(1, min(limit, 200))
    q = db.query(db_models.BotExchange)
    if from_phone:
        q = q.filter(db_models.BotExchange.from_phone == from_phone)
    rows = q.order_by(db_models.BotExchange.created_at.desc()).limit(limit).all()

    return {
        "total": len(rows),
        "items": [
            {
                "id": r.id,
                "from_phone": r.from_phone,
                "message": r.message,
                "reply": r.reply,
                "tools_used": r.tools_used or [],
                "iterations": r.iterations,
                "success": r.success,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post(
    "/admin/scrape-pizarra",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_pizarra(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Dispara manualmente el scraper de precios pizarra. Útil para debug y
    para llenar la tabla la primera vez sin esperar el cron de las 10:30."""
    from bot.scraper_pizarra import scrape_precios_pizarra

    return scrape_precios_pizarra(db)


@router.post(
    "/admin/scrape-comentarios",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_comentarios(
    source: str = "local",
    max_pages: int = 1,
    max_upload: int = 25,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dispara manualmente el scraper de comentarios diarios. Útil para
    backfill inicial (subí max_pages a 5-10 para traer más historia)."""
    from bot.scraper_comentarios import scrape_comentarios

    return scrape_comentarios(db, source=source, max_pages=max_pages, max_upload_per_run=max_upload)


@router.post(
    "/admin/scrape-informativo",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_informativo(
    max_uploads: int = 20,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dispara manualmente el scraper de la edición vigente del informativo
    semanal. Útil para llenar la primera vez sin esperar al viernes."""
    from bot.scraper_informativo import scrape_current_edition

    return scrape_current_edition(db, max_uploads=max_uploads)


@router.post(
    "/admin/backfill-informativo",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_backfill_informativo(
    max_editions: int = 8,
    max_articles_total: int = 40,
    start_page: int = 0,
    pages_to_walk: int = 3,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """One-shot para traer ediciones pasadas del informativo semanal.
    Llamalo varias veces variando start_page (0, 3, 6, ...) para ir más
    atrás en el tiempo sin que un solo POST tarde una eternidad."""
    from bot.scraper_informativo import backfill_past_editions

    return backfill_past_editions(
        db,
        max_editions=max_editions,
        max_articles_total=max_articles_total,
        start_page=start_page,
        pages_to_walk=pages_to_walk,
    )


@router.post(
    "/admin/scrape-gea-panel",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_gea_panel(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Dispara manualmente el scraper del panel GEA. Útil para llenar la
    tabla la primera vez sin esperar el cron diario."""
    from bot.scraper_gea import scrape_gea_panel

    return scrape_gea_panel(db)


@router.post(
    "/admin/scrape-gea-informes",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_gea_informes(
    max_pages: int = 1,
    max_upload: int = 12,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dispara manualmente el scraper de informes mensuales GEA. Para
    backfill, subí max_pages (cada página tiene ~10 informes)."""
    from bot.scraper_gea import scrape_gea_informes

    return scrape_gea_informes(db, max_pages=max_pages, max_upload_per_run=max_upload)


@router.post(
    "/admin/scrape-gea-seguimiento",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_gea_seguimiento(
    max_upload: int = 12,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dispara el scraper de Seguimiento de cultivos GEA (informe semanal región
    núcleo). Sube al vector store 'gea' — lo cubre buscar_informe_gea."""
    from bot.scraper_gea import scrape_gea_seguimiento

    return scrape_gea_seguimiento(db, max_upload_per_run=max_upload)


@router.post(
    "/admin/scrape-gea-noticias",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_gea_noticias(
    max_upload: int = 12,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dispara el scraper de Noticias GEA (notas puntuales). Sube al vector store
    'gea' — lo cubre buscar_informe_gea."""
    from bot.scraper_gea import scrape_gea_noticias

    return scrape_gea_noticias(db, max_upload_per_run=max_upload)


# ---------------------------------------------------------------------------
# Archivo de newsletters "Conectados" — la app de Agenda de Comunicación
# (o la carga de la semilla histórica) postea acá para archivar un newsletter
# en el vector store del bot.
# ---------------------------------------------------------------------------
class _ConectadoBloque(BaseModel):
    titulo: Optional[str] = None
    texto: Optional[str] = None


class _ArchivarConectadoRequest(BaseModel):
    fecha: str  # 'YYYY-MM-DD'
    titulo: Optional[str] = None
    semana_key: Optional[str] = None
    # Uno de los dos: bloques (desde la app) o contenido ya armado (semilla).
    bloques: Optional[list[_ConectadoBloque]] = None
    contenido: Optional[str] = None


@router.post(
    "/admin/archivar-conectado",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def archivar_conectado_endpoint(
    payload: _ArchivarConectadoRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Archiva un newsletter Conectados en el vector store del bot.

    Acepta dos formas: `bloques` (título+texto por actividad, como los manda la
    app al exportar) o `contenido` (texto ya armado, para la semilla histórica).
    Idempotente por fecha/semana_key: re-archivar la misma semana reemplaza.
    """
    from config import BOT_OPENAI_API_KEY
    from openai import OpenAI
    from bot.ingest_conectados import archivar_conectado, construir_texto_conectado

    if not BOT_OPENAI_API_KEY:
        return {"status": "error", "error": "missing_openai_api_key"}

    if payload.contenido and payload.contenido.strip():
        contenido = payload.contenido.strip()
        n_bloques = None
    elif payload.bloques:
        bloques = [{"titulo": b.titulo, "texto": b.texto} for b in payload.bloques]
        contenido = construir_texto_conectado(f"CONECTADOS — {payload.fecha}", bloques)
        n_bloques = sum(1 for b in bloques if (b.get("titulo") or b.get("texto")))
    else:
        return {"status": "error", "error": "falta_contenido_o_bloques"}

    client = OpenAI(api_key=BOT_OPENAI_API_KEY, timeout=60.0, max_retries=2)
    return archivar_conectado(
        db,
        client,
        fecha=payload.fecha,
        contenido=contenido,
        titulo=payload.titulo,
        semana_key=payload.semana_key,
        n_bloques=n_bloques,
    )


# ---------------------------------------------------------------------------
# Coyuntura automática — genera borradores por búsqueda web (cada 72 hs o manual),
# se revisan/aprueban en la página /bot/coyuntura, y recién lo aprobado lo usa el
# bot. Todo protegido con auth (curaduría, sólo Comunicación).
# ---------------------------------------------------------------------------
class _CoyunturaAprobarRequest(BaseModel):
    tema: Optional[str] = None
    todo: bool = False


class _CoyunturaEditarRequest(BaseModel):
    tema: str
    contenido: str


@router.get("/admin/coyuntura", dependencies=[Depends(require_roles(ROLE_COMUNICACION))])
def coyuntura_listar(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Estado de todos los temas (aprobado + borrador pendiente) para la página
    de revisión."""
    from bot import coyuntura_auto

    return {"temas": coyuntura_auto.listar(db)}


def _bg_generar_coyuntura() -> None:
    """Corre la generación de borradores en segundo plano con su propia Session."""
    from bot.coyuntura_auto import generar_borradores

    db = SessionLocal()
    try:
        result = generar_borradores(db)
        print(f"[bot.coyuntura] generar (bg) → status={result.get('status')} "
              f"generados={result.get('generados')} fallidos={len(result.get('fallidos', []))}")
    except Exception as exc:  # noqa: BLE001
        print(f"[bot.coyuntura] generar (bg) falló: {type(exc).__name__}: {exc}")
    finally:
        db.close()


@router.post("/admin/coyuntura/generar", dependencies=[Depends(require_roles(ROLE_COMUNICACION))])
def coyuntura_generar(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Dispara la generación de borradores (búsqueda web) para todos los temas, en
    SEGUNDO PLANO (la búsqueda web de varios temas puede tardar 1-2 min). NO publica
    nada — quedan pendientes de aprobación. Refrescá la página para ver los borradores."""
    background_tasks.add_task(_bg_generar_coyuntura)
    return {"status": "iniciado", "detalle": "Generando borradores en segundo plano. Refrescá en 1-2 min."}


@router.post("/admin/coyuntura/aprobar", dependencies=[Depends(require_roles(ROLE_COMUNICACION))])
def coyuntura_aprobar(
    payload: _CoyunturaAprobarRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Aprueba un borrador (por `tema`) o todos (`todo=true`). Recién lo aprobado
    lo usa el bot."""
    from bot import coyuntura_auto

    if payload.todo:
        n = coyuntura_auto.aprobar_todo(db)
        return {"status": "ok", "aprobados": n}
    if not payload.tema:
        return {"status": "error", "error": "falta_tema_o_todo"}
    ok = coyuntura_auto.aprobar(db, payload.tema)
    return {"status": "ok" if ok else "error", "tema": payload.tema, "aprobado": ok}


@router.post("/admin/coyuntura/editar", dependencies=[Depends(require_roles(ROLE_COMUNICACION))])
def coyuntura_editar(
    payload: _CoyunturaEditarRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reemplaza el borrador de un tema con texto editado a mano (queda pendiente
    de aprobación)."""
    from bot import coyuntura_auto

    ok = coyuntura_auto.editar_borrador(db, payload.tema, payload.contenido)
    return {"status": "ok" if ok else "error", "tema": payload.tema}


@router.post(
    "/admin/scrape-capacita",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_capacita(
    fetch_details: bool = True,
    max_detail_fetches: int = 60,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dispara manualmente el scraper del catálogo de BCR Capacita. Útil
    para llenar la tabla la primera vez sin esperar el cron del lunes."""
    from bot.scraper_capacita import scrape_capacita

    return scrape_capacita(db, fetch_details=fetch_details, max_detail_fetches=max_detail_fetches)


@router.post(
    "/admin/scrape-innova-novedades",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_innova_novedades(
    max_upload: int = 15,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dispara manualmente el scraper de novedades de BCR Innova. Útil
    para backfill inicial."""
    from bot.scraper_innova_novedades import scrape_innova_novedades

    return scrape_innova_novedades(db, max_upload_per_run=max_upload)


@router.post(
    "/admin/scrape-startups-innova",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def trigger_scrape_startups_innova(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Dispara manualmente el scraper del Startup Network."""
    from bot.scraper_startups import scrape_startups_innova

    return scrape_startups_innova(db)


@router.get(
    "/admin/ingested",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def list_ingested(
    source: str = "informativo",
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lista los items ya ingestados por fuente. Útil para auditar si un
    artículo/comentario específico está o no en el vector store.

    source: 'informativo' | 'comentarios' | 'gea_informes'
    """
    if source == "informativo":
        rows = (
            db.query(db_models.IngestedInformativoArticle)
            .order_by(db_models.IngestedInformativoArticle.ingested_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "source": "informativo",
            "total": len(rows),
            "items": [
                {
                    "slug": r.slug,
                    "edicion_numero": r.edicion_numero,
                    "fecha": r.fecha,
                    "titulo": r.titulo,
                    "seccion": r.seccion,
                    "url": r.url,
                    "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
                }
                for r in rows
            ],
        }
    if source == "comentarios":
        rows = (
            db.query(db_models.IngestedComentario)
            .order_by(db_models.IngestedComentario.ingested_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "source": "comentarios",
            "total": len(rows),
            "items": [
                {
                    "source": r.source,
                    "comentario_id": r.comentario_id,
                    "fecha": r.fecha,
                    "url": r.url,
                    "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
                }
                for r in rows
            ],
        }
    if source == "gea_informes":
        rows = (
            db.query(db_models.IngestedGeaReport)
            .order_by(db_models.IngestedGeaReport.ingested_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "source": "gea_informes",
            "total": len(rows),
            "items": [
                {
                    "slug": r.slug,
                    "fecha": r.fecha,
                    "titulo": r.titulo,
                    "autor": r.autor,
                    "url": r.url,
                    "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
                }
                for r in rows
            ],
        }
    return {"error": f"source desconocido: {source!r}", "valid": ["informativo", "comentarios", "gea_informes"]}


@router.post("/admin/setup-menu", dependencies=[Depends(require_roles(ROLE_COMUNICACION))])
def setup_menu(db: Session = Depends(get_db)) -> dict[str, Any]:
    """(Re)crea el template del menú (list-picker) en Twilio y guarda su
    ContentSid en bot_config. Útil para iterar el texto/opciones del menú."""
    sid = ensure_menu_content_sid(db, force=True)
    return {"content_sid": sid}


@router.get("/admin/menu-preview", dependencies=[Depends(require_roles(ROLE_COMUNICACION))])
def menu_preview(opt: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Devuelve el texto que respondería una opción del menú, sin mandar WhatsApp.
    Para revisar el formato con datos reales. opt: agenda|precios|informativo|gea|asuntos|conectados"""
    if opt not in ("agenda", "precios", "informativo", "gea", "asuntos", "conectados"):
        raise HTTPException(400, "opción inválida")
    return {"opcion": opt, "reply": menu_handlers.handle(opt, db)}


@router.get(
    "/admin/health",
    dependencies=[Depends(require_roles(ROLE_COMUNICACION))],
)
def health_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Diagnóstico rápido — qué hay configurado y qué no, y estado de los
    crons del scheduler (último firing y próximo)."""
    from config import BOT_OPENAI_API_KEY, BOT_OPENAI_MODEL, BOT_TWILIO_WHATSAPP_FROM
    from bot.openai_vector_stores import get_vector_store_id
    from bot.scheduler import scheduler

    yesterday = datetime.utcnow() - timedelta(hours=24)
    recent_count = db.query(db_models.BotExchange).filter(
        db_models.BotExchange.created_at >= yesterday
    ).count()
    failures_24h = db.query(db_models.BotExchange).filter(
        db_models.BotExchange.created_at >= yesterday,
        db_models.BotExchange.success.is_(False),
    ).count()

    # Cuándo fue la última ingesta exitosa de cada fuente — eso nos dice si
    # los crons están firmando (más útil que mirar la config aislada).
    last_pizarra = (
        db.query(db_models.PrecioPizarra.scraped_at)
        .order_by(db_models.PrecioPizarra.scraped_at.desc())
        .first()
    )
    last_comentario = (
        db.query(db_models.IngestedComentario.ingested_at)
        .order_by(db_models.IngestedComentario.ingested_at.desc())
        .first()
    )
    last_informativo = (
        db.query(db_models.IngestedInformativoArticle.ingested_at)
        .order_by(db_models.IngestedInformativoArticle.ingested_at.desc())
        .first()
    )
    last_gea_panel = (
        db.query(db_models.EstimacionGea.scraped_at)
        .order_by(db_models.EstimacionGea.scraped_at.desc())
        .first()
    )
    last_gea_informe = (
        db.query(db_models.IngestedGeaReport.ingested_at)
        .order_by(db_models.IngestedGeaReport.ingested_at.desc())
        .first()
    )

    def _iso_or_none(row):
        return row[0].isoformat() if row and row[0] else None

    # Estado del scheduler in-process.
    scheduler_info: dict[str, Any] = {
        "running": getattr(scheduler, "running", False),
        "timezone": str(getattr(scheduler, "timezone", None)),
        "jobs": [],
    }
    try:
        for job in scheduler.get_jobs():
            scheduler_info["jobs"].append({
                "id": job.id,
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "trigger": str(job.trigger),
                "coalesce": job.coalesce,
                "max_instances": job.max_instances,
            })
    except Exception as exc:  # noqa: BLE001
        scheduler_info["error"] = f"{type(exc).__name__}: {exc}"

    return {
        "openai_configured": bool(BOT_OPENAI_API_KEY),
        "openai_model": BOT_OPENAI_MODEL,
        "twilio_configured": twilio_client.is_configured(),
        "twilio_from": BOT_TWILIO_WHATSAPP_FROM,
        "whitelist": {"restringido": bool(_WHITELIST), "cantidad": len(_WHITELIST)},
        "menu_content_sid": (lambda r: r.value if r else None)(
            db.query(db_models.BotConfig).filter(db_models.BotConfig.key == "menu_content_sid").first()),
        "ultimos_webhooks": list(_LAST_WEBHOOKS),
        "vector_stores": {
            "institucional": get_vector_store_id(db, "institucional"),
            "informativo": get_vector_store_id(db, "informativo"),
            "comentarios": get_vector_store_id(db, "comentarios"),
            "gea": get_vector_store_id(db, "gea"),
        },
        "exchanges_24h": recent_count,
        "failures_24h": failures_24h,
        "last_ingest": {
            "precios_pizarra": _iso_or_none(last_pizarra),
            "comentario_diario": _iso_or_none(last_comentario),
            "informativo_semanal": _iso_or_none(last_informativo),
            "gea_panel": _iso_or_none(last_gea_panel),
            "gea_informes": _iso_or_none(last_gea_informe),
        },
        "scheduler": scheduler_info,
        "now_utc": datetime.utcnow().isoformat(),
    }
