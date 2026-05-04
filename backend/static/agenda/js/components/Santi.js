import { state } from '../state.js';

export function renderSanti(container) {
    const avActivities = state.activities
        .filter(a => {
            if (a.is_custom) return false;
            const isStoryVideo = a.channels.includes('Instagram Story') && a.story_type !== 'Layout';
            const isYoutube = a.channels.includes('YouTube');
            return isStoryVideo || isYoutube;
        })
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            return a.time.localeCompare(b.time);
        });

    const wrapper = document.createElement('div');
    wrapper.className = 'content-wrapper';

    const formatFullDate = (dateStr) => {
        const days = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
        const [year, month, day] = dateStr.split('-');
        const date = new Date(year, month - 1, day);
        return `${days[date.getDay()]} ${parseInt(day)}/${parseInt(month)}`;
    };

    if (avActivities.length === 0) {
        wrapper.innerHTML = '<div style="text-align: center; padding: 4rem; color: var(--text-muted);">No hay tareas audiovisuales (IG Stories) pendientes.</div>';
        container.appendChild(wrapper);
        return;
    }

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
                        <th style="width: 250px;">Links Drive</th>
                    </tr>
                </thead>
                <tbody>
                    ${avActivities.map(act => `
                        <tr onclick="window.openActivityDetail('${act.id}')">
                            <td style="font-size: 0.8rem; color: var(--text-muted); font-weight: 500;">
                                ${formatFullDate(act.date)}
                            </td>
                            <td style="font-weight: 500;">${act.time}</td>
                            <td>
                                <div style="font-weight: 600;">${act.title}</div>
                                <div style="font-size: 0.8rem; color: var(--text-muted);">${act.description.substring(0, 50)}...</div>
                            </td>
                            <td>
                                <span class="badge" style="background: ${act.story_type === 'Video' ? '#dcfce7' : '#fef9c3'}; color: ${act.story_type === 'Video' ? '#166534' : '#854d0e'}; font-size: 0.7rem; padding: 0.2rem 0.5rem; border-radius: 999px; font-weight: 600;">
                                    ${act.story_type || 'Video'}
                                </span>
                            </td>
                            <td>
                                <div style="display: flex; flex-direction: column; gap: 0.25rem;">
                                    ${act.drive_bcr ? `<a href="${act.drive_bcr}" target="_blank" onclick="event.stopPropagation()" style="font-size: 0.75rem; color: var(--primary); text-decoration: none;">📁 Drive BCR</a>` : ''}
                                    ${act.drive_santiago ? `<a href="${act.drive_santiago}" target="_blank" onclick="event.stopPropagation()" style="font-size: 0.75rem; color: #7c3aed; text-decoration: none;">📽️ Drive Santi</a>` : ''}
                                    ${!act.drive_bcr && !act.drive_santiago ? '<span style="color: var(--text-muted); font-size: 0.75rem;">Sin links aún</span>' : ''}
                                </div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;

    container.appendChild(wrapper);
}
