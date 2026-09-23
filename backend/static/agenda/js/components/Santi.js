import { state } from '../state.js';

// ¿Esta actividad requiere una tarea de video de Santi?
// (IG Story en formato Video —no Layout— o YouTube).
function needsVideo(act) {
    const isStoryVideo = (act.channels || []).includes('Instagram Story') && act.story_type !== 'Layout';
    const isYoutube = (act.channels || []).includes('YouTube');
    return isStoryVideo || isYoutube;
}

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

    // ----- Toda la agenda visible (sin bloques de newsletter ni pasadas) -----
    // Santi ve TODO; las tareas de video se resaltan (needsVideo).
    const activities = state.activities
        .filter(a => {
            if (a.is_custom) return false;      // bloques de Conectados, no son actividades
            if (a.date < todayISO) return false; // sin pasadas
            return true;
        })
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            return (a.time || '').localeCompare(b.time || '');
        });

    const videoCount = activities.filter(needsVideo).length;

    // ----- Agrupado -----
    const GROUPS = ['HOY', 'MAÑANA', 'ESTA SEMANA', 'MÁS ADELANTE'];
    const groups = { 'HOY': [], 'MAÑANA': [], 'ESTA SEMANA': [], 'MÁS ADELANTE': [] };

    activities.forEach(act => {
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

    const header = `
        <div class="group-header">
            <span class="group-title">AGENDA — SANTI (AV EDITOR)</span>
            <div class="group-line"></div>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-muted); margin: 0 0 0.75rem;">
            Se listan todas las actividades. Las <b style="color: var(--primary);">resaltadas</b> son las que requieren video.
        </p>`;

    if (activities.length === 0) {
        wrapper.innerHTML = `
            <div class="list-group">
                ${header}
                <div style="text-align: center; padding: 4rem; color: var(--text-muted);">
                    No hay actividades en agenda.
                </div>
            </div>
        `;
        container.appendChild(wrapper);
        return;
    }

    // Una sola tabla unificada (columnas alineadas entre grupos), con sub-header
    // por grupo no vacío. Las filas de video se resaltan.
    const groupsWithContent = GROUPS.filter(g => groups[g].length > 0);

    const rowsHTML = groupsWithContent.map(groupName => {
        const groupVideo = groups[groupName].filter(needsVideo).length;
        const groupRows = groups[groupName].map(act => {
            const isVid = needsVideo(act);
            // Resalte de la fila de video: fondo suave + borde izquierdo primario.
            const rowStyle = isVid
                ? 'cursor: pointer; background: #eef2ff;'
                : 'cursor: pointer;';
            const accent = isVid
                ? 'border-left: 3px solid var(--primary);'
                : 'border-left: 3px solid transparent;';
            const tipo = isVid
                ? `<span class="badge" style="background: #dcfce7; color: #166534; font-size: 0.7rem; padding: 0.2rem 0.5rem; border-radius: 999px; font-weight: 600; display: inline-flex; align-items: center; gap: 0.3rem;"><i data-lucide="video" style="width: 12px; height: 12px;"></i> Video</span>`
                : '';
            return `
            <tr onclick="window.openActivityDetail('${act.id}')" style="${rowStyle}">
                <td style="font-size: 0.8rem; color: var(--text-muted); font-weight: 500; ${accent}">
                    ${formatFullDate(act.date)}
                </td>
                <td style="font-weight: 500;">${act.time || ''}</td>
                <td>
                    <div style="font-weight: 600; ${isVid ? 'color: var(--primary);' : ''}">${act.title}</div>
                    ${act.description ? `<div style="font-size: 0.8rem; color: var(--text-muted);">${act.description.substring(0, 80)}${act.description.length > 80 ? '…' : ''}</div>` : ''}
                </td>
                <td>${tipo}</td>
            </tr>`;
        }).join('');

        return `
            <tr class="santi-group-row">
                <td colspan="4" style="background: #f8fafc; padding: 0.85rem 1rem 0.5rem; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);">
                    <div style="display: flex; align-items: center; gap: 0.6rem;">
                        <span style="font-size: 0.75rem; font-weight: 700; color: var(--primary); letter-spacing: 0.06em;">${groupName}</span>
                        <span style="font-size: 0.7rem; color: var(--text-muted); background: white; padding: 0.1rem 0.45rem; border-radius: 999px; border: 1px solid var(--border);">${groups[groupName].length}</span>
                        ${groupVideo > 0 ? `<span style="font-size: 0.7rem; color: var(--primary); background: #eef2ff; padding: 0.1rem 0.45rem; border-radius: 999px; border: 1px solid #c7d2fe;">${groupVideo} con video</span>` : ''}
                    </div>
                </td>
            </tr>
            ${groupRows}
        `;
    }).join('');

    wrapper.innerHTML = `
        <div class="list-group">
            ${header}
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
