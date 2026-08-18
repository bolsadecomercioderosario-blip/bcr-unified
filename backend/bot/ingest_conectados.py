"""
Archivado de newsletters "Conectados" para el bot.

A diferencia de los otros insumos del bot (que se scrapean de la web), los
Conectados se archivan por PUSH: la app de Agenda de Comunicación, al exportar
el newsletter, manda los bloques (título + texto) a un endpoint que llama a
`archivar_conectado`. También sirve para cargar la semilla histórica (mails
viejos ya limpiados a texto).

Cada newsletter se sube como un TXT al vector store "conectados" (RAG) y se
trackea en la tabla ingested_conectados. La key estable es `semana_key`
(normalmente la fecha YYYY-MM-DD): re-archivar la misma semana REEMPLAZA el
archivo anterior en el vector store en vez de duplicar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from bot.db_models import IngestedConectado
from bot.openai_vector_stores import ensure_vector_store_id, upload_text_file


def construir_texto_conectado(titulo_doc: str, bloques: list[dict[str, Any]]) -> str:
    """Arma el texto plano del newsletter a partir de los bloques
    (título + texto de cada actividad), en orden. Formato pensado para RAG:
    un encabezado con la fecha y luego cada bloque como "• Título" + cuerpo.
    """
    lines: list[str] = [titulo_doc.strip(), ""]
    for b in bloques:
        titulo = (b.get("titulo") or b.get("title") or "").strip()
        texto = (b.get("texto") or b.get("text") or "").strip()
        if not titulo and not texto:
            continue
        if titulo:
            lines.append(f"• {titulo}")
        if texto:
            lines.append(texto)
        lines.append("")
    return "\n".join(lines).strip()


def _borrar_archivo_anterior(client: OpenAI, vector_store_id: str, file_id: str) -> None:
    """Borra el file viejo del vector store y del storage de OpenAI. Tolerante
    a fallos: si ya no existe, seguimos (el objetivo es no acumular basura)."""
    try:
        client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[bot.conectados] no se pudo quitar file del VS ({file_id}): {exc}")
    try:
        client.files.delete(file_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[bot.conectados] no se pudo borrar file de OpenAI ({file_id}): {exc}")


def archivar_conectado(
    db: Session,
    client: OpenAI,
    *,
    fecha: str,
    contenido: str,
    titulo: str | None = None,
    semana_key: str | None = None,
    n_bloques: int | None = None,
) -> dict[str, Any]:
    """Sube un newsletter Conectados (texto ya armado) al vector store y lo
    trackea. Idempotente por `semana_key`: si ya existía, reemplaza el archivo.

    - fecha: 'YYYY-MM-DD' del newsletter.
    - contenido: texto plano ya limpio (encabezado + bloques).
    - semana_key: clave de dedupe; por defecto la fecha.
    """
    contenido = (contenido or "").strip()
    if not contenido:
        return {"status": "error", "error": "contenido_vacio"}

    semana_key = (semana_key or fecha or "").strip()
    if not semana_key:
        return {"status": "error", "error": "falta_fecha_o_semana_key"}

    titulo = titulo or f"Conectados {fecha}"
    vs_id = ensure_vector_store_id(db, "conectados", client)

    existing = (
        db.query(IngestedConectado)
        .filter(IngestedConectado.semana_key == semana_key)
        .first()
    )
    replaced = False
    if existing and existing.openai_file_id:
        _borrar_archivo_anterior(client, vs_id, existing.openai_file_id)
        replaced = True

    filename = f"conectados_{semana_key}.txt"
    file_id = upload_text_file(client, vs_id, filename, contenido)

    now = datetime.utcnow()
    if existing is None:
        db.add(IngestedConectado(
            semana_key=semana_key,
            fecha=fecha,
            titulo=titulo,
            n_bloques=n_bloques,
            openai_file_id=file_id,
            ingested_at=now,
        ))
    else:
        existing.fecha = fecha
        existing.titulo = titulo
        existing.n_bloques = n_bloques
        existing.openai_file_id = file_id
        existing.ingested_at = now
    db.commit()

    return {
        "status": "ok",
        "semana_key": semana_key,
        "fecha": fecha,
        "titulo": titulo,
        "replaced": replaced,
        "chars": len(contenido),
        "openai_file_id": file_id,
        "vector_store_id": vs_id,
    }
