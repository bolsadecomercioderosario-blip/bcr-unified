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
- consultar_agenda: actividades, eventos, encuentros, capacitaciones, visitas \
en la agenda de la BCR. Para preguntas con fecha.
- buscar_institucional: info sobre qué es la BCR, áreas (BCRlabs, BCRinnova, \
BCRcapacita, BCRcultura, BCRdigital), autoridades, mercados (Físico de Granos, \
A3, MAV, Rosgan), cámaras arbitrales, fundación, centro de convenciones, \
oficina de asociados, museo, contactos institucionales.
- buscar_informativo: análisis del Informativo Semanal (sale los viernes). \
Para preguntas sobre temas económicos/sectoriales: acuerdos comerciales, \
campañas agrícolas, exportaciones, política agropecuaria, geopolítica del agro.
- buscar_comentario_diario: comentarios diarios del mercado (Rosario y Chicago). \
Para preguntas de coyuntura: '¿qué pasó con la soja hoy?', 'cómo cerró el mercado'.

Reglas de uso de las tools:
1. Si la pregunta es sobre fechas/eventos/actividades → consultar_agenda. \
Calculá los rangos en base a la fecha actual: 'esta semana' = hoy → próximo \
domingo; 'mañana' = hoy+1; 'este mes' = hoy → fin de mes; 'cuándo es X' = \
rango amplio (60-90 días) con filtro_titulo.

2. Si la pregunta NO especifica si es agenda, informativo o comentario: \
elegí la tool por el tipo de información que necesita la respuesta. Si una \
pregunta puede tener componentes de mercado actual + análisis (ej. 'qué pasa \
con la soja'), podés llamar a buscar_comentario_diario Y buscar_informativo \
en la misma iteración (el sistema te lo permite). NO llames a tools que no \
hagan falta — cada llamada cuesta.

3. Si una tool devuelve 'No se encontró información', NO inventes — decílo \
al usuario y, si hace sentido, sugerí reformular o consultar otra fuente \
oficial (sitio web, contacto del área).

4. Si una tool devuelve un error 'vector_store_no_configurado', avisale al \
usuario que esa fuente todavía no está disponible y respondé con lo que sí \
puedas (otras tools que sí funcionen).

5. Cuando cites información del informativo o de comentarios diarios, incluí \
la fecha o número de edición si la tool te lo devolvió, así el usuario sabe \
de cuándo es el dato.

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
    debug: dict[str, Any] = field(default_factory=dict)


def run_agent(message: str, from_phone: str | None, db: Session) -> AgentResult:
    """Corre el agente sobre un único mensaje del usuario y devuelve la respuesta.

    Patrón de continuación: en la primera llamada mandamos el mensaje + las
    instrucciones; en las siguientes pasamos previous_response_id y SÓLO los
    function_call_output nuevos. Esto es lo que la Responses API exige para
    modelos de razonamiento (gpt-5-mini, o1, o3, etc.): cada function_call
    está asociada server-side a un item de 'reasoning' que el cliente no
    debería reconstruir manualmente. Sin previous_response_id la API rompe
    con 'function_call was provided without its required reasoning item'.

    Sin historial conversacional cross-mensaje todavía (el bot es stateless
    entre mensajes — eso se suma con Twilio en 2.5 + persistencia en DB).
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
    instructions = _build_system_instructions(date.today())

    tools_used: list[str] = []
    tool_args_log: list[dict[str, Any]] = []
    previous_response_id: str | None = None

    # Primera iteración: mandamos el mensaje del usuario. Siguientes: sólo
    # los outputs de las tools, encadenados via previous_response_id.
    next_input: list[dict[str, Any]] = [{"role": "user", "content": message}]

    for iteration in range(_MAX_TOOL_ITERATIONS):
        create_kwargs: dict[str, Any] = {
            "model": BOT_OPENAI_MODEL,
            "input": next_input,
            "tools": tools.TOOL_DEFINITIONS,
        }
        if previous_response_id is None:
            create_kwargs["instructions"] = instructions
        else:
            create_kwargs["previous_response_id"] = previous_response_id

        response = client.responses.create(**create_kwargs)
        previous_response_id = response.id

        function_calls = [item for item in response.output if item.type == "function_call"]

        # Sin más function_calls → tenemos la respuesta final.
        if not function_calls:
            return AgentResult(
                reply=(response.output_text or "").strip()
                or "No supe cómo responder a eso. ¿Podés reformular?",
                tools_used=tools_used,
                iterations=iteration + 1,
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
        debug={"tool_args": tool_args_log, "exhausted_iterations": True},
    )
