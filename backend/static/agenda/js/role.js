/**
 * Rol del usuario logueado, leído del auth centralizado (static/auth.js).
 *
 * Roles:
 *   - 'secretaria'   → administra la Agenda de Compromisos (Mesa Ejecutiva).
 *   - 'comunicacion' → la app completa (coberturas). Default.
 *   - 'area'         → un área interna (DIyEE, Innova, CAC, BCR Digital…). El
 *                      rol crudo es 'area:<slug>'; getAreaSlug() da el slug.
 *
 * Si no hay rol guardado (sesión vieja), asumimos 'comunicacion'.
 */
export function getRoleRaw() {
    return (window.BCRAuth && window.BCRAuth.getRole && window.BCRAuth.getRole()) || '';
}

export function getRole() {
    const r = getRoleRaw();
    if (r === 'secretaria') return 'secretaria';
    if (r.startsWith('area:')) return 'area';
    return 'comunicacion';
}

export function getAreaSlug() {
    const r = getRoleRaw();
    return r.startsWith('area:') ? r.slice('area:'.length) : '';
}

export const isSecretaria = () => getRole() === 'secretaria';
export const isComunicacion = () => getRole() === 'comunicacion';
export const isArea = () => getRole() === 'area';
