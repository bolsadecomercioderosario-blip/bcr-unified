# Duplicar el servicio en Render para testing de Sistemas

Objetivo: levantar una **copia completa** de la app en Render (servicio + base de
datos propios, separados de producción) con las integraciones externas
**encendidas** (Drive, WhatsApp, Twitter, OpenAI, etc.), para que Sistemas pueda
probar todo end-to-end sin tocar producción.

> **Regla de oro del entorno de testing:** usar credenciales **sandbox/separadas**
> para todo lo que dispara acciones hacia afuera. Si el testing usa las
> credenciales reales de prod, cada prueba **publica tweets reales, manda
> WhatsApp reales y crea carpetas reales** en el Drive institucional.

---

## Paso 0 — Inventario: ¿qué credenciales ya existen?

La verdad de qué hay disponible vive en el **Render de producción**:

1. Entrá a Render → servicio de producción → pestaña **Environment**.
2. Anotá la **lista de nombres** de variables que ya están cargadas (no hace
   falta copiar los valores secretos para esto).
3. Compará contra la tabla del Paso 3. Lo que esté en prod ya existe; lo que
   falte hay que conseguirlo.

Para el testing, además, vas a necesitar credenciales **sandbox** nuevas para
Twilio, Twitter y (opcional) Drive — ver Paso 4.

---

## Paso 1 — Crear el servicio duplicado

**Opción A (recomendada) — con el Blueprint del repo:**

1. Render → **New → Blueprint**.
2. Conectá este repo y elegí la branch (`main`).
3. Render lee `render.yaml` y crea **`bcr-unified-test`** + la DB
   **`bcr-unified-test-db`**. No toca el servicio de producción.

**Opción B — a mano:**

1. Render → **New → Web Service** → mismo repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `cd backend && python app.py`
2. Render → **New → PostgreSQL** para la base de datos del testing.
3. Cargá todas las variables del Paso 3 a mano.

---

## Paso 2 — Base de datos separada

El testing usa su **propia** base de datos (`bcr-unified-test-db`), vacía. Las
tablas se crean solas al arrancar (`create_all` + `migrate()`). Así Sistemas
puede cargar, borrar y romper datos sin afectar producción.

---

## Paso 3 — Cargar las variables de entorno

En el servicio de testing → **Environment**. El `render.yaml` ya deja
declaradas las que tienen valor fijo; las marcadas como secreto (`sync: false`)
hay que completarlas a mano.

| Variable | Para qué | En testing |
|---|---|---|
| `EXTERNAL_INTEGRATIONS_ENABLED` | Master switch de integraciones | `true` |
| `OPENAI_API_KEY` | OpenAI (bot, buscador, agenda, clips) | se puede compartir con prod |
| `BOT_OPENAI_MODEL` | Modelo del bot | `gpt-5-mini` |
| `BOT_VS_INSTITUCIONAL` / `_INFORMATIVO` / `_COMENTARIOS` / `_GEA` | Vector stores del bot | mismos que prod |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | WhatsApp (Twilio) | **sandbox de Twilio** |
| `TWILIO_WHATSAPP_FROM` | Número emisor de WhatsApp | número del sandbox de Twilio |
| `X_API_KEY` / `_API_KEY_SECRET` / `_ACCESS_TOKEN` / `_ACCESS_TOKEN_SECRET` | Twitter / X | **cuenta de prueba** o dejar vacías |
| `CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET` | CDN de imágenes | se puede compartir con prod |
| `OAUTH_REDIRECT_URI` | Callback OAuth de Google | la **URL nueva** del testing (ver Paso 4) |
| `DRIVE_PARENT_FOLDER_ID` | Carpeta madre de Drive | carpeta de la **cuenta de Google de prueba** |
| `SANTIAGO_WEBHOOK_URL` | Webhook a Pipedream | webhook de prueba o vacío |
| `METRICAS_SHEET_CSV_URL` / `_EDIT_URL` / `_TTL` | Dashboard de métricas | mismos que prod (es solo lectura) |
| `AGENDA_PASSWORD` / `SECGRAL_PASSWORD` | Passwords de acceso | **distintos** a prod |
| `SESSION_TOKEN` | Token de sesión | que Render lo genere |
| `COMPROMISOS_PUBLIC_TOKEN` | Token de la agenda pública | el que quieras |
| `DATABASE_URL` | Conexión a la DB | la inyecta Render solo |

---

## Paso 4 — Las integraciones que necesitan atención especial

### Google Drive + YouTube — usar una cuenta de Google de PRUEBA (no la de BCR)

La idea: crear una **cuenta de Google nueva, solo para testing**, y que el
entorno de pruebas escriba en SU Drive, nunca en el de BCR.

1. Crear una cuenta de Google de prueba.
2. En esa cuenta, crear una **carpeta en su Drive** que haga de carpeta madre,
   y copiar el **ID** de esa carpeta (está en la URL: `.../folders/EL_ID`).
   Ese ID va en la variable `DRIVE_PARENT_FOLDER_ID` del testing.
3. En **Google Cloud Console** (un proyecto de esa cuenta de prueba) crear unas
   credenciales OAuth y bajar el `client_secret.json`.
4. Generar el `token.json` corriendo `python scripts/reauth_google.py` en tu PC
   y **logueándote con la cuenta de prueba** (no la de BCR).
5. Subir `client_secret.json` y `token.json` como **Secret Files** al servicio
   de testing (Environment → Secret Files).
6. Setear `OAUTH_REDIRECT_URI` con la URL del testing y **registrar esa URL** en
   Google Cloud Console → Credentials → Authorized redirect URIs.

> El código ya soporta `DRIVE_PARENT_FOLDER_ID`. Si no se setea, cae a la
> carpeta institucional de prod — por eso en testing **siempre** hay que
> setearla a la carpeta de la cuenta de prueba.

### Twitter / X — usar una cuenta de prueba (no @BolsaRosario)
No hay sandbox: cualquier credencial válida publica de verdad. Por eso:
- Crear una **cuenta de X de prueba** + su app de developer, y usar esas 4
  credenciales (`X_*`) en el testing, o
- Dejar las 4 variables `X_*` **vacías** → el módulo queda deshabilitado en test.

### WhatsApp (Twilio)
Twilio tiene un **WhatsApp Sandbox** gratis: da un `ACCOUNT_SID`,
`AUTH_TOKEN` y un número (`whatsapp:+1415...`) de prueba. Ideal para testing:
no manda mensajes a números reales salvo los que se unieron al sandbox.

---

## Paso 5 — Verificar

1. Abrí la URL del servicio de testing → debería cargar el hub en `/`.
2. `GET /health` → devuelve la versión (debería ser la misma que prod).
3. Probar una acción de cada integración con las credenciales sandbox.

---

## Resumen de seguridad

- ✅ Compartibles con prod: OpenAI, Cloudinary, Métricas (solo lectura).
- ⚠️ Sandbox/separadas obligatorio: Twilio (WhatsApp), Twitter/X, Drive.
- ⚠️ Passwords y tokens de acceso: **distintos** a producción.
- ❌ Nunca escribir credenciales en `render.yaml` ni en el repo.
