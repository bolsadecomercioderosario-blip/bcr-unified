# Módulo Aapresid 2026

App interna, simple, para organizar la presencia de la BCR en el **Congreso
Aapresid 2026** (Salón Metropolitano, Rosario, 4-6 ago 2026). Módulo de
`bcr-unified` (FastAPI + JS vanilla + Postgres/Render), servido en **`/aapresid`**.

## Qué hace (versión simple)

**Una sola vista: el tablero.**
- Arriba, indicadores: reuniones, confirmadas, tentativas, turnos sin responsable.
- Debajo, **3 columnas (una por día)**: Martes / Miércoles / Jueves, con los turnos
  apilados en orden (el martes no tiene Mañana).
- **Por turno**:
  - **Responsable del turno** (texto libre): quien corresponda escribe el nombre.
    Si no hay, un botón "Designar responsable".
  - **Reuniones** del turno + botón "+ Reunión".
- **Reunión** (simple): descripción, responsable (texto libre), área de la BCR
  (lista), estado (Tentativa/Confirmada/Realizada/Cancelada) y dónde
  (Stand BCR u otro espacio). Crear / editar / eliminar.
- **Colaborativo**: DB compartida + refresco automático (polling 15s).

Login por usuario (email + contraseña, roles admin/editor) para poder auditar
los cambios. Cada cambio en reuniones/turnos queda en un log interno (`aap_audit_log`).

## Variables de entorno

Ver [`.env.example`](.env.example) (todas opcionales):
- `AAPRESID_SECRET` — secreto para firmar tokens (cambiar en prod).
- `AAPRESID_ADMIN_EMAIL` / `AAPRESID_ADMIN_PASSWORD` — admin inicial (default
  `admin@aapresid.bcr` / `aapresid2026`, **cambiar**).

## Acceso inicial

Primer login: `admin@aapresid.bcr` / `aapresid2026` (o lo que definan las env vars).

## Correr localmente

```powershell
cd backend
python app.py    # http://localhost:8000 → /aapresid/
```

Crea el evento + turnos + admin en el primer arranque (migración/seed
idempotentes). No usa integraciones externas.

## Datos

Tablas `aap_*` (evento, turnos, áreas, personas, presencias, reuniones,
usuarios, audit). La versión simple del tablero usa turnos (con responsable),
áreas (para la lista) y reuniones. Las tablas de personas/presencias quedan en
el modelo por si se retoma una versión más detallada.
