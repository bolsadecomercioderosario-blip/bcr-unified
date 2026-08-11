# Módulo `corte` — Encuesta versión reducida de "El Más Acá"

Encuesta interna para que los murguistas armen su **corte ideal** del
espectáculo en ~30 min (máx 35). Cada persona marca los bloques que conservaría
y la app le muestra en vivo cuánto dura su selección. El organizador ve un
ranking de bloques por votos y puede probar combinaciones reales.

Vive dentro de `bcr-unified` como un módulo más (FastAPI + SQLAlchemy + frontend
estático). Sin dependencias nuevas.

## URLs

| URL | Quién | Qué |
|---|---|---|
| `/corte/` | **Murguistas** (link de WhatsApp) | Encuesta: nombre + selección de bloques con contador en vivo |
| `/corte/resultados?k=TOKEN` | Organizador | Ranking por votos + calculadora de duración del corte |

## Cómo funciona

- **Encuesta**: pide el nombre y muestra los 24 bloques agrupados por sección
  narrativa. Al tildar, una barra fija abajo muestra `MM:SS / 30:00`, cambia de
  color por zona (margen / ideal / extendida / pasado) y **bloquea el envío si
  supera 35:00**. El total se recalcula server-side al guardar (no se confía en
  el cliente).
- **Re-editar**: no hay login. Se guarda por nombre (upsert). Si la persona
  vuelve con el mismo nombre (o desde el mismo celular), se le carga su selección
  anterior para editarla.
- **Resultados**: total de respuestas + tabla de bloques con votos, % y duración,
  ordenable por votos o por orden del show. Tildando filas se calcula la
  **duración del corte resultante**; el botón "Auto ~30'" arma un corte inicial
  con los más votados.

## Datos del espectáculo

Los bloques, duraciones, grupos y los objetivos (30' / máx 35') están en
[`data.py`](data.py). Es la fuente única: para cambiar una duración o agregar/
sacar un bloque, se edita ahí (los `id` son estables, no cambiarlos porque son
la clave que se guarda en cada respuesta).

## Variable de entorno

| Variable | Default (dev) | Prod |
|---|---|---|
| `CORTE_TOKEN` | `corte2026` | Seteala en Render con un valor propio para los resultados. |

La base de datos usa la `DATABASE_URL` compartida de `bcr-unified` (Postgres en
Render, SQLite en local). La tabla `corte_respuestas` se crea sola al arrancar.

## Correr localmente

```bash
cd backend
python app.py
```
- Encuesta: http://localhost:8000/corte/
- Resultados: http://localhost:8000/corte/resultados?k=corte2026

## Desplegar

Es parte de `bcr-unified`: push a `main` → Render redeploya y queda online en el
mismo dominio. Link para el grupo: `https://<dominio>/corte/`.
