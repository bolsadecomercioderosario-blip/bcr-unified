/**
 * Recordatorios operativos del equipo de Comunicación.
 *
 * Estos NO son actividades (no van como filas en la lista, no son editables
 * desde la UI ni tienen botón propio en la top-bar). Son fechas que el equipo
 * tiene que tener presentes — visualmente aparecen como un banner discreto
 * debajo del header del grupo HOY / MAÑANA / ESTA SEMANA, igual que las
 * efemérides.
 *
 * Cada entrada tiene fecha completa (año/mes/día) — no son recurrentes anuales
 * como las efemérides. Cada año hay que renovar este listado.
 *
 * Notas operativas:
 * - "Informe GEA Mensual": sale ese día (generalmente a la tarde). Al día
 *   siguiente el equipo graba un video contándolo.
 * - "Informe ICA": sale ese día a las 8:30. El día anterior hay que armar
 *   una gacetilla de prensa, validarla y dejarla lista para enviar.
 */
export const RECORDATORIOS = [
    // 2026
    { fecha: "2026-05-13", titulo: "Informe GEA Mensual" },
    { fecha: "2026-05-29", titulo: "Informe ICA" },
    { fecha: "2026-06-10", titulo: "Informe GEA Mensual" },
    { fecha: "2026-06-30", titulo: "Informe ICA" },
    { fecha: "2026-07-08", titulo: "Informe GEA Mensual" },
    { fecha: "2026-07-31", titulo: "Informe ICA" },
    { fecha: "2026-08-12", titulo: "Informe GEA Mensual" },
    { fecha: "2026-08-31", titulo: "Informe ICA" },
    { fecha: "2026-09-09", titulo: "Informe GEA Mensual" },
    { fecha: "2026-09-30", titulo: "Informe ICA" },
    { fecha: "2026-10-14", titulo: "Informe GEA Mensual" },
    { fecha: "2026-10-30", titulo: "Informe ICA" },
    { fecha: "2026-11-11", titulo: "Informe GEA Mensual" },
    { fecha: "2026-11-30", titulo: "Informe ICA" },
    { fecha: "2026-12-03", titulo: "Informe ICA" },
    { fecha: "2026-12-09", titulo: "Informe GEA Mensual" },
];
