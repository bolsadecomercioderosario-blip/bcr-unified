# Módulo Aapresid 2026

App interna para organizar la presencia de la BCR y sus áreas en el **Congreso
Aapresid 2026** (Salón Metropolitano, Rosario, 4-6 ago 2026). Es un módulo más de
`bcr-unified` (FastAPI + JS vanilla + Postgres/Render), servido en **`/aapresid`**.

## Estado: Fases 1-2 hechas

**Fase 1 — cimiento:**
- **Login por usuario** (email + contraseña; auth propia del módulo, con roles
  `admin` / `editor`). Necesaria para la auditoría (`created_by`/`updated_by`).
- **Modelo de datos completo** (todas las tablas `aap_*`) + **seed**: evento, los
  8 turnos (el martes sin Mañana), áreas de la BCR, un admin y datos de ejemplo
  (marcados con `[Ejemplo]`).
- **Tablero** de 8 bloques con KPIs, responsables destacados y aviso de turnos
  sin responsable.
- **ABM de personas y áreas** (áreas: sólo admin; no se borran si tienen
  personas — se desactivan).
- **Presencias**: crear / editar / eliminar / duplicar en otro turno, sin
  permitir la misma persona dos veces en el mismo turno. Alta de persona nueva
  sin salir del formulario.
- **Colaborativo**: datos en la DB compartida + polling cada 15s.

**Fase 2 — reuniones:**
- **ABM de reuniones**: título, empresa/contraparte, fecha, hora inicio/fin,
  lugar, responsable, participantes BCR, participantes externos, descripción,
  observaciones y estado (Tentativa/Confirmada/Realizada/Cancelada).
- **Turno automático** según el horario de inicio.
- **Validaciones**: duras (título/fecha/hora/responsable) + advertencias no
  bloqueantes (superposición, fuera de horario de presencia, responsable
  ausente del turno).
- Se ven **en el bloque** correspondiente y en una **agenda cronológica**.

**Fase 3 — vistas y filtros:**
- **Panel de indicadores** completo (personas, presencias, reuniones,
  tentativas, confirmadas, turnos sin responsable, personas con reuniones
  superpuestas + personas por día).
- **Barra de filtros** en el tablero: buscador general + día, turno, área,
  responsable, estado de reunión y "sólo sin responsable", con "Limpiar".
- **Vista por persona** (turnos, horarios, reuniones donde participa / es
  responsable) y **vista por área** (personas, cobertura por turno, reuniones,
  turnos sin representantes del área). Se abren clickeando en las listas.

Pendiente: export CSV, audit_log/historial.

## Variables de entorno

Ver [`.env.example`](.env.example). Todas opcionales:
- `AAPRESID_SECRET` — secreto para firmar tokens (cambiar en prod).
- `AAPRESID_ADMIN_EMAIL` / `AAPRESID_ADMIN_PASSWORD` — admin inicial (default
  `admin@aapresid.bcr` / `aapresid2026`, **cambiar**).

## Acceso inicial

Primer login: `admin@aapresid.bcr` / `aapresid2026` (o lo que definan las env
vars). Desde ese admin se administran áreas, personas y (próximamente) usuarios.

## Correr / probar localmente

Forma parte de `bcr-unified`, así que arranca con el server principal:

```powershell
cd backend
python app.py   # http://localhost:8000  → /aapresid/
```

Sin env vars usa SQLite local y crea el evento + turnos + admin en el primer
arranque (migración/seed idempotentes). Las integraciones externas (Drive, X,
etc.) no se tocan: este módulo no las usa.

## Modelo de datos

Tablas `aap_events`, `aap_shifts`, `aap_areas`, `aap_people`, `aap_attendance`,
`aap_meetings`, `aap_meeting_participants`, `aap_users`, `aap_audit_log`
(definidas en [`models.py`](models.py); se crean con `Base.metadata.create_all` +
seed en `migrate.py`).
