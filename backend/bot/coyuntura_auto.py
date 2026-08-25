"""
Coyuntura automática: genera el "estado actual" (novedades) por tema estratégico
buscando en la web, con supervisión humana antes de que el bot lo use.

Flujo:
  1. Cada 72 hs (o manual) `generar_borradores()` recorre los temas activos, hace
     una búsqueda web por cada uno (tool `web_search` de la Responses API) y guarda
     el resultado como BORRADOR pendiente en la tabla coyuntura_auto.
  2. Una persona revisa/edita/aprueba desde la página /bot/coyuntura.
  3. El bot (consultar_asuntos_publicos) lee SÓLO el contenido APROBADO.

Anclaje anti-alucinación: el prompt obliga a reportar sólo lo que devuelve la
búsqueda, con fuente y fecha, y a decir "Sin novedades..." si no hay nada.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from config import BOT_COYUNTURA_AUTO_MODEL, BOT_OPENAI_API_KEY
from bot.db_models import CoyunturaAuto


# Subconjunto ACTIVO de temas (arranque). Ampliar agregando entradas.
# `contexto` enfoca la búsqueda para que no se disperse.
TEMAS: list[dict[str, Any]] = [
    {
        "tema": "hidrovia",
        "titulo": "Hidrovía / Vía Navegable Troncal",
        "orden": 1,
        "contexto": (
            "Concesión de la Vía Navegable Troncal (Hidrovía Paraguay-Paraná) en "
            "Argentina: obras de dragado y balizamiento, peajes, cronograma del "
            "concesionario (Jan de Nul / Servimagnus), Consejo de Control, impacto "
            "en el complejo portuario del Gran Rosario."
        ),
    },
    {
        "tema": "retenciones",
        "titulo": "Retenciones / Derechos de Exportación",
        "orden": 2,
        "contexto": (
            "Derechos de exportación (retenciones) del agro en Argentina: cambios "
            "de alícuotas para soja, trigo, maíz; cronograma de reducción; decretos; "
            "impacto en la cadena agroexportadora."
        ),
    },
    {
        "tema": "mercosur_ue",
        "titulo": "Mercosur–Unión Europea / Biodiesel",
        "orden": 3,
        "contexto": (
            "Acuerdo Mercosur-Unión Europea y su implementación; regulaciones "
            "ambientales europeas (EUDR, iLUC) sobre biodiesel de soja; impacto para "
            "Argentina y el complejo agroindustrial."
        ),
    },
    {
        "tema": "accesos_viales",
        "titulo": "Accesos viales a los puertos del Gran Rosario",
        "orden": 4,
        "contexto": (
            "Obras e infraestructura vial de acceso a las terminales portuarias del "
            "Gran Rosario (Santa Fe): tercer carril autopista Rosario-Santa Fe, RP 91, "
            "Ruta A012, Circuito de Ingreso a Puertos, financiamiento y mantenimiento."
        ),
    },
    {
        "tema": "financiamiento_obra_publica",
        "titulo": "Financiamiento de obra pública vía mercado de capitales",
        "orden": 5,
        "contexto": (
            "Financiamiento de infraestructura/obra pública a través del mercado de "
            "capitales en Argentina, especialmente Santa Fe y municipios: emisiones, "
            "fideicomisos, títulos provinciales, casos concretos."
        ),
    },
]

_TEMAS_BY_KEY = {t["tema"]: t for t in TEMAS}


_SYSTEM = """\
Sos un analista que redacta un briefing BREVE y factual para la Mesa Ejecutiva de \
la Bolsa de Comercio de Rosario (BCR). Tu tarea: buscar en la web novedades \
RECIENTES (últimas ~2 semanas) sobre el tema indicado, en Argentina.

REGLAS ESTRICTAS (anti-invención):
- Afirmá SÓLO lo que encontraste en las fuentes de la búsqueda. NO inventes datos, \
fechas, cifras ni declaraciones.
- Cada novedad con su FUENTE y FECHA aproximada.
- Si NO hay novedades relevantes y confiables recientes, respondé EXACTAMENTE: \
"Sin novedades relevantes en los últimos días."
- Sé conciso: 3 a 6 viñetas como máximo. Tono sobrio, sin opinión ni adjetivación.
- Español rioplatense, listo para leer en el teléfono. Sin títulos con # ni tablas.
- Cerrá con una línea "Fuentes: <medios y fechas>".
"""


def _crear_cliente() -> OpenAI | None:
    if not BOT_OPENAI_API_KEY:
        return None
    return OpenAI(api_key=BOT_OPENAI_API_KEY, timeout=90.0, max_retries=1)


def _buscar_tema(client: OpenAI, t: dict[str, Any]) -> str:
    """Corre una búsqueda web + resumen para un tema. Devuelve el texto.

    Intenta con la tool `web_search`; si la versión del modelo/SDK usa el nombre
    `web_search_preview`, reintenta con ese.
    """
    user = (
        f"Tema: {t['titulo']}.\n"
        f"Foco de la búsqueda: {t['contexto']}\n"
        f"Fecha de hoy: {date.today().isoformat()}.\n"
        "Buscá y resumí las novedades recientes siguiendo las reglas."
    )
    for tool_name in ("web_search", "web_search_preview"):
        try:
            resp = client.responses.create(
                model=BOT_COYUNTURA_AUTO_MODEL,
                tools=[{"type": tool_name}],
                instructions=_SYSTEM,
                input=[{"role": "user", "content": user}],
            )
            return (resp.output_text or "").strip()
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            # Si el error es por el nombre de la tool, probamos el otro nombre.
            if "web_search" in msg and tool_name == "web_search":
                print(f"[coyuntura_auto] '{tool_name}' falló ({exc}); reintento con web_search_preview")
                continue
            raise
    return ""


def _upsert_borrador(db: Session, t: dict[str, Any], contenido: str) -> None:
    row = db.query(CoyunturaAuto).filter(CoyunturaAuto.tema == t["tema"]).first()
    now = datetime.utcnow()
    if row is None:
        row = CoyunturaAuto(tema=t["tema"], titulo=t["titulo"], orden=t["orden"])
        db.add(row)
    row.titulo = t["titulo"]
    row.orden = t["orden"]
    row.contenido_borrador = contenido
    row.borrador_at = now
    row.borrador_pendiente = True


def generar_borradores(db: Session) -> dict[str, Any]:
    """Genera un borrador nuevo por cada tema activo (búsqueda web). NO toca lo
    aprobado. Devuelve un resumen de lo generado."""
    client = _crear_cliente()
    if client is None:
        return {"status": "error", "error": "missing_openai_api_key"}

    generados, fallidos = [], []
    for t in TEMAS:
        try:
            contenido = _buscar_tema(client, t)
            if not contenido:
                fallidos.append({"tema": t["tema"], "error": "respuesta_vacia"})
                continue
            _upsert_borrador(db, t, contenido)
            generados.append(t["tema"])
        except Exception as exc:  # noqa: BLE001
            fallidos.append({"tema": t["tema"], "error": f"{type(exc).__name__}: {exc}"})
    db.commit()
    return {
        "status": "ok" if generados else "error",
        "generados": generados,
        "fallidos": fallidos,
        "generado_at": datetime.utcnow().isoformat(),
    }


def aprobar(db: Session, tema: str) -> bool:
    """Aprueba el borrador de un tema: pasa a ser lo que sirve el bot."""
    row = db.query(CoyunturaAuto).filter(CoyunturaAuto.tema == tema).first()
    if row is None:
        return False
    row.contenido_aprobado = row.contenido_borrador
    row.aprobado_at = datetime.utcnow()
    row.borrador_pendiente = False
    db.commit()
    return True


def aprobar_todo(db: Session) -> int:
    """Aprueba todos los borradores pendientes. Devuelve cuántos aprobó."""
    rows = db.query(CoyunturaAuto).filter(CoyunturaAuto.borrador_pendiente.is_(True)).all()
    now = datetime.utcnow()
    for row in rows:
        row.contenido_aprobado = row.contenido_borrador
        row.aprobado_at = now
        row.borrador_pendiente = False
    db.commit()
    return len(rows)


def editar_borrador(db: Session, tema: str, contenido: str) -> bool:
    """Reemplaza el borrador de un tema con texto editado a mano (queda pendiente
    de aprobación)."""
    row = db.query(CoyunturaAuto).filter(CoyunturaAuto.tema == tema).first()
    if row is None:
        meta = _TEMAS_BY_KEY.get(tema)
        if meta is None:
            return False
        row = CoyunturaAuto(tema=tema, titulo=meta["titulo"], orden=meta["orden"])
        db.add(row)
    row.contenido_borrador = contenido
    row.borrador_at = datetime.utcnow()
    row.borrador_pendiente = True
    db.commit()
    return True


def listar(db: Session) -> list[dict[str, Any]]:
    """Estado de todos los temas para la página de revisión."""
    rows = {r.tema: r for r in db.query(CoyunturaAuto).all()}
    out = []
    for t in TEMAS:
        r = rows.get(t["tema"])
        out.append({
            "tema": t["tema"],
            "titulo": t["titulo"],
            "orden": t["orden"],
            "contenido_aprobado": (r.contenido_aprobado if r else None),
            "aprobado_at": (r.aprobado_at.isoformat() if (r and r.aprobado_at) else None),
            "contenido_borrador": (r.contenido_borrador if r else None),
            "borrador_at": (r.borrador_at.isoformat() if (r and r.borrador_at) else None),
            "borrador_pendiente": bool(r.borrador_pendiente) if r else False,
        })
    out.sort(key=lambda x: x["orden"])
    return out


def get_estado_actual_aprobado(db: Session) -> str | None:
    """Arma el texto de 'estado actual' con lo APROBADO de cada tema, para que lo
    lea el bot. Devuelve None si no hay nada aprobado todavía."""
    rows = {r.tema: r for r in db.query(CoyunturaAuto).all()}
    bloques = []
    for t in sorted(TEMAS, key=lambda x: x["orden"]):
        r = rows.get(t["tema"])
        if r and r.contenido_aprobado and r.contenido_aprobado.strip():
            fecha = r.aprobado_at.date().isoformat() if r.aprobado_at else ""
            encabezado = f"*{t['titulo']}*" + (f" (actualizado {fecha})" if fecha else "")
            bloques.append(f"{encabezado}\n{r.contenido_aprobado.strip()}")
    if not bloques:
        return None
    return "\n\n".join(bloques)
