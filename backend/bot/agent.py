"""
Orquestación del agente del bot BCR.

run_agent() recibe el mensaje del usuario, llama a OpenAI con las tools
registradas y maneja el loop de tool-calling: el modelo puede pedir ejecutar
una o varias tools, nosotros las ejecutamos contra la DB, y le devolvemos
el output para que sintetice la respuesta final.

Usamos la Responses API porque en próximos chunks vamos a sumar file_search
(2.3) sobre vector stores, que se integra nativamente en esa API. Mantener
una sola API para todo el bot evita pegar APIs distintas.
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
_MAX_TOOL_ITERATIONS = 5


SYSTEM_INSTRUCTIONS_TEMPLATE = """\
Sos el asistente virtual de la Bolsa de Comercio de Rosario (BCR). Respondés \
consultas que llegan por WhatsApp, en español rioplatense, de forma breve y \
clara.

Fecha actual: {today_iso} ({today_human}).

Herramientas disponibles:
- consultar_agenda: para preguntas sobre actividades, eventos, encuentros, \
capacitaciones, visitas o cualquier cosa con fecha en la agenda de la BCR.

Reglas de uso:
1. Si la consulta es sobre eventos/actividades/capacitaciones/fechas, USÁ \
consultar_agenda. No respondas de memoria — los eventos cambian.
2. Cuando llames a consultar_agenda, calculá los rangos de fechas en base a \
la fecha actual indicada arriba. Ejemplos:
   - "esta semana" → desde hoy hasta el próximo domingo
   - "mañana" → desde hoy+1 hasta hoy+1
   - "este mes" → desde hoy hasta el último día del mes
   - "cuándo es el Encuentro de Abogados" → consultá un rango amplio (60-90 \
días desde hoy) y pasá filtro_titulo='Encuentro de Abogados'.
3. Si la tool devuelve 0 actividades, decilo claro (no inventes eventos).
4. Si la tool devuelve actividades, listá las relevantes con fecha, hora, \
título y ubicación. Mantené el formato corto, pensado para WhatsApp.
5. Si la pregunta NO es de agenda (mercado, precios, comentarios, info \
institucional), avisá amablemente que estás en versión limitada y que pronto \
vas a poder ayudar con eso también. No inventes la respuesta.

Tono: amable, directo, sin formalismos exagerados. Sin emojis a menos que \
sumen mucho. No firmes con "atte." ni cosas similares — esto es WhatsApp.
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

    Sin historial conversacional todavía (el bot es stateless por ahora — eso
    se sumará cuando enchufemos Twilio en 2.5 con persistencia en DB).
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
    instructions = _build_system_instructions(date.today())

    # `input` arranca con el mensaje del usuario y va creciendo con las
    # function_calls del modelo y los function_call_output que devolvemos.
    conversation_input: list[dict[str, Any]] = [
        {"role": "user", "content": message},
    ]

    tools_used: list[str] = []
    tool_args_log: list[dict[str, Any]] = []

    for iteration in range(_MAX_TOOL_ITERATIONS):
        response = client.responses.create(
            model=BOT_OPENAI_MODEL,
            instructions=instructions,
            input=conversation_input,
            tools=tools.TOOL_DEFINITIONS,
        )

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

        # Ejecutamos cada tool pedida y sumamos input para la próxima iteración.
        for call in function_calls:
            try:
                args = json.loads(call.arguments) if call.arguments else {}
            except json.JSONDecodeError:
                args = {}

            tools_used.append(call.name)
            tool_args_log.append({"name": call.name, "arguments": args})

            output = tools.execute_tool(call.name, args, db=db)

            # La Responses API necesita que metamos en el input tanto la
            # llamada como el output, en ese orden, para que el modelo entienda
            # la continuidad.
            conversation_input.append(call.model_dump(exclude_unset=True))
            conversation_input.append({
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
