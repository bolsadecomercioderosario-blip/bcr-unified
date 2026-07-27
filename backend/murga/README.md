# Módulo `murga` — Sorteo del estreno "El Más Acá"

Mini app de **un solo uso** para el estreno de la murga *Y Parió La Abuela*
(8 de agosto). La gente escanea un QR, completa un formulario, y antes de la
función el presentador sortea una remera entre los inscriptos.

Vive dentro de `bcr-unified` como un módulo más (FastAPI + SQLAlchemy + frontend
estático). No agrega dependencias nuevas al backend: el Excel se genera en el
browser con SheetJS (CDN).

## Las 4 URLs

| URL | Quién | Qué |
|---|---|---|
| `/murga/` | **Público** (QR) | Formulario: nombre, celular, última voluntad → confirmación personalizada |
| `/murga/voluntades?k=TOKEN` | Presentador | Pantalla de últimas voluntades (nombre + voluntad, **sin** celular). Auto-refresh cada 5 s + botón refrescar. |
| `/murga/sorteo?k=TOKEN` | Presentador | Ruleta con suspenso → ganador. Re-sortear y "marcar como ganador/a" (lo excluye del próximo sorteo). |
| `/murga/export?k=TOKEN` | Presentador | Descarga un `.xlsx` con todo: nombre, celular, voluntad, fecha/hora. |

**El QR apunta a `https://TU-DOMINIO/murga/`** (con la barra final).

## Seguridad

Las tres vistas del presentador se protegen con un **token en la URL** (`?k=`),
validado en el backend contra la env var `SORTEO_TOKEN`. Sin token válido, el API
devuelve 401 y la vista muestra "acceso restringido". No es Fort Knox — es para
que no entre cualquiera que adivine la ruta, que es justo lo que pediste.

El presentador se guarda los 3 links completos (con `?k=...`) en favoritos.

## Variable de entorno

| Variable | Default (dev) | Prod |
|---|---|---|
| `SORTEO_TOKEN` | `abuela2026` | **Seteala en Render** con un valor propio antes del estreno. |

Es la única variable propia del módulo. La base de datos usa la `DATABASE_URL`
que ya comparte todo `bcr-unified` (Postgres en Render, SQLite en local).

## Correr localmente

Desde la raíz del repo:

```bash
pip install -r requirements.txt
cd backend
python app.py
```

Abrí:
- Formulario: http://localhost:8000/murga/
- Presentador: http://localhost:8000/murga/sorteo?k=abuela2026 (y `/voluntades`, `/export`)

Sin `SORTEO_TOKEN` seteada, el token local es `abuela2026`.

> Nota Windows: si el arranque de `app.py` falla por `tzdata` (lo usa el módulo
> `bot`, no `murga`), instalá el paquete: `pip install tzdata`.

## Desplegar

Ya se despliega solo: es parte de `bcr-unified`, que corre en Render. Al hacer
**merge/push a `main`**, Render redeploya y `/murga/` queda online en el mismo
dominio del resto de los servicios. Pasos:

1. `SORTEO_TOKEN` → seteala en Render (Environment) con tu valor.
2. Deploy (push a `main`).
3. La tabla `murga_participantes` se crea sola al arrancar (`create_all`).
4. **URL final para el QR:** `https://<tu-dominio-render>/murga/`

## Branding

Dejá los PNG en `backend/static/murga/assets/`:
- `logo.png` — logo de la murga
- `titulo.png` — lettering del título

Mientras no existan, el header muestra un texto de respaldo. Ver
`assets/LEEME.txt`.

## Después del estreno

Es de un solo uso. Para bajarlo: sacá el include del router y los handlers en
`app.py` (o dejalo — no molesta). Para exportar y guardar los datos antes de
borrar: `/murga/export?k=TOKEN`.
