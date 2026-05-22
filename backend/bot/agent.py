"""
Orquestación del agente del bot BCR.

run_agent() recibe el mensaje del usuario, llama a OpenAI con las tools
registradas y maneja el loop de tool-calling: el modelo puede pedir ejecutar
una o varias tools, nosotros las ejecutamos (DB o file_search), y le devolvemos
el output para que sintetice la respuesta final.

Usamos la Responses API porque algunas tools internas (buscar_*) hacen
file_search sobre vector stores y mantener una sola API en todo el bot evita
mezclar surfaces.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from config import BOT_OPENAI_API_KEY, BOT_OPENAI_MODEL

from bot import tools


# Tope de iteraciones de tool-calling para evitar loops infinitos si el modelo
# se queda en bucle pidiendo herramientas sin sintetizar respuesta.
_MAX_TOOL_ITERATIONS = 6


SYSTEM_INSTRUCTIONS_TEMPLATE = """\
Sos el asistente virtual de la Bolsa de Comercio de Rosario (BCR). Respondés \
consultas que llegan por WhatsApp, en español rioplatense, de forma breve y \
clara.

Fecha actual: {today_iso} ({today_human}).

Herramientas disponibles:

A. AGENDA
- consultar_agenda: actividades, eventos, encuentros, capacitaciones, visitas \
en la agenda de la BCR. Para preguntas con fecha.

B. RAG (búsqueda en documentos)
- buscar_institucional: qué es la BCR, áreas (BCRlabs, BCRinnova, BCRcapacita, \
BCRcultura, BCRdigital), autoridades, mercados (Físico de Granos, A3, MAV, \
Rosgan), cámaras arbitrales, fundación, centro de convenciones, oficina de \
asociados, museo, contactos institucionales.
- buscar_informativo: análisis del Informativo Semanal (viernes). Temas \
económicos/sectoriales: acuerdos comerciales, campañas agrícolas, exportaciones, \
política agropecuaria, geopolítica del agro.
- buscar_comentario_diario: comentarios diarios del mercado (Rosario y Chicago). \
Para preguntas de coyuntura: '¿qué pasó con la soja hoy?', 'cómo cerró el mercado'.
- buscar_informe_gea: informes mensuales de Estimación Nacional de Producción de \
GEA (Guía Estratégica para el Agro). Para preguntas sobre el porqué de los cambios \
en estimaciones, condiciones climáticas, decisiones de siembra, ajustes de producción.

C. DATA ESTRUCTURADA (números exactos)
- get_precios_pizarra: precios de soja/trigo/maíz/otros del Mercado Físico de Rosario. \
Para preguntas con respuesta numérica: 'cuánto está la soja', 'precio del trigo'.
- get_estimaciones_gea: estimaciones de producción nacional (área, rinde, producción) \
para soja/trigo/maíz, campaña vigente y anterior. Para preguntas de magnitud: \
'cuánto se va a producir de soja', 'qué área tiene el trigo esta campaña'.

Reglas de uso de las tools:
1. Si la pregunta es sobre fechas/eventos/actividades → consultar_agenda. \
Calculá los rangos en base a la fecha actual: 'esta semana' = hoy → próximo \
domingo; 'mañana' = hoy+1; 'este mes' = hoy → fin de mes; 'cuándo es X' = \
rango amplio (60-90 días) con filtro_titulo.

2. Para preguntas que combinan número + contexto: llamá a la tool estructurada \
PRIMERO (get_precios_pizarra o get_estimaciones_gea), y si necesitás "por qué", \
llamá también a la narrativa correspondiente (buscar_comentario_diario o \
buscar_informe_gea). Ejemplo: '¿cuánto está la soja y por qué bajó?' → \
get_precios_pizarra + buscar_comentario_diario en paralelo.

3. NO llames a tools que no hagan falta — cada llamada cuesta. Si una sola \
herramienta basta, usá esa.

4. Si una tool devuelve estado 'datos_no_disponibles_aun', avisale al usuario \
que esa fuente todavía está en desarrollo y compartile el link oficial que \
trae el campo 'detalle'.

5. Si una tool devuelve 'No se encontró información' o 'vector_store_no_configurado', \
NO inventes — decílo claro al usuario y, si hace sentido, sugerí reformular o \
consultar otra fuente oficial.

6. Cuando cites información de informativos, comentarios o informes GEA, incluí \
la fecha o autor si la tool te lo devolvió.

Formato de respuesta (WhatsApp):
- Oraciones cortas, lenguaje directo, español rioplatense.
- Listas con bullets ('•') o numeración cuando hay varios ítems.
- Sin emojis salvo que sumen mucho.
- Sin firmas tipo 'atte.', 'saludos cordiales'. Esto es WhatsApp, no un mail.
- Si la pregunta queda totalmente fuera de lo que las tools cubren, decilo \
con honestidad y sugerí dónde más buscar (sitio bcr.com.ar, o pedir al \
contacto del área correspondiente).
"""


_SPANISH_MONTHS = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}
_SPANISH_WEEKDAYS = {
    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
    4: "viernes", 5: "sábado", 6: "domingo",
}


def _build_system_instructions(today: date) -> str:
    today_human = (
        f"{_SPANISH_WEEKDAYS[today.weekday()]} "
        f"{today.day} de {_SPANISH_MONTHS[today.month]} de {today.year}"
    )
    return SYSTEM_INSTRUCTIONS_TEMPLATE.format(
        today_iso=today.isoformat(),
        today_human=today_human,
    )


@dataclass
class AgentResult:
    reply: str
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0
    response_id: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)


def run_agent(
    message: str,
    from_phone: str | None,
    db: Session,
    previous_response_id: str | None = None,
) -> AgentResult:
    """Corre el agente sobre un mensaje del usuario y devuelve la respuesta.

    Si `previous_response_id` viene seteado, encadena con ese turno previo
    para mantener memoria conversacional. Si no, arranca de cero con las
    instrucciones del sistema. El llamador puede leer `result.response_id`
    y pasarlo en el próximo turno.

    Patrón de continuación: en la primera llamada del turno mandamos el
    mensaje + las instrucciones; en las siguientes (loop de tool-calling)
    pasamos previous_response_id y SÓLO los function_call_output nuevos.
    Esto es lo que la Responses API exige para modelos de razonamiento
    (gpt-5-mini, o1, o3, etc.).
    """
    if not BOT_OPENAI_API_KEY:
        return AgentResult(
            reply=(
                "El bot no está configurado correctamente (falta OPENAI_API_KEY "
                "en el servidor). Avisale al admin."
            ),
            debug={"error": "missing_openai_api_key"},
        )

    client = OpenAI(api_key=BOT_OPENAI_API_KEY)
    ctx = tools.ToolContext(db=db, openai_client=client)

    tools_used: list[str] = []
    tool_args_log: list[dict[str, Any]] = []

    # current_response_id arranca con lo que nos pasó el caller (memoria del
    # turno anterior) o None si es el primer mensaje de la conversación.
    current_response_id: str | None = previous_response_id

    # Primera iteración: mandamos el mensaje del usuario. Si hay memoria
    # previa, encadenamos vía previous_response_id; si no, mandamos las
    # instrucciones del sistema.
    next_input: list[dict[str, Any]] = [{"role": "user", "content": message}]

    for iteration in range(_MAX_TOOL_ITERATIONS):
        create_kwargs: dict[str, Any] = {
            "model": BOT_OPENAI_MODEL,
            "input": next_input,
            "tools": tools.TOOL_DEFINITIONS,
        }
        if current_response_id is None:
            # Primer turno de la conversación — pasamos las instrucciones.
            create_kwargs["instructions"] = _build_system_instructions(date.today())
        else:
            create_kwargs["previous_response_id"] = current_response_id

        response = client.responses.create(**create_kwargs)
        current_response_id = response.id

        function_calls = [item for item in response.output if item.type == "function_call"]

        # Sin más function_calls → tenemos la respuesta final.
        if not function_calls:
            return AgentResult(
                reply=(response.output_text or "").strip()
                or "No supe cómo responder a eso. ¿Podés reformular?",
                tools_used=tools_used,
                iterations=iteration + 1,
                response_id=response.id,
                debug={"tool_args": tool_args_log, "response_id": response.id},
            )

        # Ejecutamos las tools pedidas y armamos el input de la próxima
        # iteración SÓLO con los function_call_output. Los reasoning items y
        # function_call items ya quedaron asociados a previous_response_id
        # del lado de OpenAI — no los tenemos que reenviar.
        next_input = []
        for call in function_calls:
            try:
                args = json.loads(call.arguments) if call.arguments else {}
            except json.JSONDecodeError:
                args = {}

            tools_used.append(call.name)
            tool_args_log.append({"name": call.name, "arguments": args})

            output = tools.execute_tool(call.name, args, ctx=ctx)

            next_input.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(output, ensure_ascii=False, default=str),
            })

    # Pasamos el tope de iteraciones — algo raro.
    return AgentResult(
        reply=(
            "Estuve pensando demasiado y no llegué a una respuesta clara. "
            "¿Podés intentar la pregunta de otra forma?"
        ),
        tools_used=tools_used,
        iterations=_MAX_TOOL_ITERATIONS,
        response_id=current_response_id,
        debug={"tool_args": tool_args_log, "exhausted_iterations": True},
    )
