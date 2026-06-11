/**
 * Rol del usuario logueado, leído del auth centralizado (static/auth.js).
 *
 * Dos roles:
 *   - 'secretaria'   → carga la Agenda de Compromisos. UI reducida.
 *   - 'comunicacion' → la app completa (default).
 *
 * Si no hay rol guardado (sesión vieja anterior a este cambio), asumimos
 * 'comunicacion' para no romperle el acceso a quien ya estaba logueado.
 *
 * v1: la separación es SÓLO de frontend (el backend no la enforcea todavía).
 */
export function getRole() {
    const r = (window.BCRAuth && window.BCRAuth.getRole && window.BCRAuth.getRole()) || '';
    return r === 'secretaria' ? 'secretaria' : 'comunicacion';
}

export const isSecretaria = () => getRole() === 'secretaria';
export const isComunicacion = () => getRole() === 'comunicacion';
