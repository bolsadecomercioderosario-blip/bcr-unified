import { state } from '../state.js';

export function renderSanti(container) {
    // ----- Fechas de referencia (idéntica lógica a List.js) -----
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayISO = today.toISOString().split('T')[0];

    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowISO = tomorrow.toISOString().split('T')[0];

    const currentDayOfWeek = today.getDay();
    const daysToSunday = currentDayOfWeek === 0 ? 0 : 7 - currentDayOfWeek;
    const endOfThisWeek = new Date(today);
    endOfThisWeek.setDate(today.getDate() + daysToSunday);
    const endOfThisWeekISO = endOfThisWeek.toISOString().split('T')[0];

    // ----- Filtrado de tareas de Santi -----
    // Mismo filtro que antes (canales que disparan tarea AV) + pasadas afuera.
    const avActivities = state.activities
        .filter(a => {
            if (a.is_custom) return false;
            if (a.date < todayISO) return false;  // sin pasadas
            const isStoryVideo = a.channels.includes('Instagram Story') && a.story_type !== 'Layout';
            const isYoutube = a.channels.includes('YouTube');
            return isStoryVideo || isYoutube;
        })
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            return (a.time || '').localeCompare(b.time || '');
        });

    // ----- Agrupado -----
    const GROUPS = ['HOY', 'MAÑANA', 'ESTA SEMANA', 'MÁS ADELANTE'];
    const groups = { 'HOY': [], 'MAÑANA': [], 'ESTA SEMANA': [], 'MÁS ADELANTE': [] };

    avActivities.forEach(act => {
        if (act.date === todayISO) groups['HOY'].push(act);
        else if (act.date === tomorrowISO) groups['MAÑANA'].push(act);
        else if (act.date <= endOfThisWeekISO) groups['ESTA SEMANA'].push(act);
        else groups['MÁS ADELANTE'].push(act);
    });

    // ----- Render -----
    const wrapper = document.createElement('div');
    wrapper.className = 'content-wrapper';

    const formatFullDate = (dateStr) => {
        const days = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
        const [year, month, day] = dateStr.split('-');
        const date = new Date(year, month - 1, day);
        return `${days[date.getDay()]} ${parseInt(day)}/${parseInt(month)}`;
    };

    if (avActivities.length === 0) {
        wrapper.innerHTML = `
            <div class="list-group">
                <div class="group-header">
                    <span class="group-title">TAREAS DE SANTI (AV EDITOR)</span>
                    <div class="group-line"></div>
                </div>
                <div style="text-align: center; padding: 4rem; color: var(--text-muted);">
                    No hay tareas audiovisuales pendientes.
                </div>
            </div>
        `;
        container.appendChild(wrapper);
        return;
    }

    // Construyo el cuerpo: encabezado de columnas + un sub-header por cada grupo
    // no vacío, con sus filas. Una sola tabla unificada para que las columnas
    // se alineen verticalmente entre grupos.
    const groupsWithContent = GROUPS.filter(g => groups[g].length > 0);

    const rowsHTML = groupsWithContent.map(groupName => {
        const groupRows = groups[groupName].map(act => `
            <tr onclick="window.openActivityDetail('${act.id}')" style="cursor: pointer;">
                <td style="font-size: 0.8rem; color: var(--text-muted); font-weight: 500;">
                    ${formatFullDate(act.date)}
                </td>
                <td style="font-weight: 500;">${act.time || ''}</td>
                <td>
                    <div style="font-weight: 600;">${act.title}</div>
                    ${act.description ? `<div style="font-size: 0.8rem; color: var(--text-muted);">${act.description.substring(0, 80)}${act.description.length > 80 ? '…' : ''}</div>` : ''}
                </td>
                <td>
                    <span class="badge" style="background: ${act.story_type === 'Video' ? '#dcfce7' : '#fef9c3'}; color: ${act.story_type === 'Video' ? '#166534' : '#854d0e'}; font-size: 0.7rem; padding: 0.2rem 0.5rem; border-radius: 999px; font-weight: 600;">
                        ${act.story_type || 'Video'}
                    </span>
                </td>
            </tr>
        `).join('');

        return `
            <tr class="santi-group-row">
                <td colspan="4" style="background: #f8fafc; padding: 0.85rem 1rem 0.5rem; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);">
                    <div style="display: flex; align-items: center; gap: 0.6rem;">
                        <span style="font-size: 0.75rem; font-weight: 700; color: var(--primary); letter-spacing: 0.06em;">${groupName}</span>
                        <span style="font-size: 0.7rem; color: var(--text-muted); background: white; padding: 0.1rem 0.45rem; border-radius: 999px; border: 1px solid var(--border);">${groups[groupName].length}</span>
                    </div>
                </td>
            </tr>
            ${groupRows}
        `;
    }).join('');

    wrapper.innerHTML = `
        <div class="list-group">
            <div class="group-header">
                <span class="group-title">TAREAS DE SANTI (AV EDITOR)</span>
                <div class="group-line"></div>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width: 100px;">Fecha</th>
                        <th style="width: 70px;">Hora</th>
                        <th>Actividad / Video</th>
                        <th style="width: 100px;">Tipo</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHTML}
                </tbody>
            </table>
        </div>
    `;

    container.appendChild(wrapper);
}
