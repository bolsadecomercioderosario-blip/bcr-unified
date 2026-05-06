import { state, updateActivity, deleteActivity, expandPastMonths } from '../state.js';

export function renderList(container) {
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

    const endOfNextWeek = new Date(endOfThisWeek);
    endOfNextWeek.setDate(endOfThisWeek.getDate() + 7);
    const endOfNextWeekISO = endOfNextWeek.toISOString().split('T')[0];

    // Cutoff para pasadas: hoy menos N meses (donde N = state.pastMonthsVisible)
    const cutoffPast = new Date(today);
    cutoffPast.setMonth(today.getMonth() - state.pastMonthsVisible);
    const cutoffPastISO = cutoffPast.toISOString().split('T')[0];

    const filteredActivities = state.activities.filter(a => {
        if (a.is_custom) return false;
        const query = state.searchQuery.toLowerCase();
        return a.title.toLowerCase().includes(query) || 
               a.description.toLowerCase().includes(query) ||
               (a.responsible && a.responsible.toLowerCase().includes(query));
    });

    const sortedActivities = filteredActivities.sort((a, b) => {
        if (a.date !== b.date) return a.date.localeCompare(b.date);
        return a.time.localeCompare(b.time);
    });

    const groups = {
        'PASADAS': [],
        'HOY': [],
        'MAÑANA': [],
        'ESTA SEMANA': [],
        'PRÓXIMA SEMANA': [],
        'MÁS ADELANTE': []
    };

    // Contador de pasadas más viejas que el cutoff (para decidir si mostrar el botón "ver más")
    let olderThanCutoffCount = 0;

    sortedActivities.forEach(act => {
        if (act.date < todayISO) {
            if (act.date >= cutoffPastISO) {
                groups['PASADAS'].push(act);
            } else {
                olderThanCutoffCount += 1;
            }
        } else if (act.date === todayISO) {
            groups['HOY'].push(act);
        } else if (act.date === tomorrowISO) {
            groups['MAÑANA'].push(act);
        } else if (act.date <= endOfThisWeekISO) {
            groups['ESTA SEMANA'].push(act);
        } else if (act.date <= endOfNextWeekISO) {
            groups['PRÓXIMA SEMANA'].push(act);
        } else {
            groups['MÁS ADELANTE'].push(act);
        }
    });

    // Pasadas: ordenar de más reciente a más antigua (los demás grupos siguen ascendente)
    groups['PASADAS'].reverse();

    const wrapper = document.createElement('div');
    wrapper.className = 'content-wrapper';

    const formatFullDate = (dateStr) => {
        const days = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
        const [year, month, day] = dateStr.split('-');
        const date = new Date(year, month - 1, day);
        const dayName = days[date.getDay()];
        return `${dayName} ${parseInt(day)}/${parseInt(month)}`;
    };

    const renderChannelNames = (channels) => {
        if (!channels || channels.length === 0) return '-';
        return `
            <div class="channel-badges-flex" style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
                ${channels.map(ch => `
                    <span style="background: #f1f5f9; color: var(--text-muted); font-size: 0.7rem; padding: 0.15rem 0.45rem; border-radius: 0.25rem; font-weight: 600; border: 1px solid var(--border); white-space: nowrap;">
                        ${ch}
                    </span>
                `).join('')}
            </div>
        `;
    };

    // Helpers de efemérides
    const efemeridesForDate = (date) => {
        const m = date.getMonth() + 1;
        const d = date.getDate();
        return state.efemerides.filter(e => e.mes === m && e.dia === d);
    };

    const efemeridesForRange = (startDate, endDate) => {
        const result = [];
        const cur = new Date(startDate);
        while (cur <= endDate) {
            result.push(...efemeridesForDate(cur).map(e => ({ ...e, _date: new Date(cur) })));
            cur.setDate(cur.getDate() + 1);
        }
        return result;
    };

    const renderEfBanner = (efs, includeDate = false) => {
        if (efs.length === 0) return '';
        let inner;
        if (includeDate) {
            const grouped = {};
            efs.forEach(e => {
                const d = e._date;
                const key = `${d.getDate()}/${d.getMonth() + 1}`;
                if (!grouped[key]) grouped[key] = [];
                grouped[key].push(`${e.tipo}: ${e.motivo}`);
            });
            inner = Object.keys(grouped)
                .map(k => `<strong>${k}</strong> · ${grouped[k].join(' · ')}`)
                .join(' &nbsp;|&nbsp; ');
        } else {
            inner = efs.map(e => `${e.tipo}: ${e.motivo}`).join(' · ');
        }
        return `<div class="efemerides-banner">${inner}</div>`;
    };

    const renderGroup = (title, items, showHeader, footerHtml = '', efBannerHtml = '') => {
        if (items.length === 0) return '';
        if (title === 'PASADAS' && !state.showPast) return '';

        const colgroup = `
            <colgroup>
                <col style="width: 120px;">
                <col style="width: 75px;">
                <col>
                <col style="width: 130px;">
                <col style="width: 200px;">
                <col style="width: 90px;">
            </colgroup>
        `;

        const thead = `
            <thead>
                <tr>
                    <th>Fecha</th>
                    <th>Hora</th>
                    <th>Actividad</th>
                    <th>Responsable</th>
                    <th>Canales</th>
                    <th style="text-align: center;">Acciones</th>
                </tr>
            </thead>
        `;

        return `
            <div class="list-group">
                <div class="group-header">
                    <span class="group-title">${title}</span>
                    <div class="group-line"></div>
                </div>
                ${efBannerHtml}
                <table class="data-table">
                    ${colgroup}
                    ${showHeader ? thead : ''}
                    <tbody>
                        ${items.map(act => `
                            <tr class="${act.done ? 'tr-done' : ''}" onclick="window.openActivityDetail('${act.id}')">
                                <td style="font-size: 0.8rem; color: var(--text-muted); font-weight: 500;">
                                    ${formatFullDate(act.date)}
                                </td>
                                <td style="font-weight: 500; font-variant-numeric: tabular-nums;">${act.time}</td>
                                <td>
                                    <div style="font-weight: 600;">${act.title}</div>
                                    <div style="font-size: 0.8rem; color: var(--text-muted);">${act.description.substring(0, 80)}${act.description.length > 80 ? '...' : ''}</div>
                                </td>
                                <td class="td-responsible"><span class="badge-user">${act.responsible || '-'}</span></td>
                                <td>${renderChannelNames(act.channels)}</td>
                                <td style="text-align: center; white-space: nowrap;" onclick="event.stopPropagation()">
                                    <div style="display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;">
                                        <button class="btn-check-done ${act.done ? 'is-done' : ''}" data-id="${act.id}" title="Marcar como realizado">
                                            <i data-lucide="check-circle-2"></i>
                                        </button>
                                        <button class="btn-delete-activity" data-id="${act.id}" title="Eliminar actividad" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 0.2rem; display: inline-flex; align-items: center;">
                                            <i data-lucide="trash-2" style="width: 18px; height: 18px;"></i>
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ${footerHtml}
            </div>
        `;
    };

    let html = '';
    let headerShown = false;
    const groupOrder = ['HOY', 'MAÑANA', 'ESTA SEMANA', 'PRÓXIMA SEMANA', 'MÁS ADELANTE', 'PASADAS'];

    groupOrder.forEach(g => {
        let footerHtml = '';
        if (g === 'PASADAS' && olderThanCutoffCount > 0) {
            footerHtml = `
                <div style="text-align: center; margin-top: 1rem;">
                    <button class="btn-show-more-past" style="background: white; border: 1px solid var(--border); color: var(--text-muted); padding: 0.5rem 1rem; border-radius: 0.5rem; cursor: pointer; font-size: 0.85rem; font-weight: 500;">
                        Ver mes anterior (${olderThanCutoffCount} más)
                    </button>
                </div>
            `;
        }

        // Banner de efemérides solo para HOY / MAÑANA / ESTA SEMANA
        let efBannerHtml = '';
        if (g === 'HOY') {
            efBannerHtml = renderEfBanner(efemeridesForDate(today), false);
        } else if (g === 'MAÑANA') {
            efBannerHtml = renderEfBanner(efemeridesForDate(tomorrow), false);
        } else if (g === 'ESTA SEMANA') {
            const start = new Date(tomorrow);
            start.setDate(start.getDate() + 1);
            efBannerHtml = renderEfBanner(efemeridesForRange(start, endOfThisWeek), true);
        }

        const groupHtml = renderGroup(g, groups[g], !headerShown, footerHtml, efBannerHtml);
        if (groupHtml) {
            html += groupHtml;
            headerShown = true;
        }
    });

    if (html === '') {
        html = '<div style="text-align: center; padding: 4rem; color: var(--text-muted);">No hay actividades pendientes.</div>';
    }

    wrapper.innerHTML = html;
    
    // Add check button listeners
    wrapper.querySelectorAll('.btn-check-done').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            const isDone = btn.classList.contains('is-done');
            updateActivity(id, { done: !isDone });
        };
    });
    
    // Add delete button listeners
    wrapper.querySelectorAll('.btn-delete-activity').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            if (confirm('¿Estás seguro de que querés eliminar esta actividad?')) {
                const id = btn.dataset.id;
                deleteActivity(id);
            }
        };
    });

    // "Ver mes anterior" button listener (solo si está renderizado)
    const btnMorePast = wrapper.querySelector('.btn-show-more-past');
    if (btnMorePast) {
        btnMorePast.onclick = () => expandPastMonths();
    }

    container.appendChild(wrapper);
}
