/**
 * Vista "Agenda de Compromisos" — pantalla principal del rol Secretaría.
 *
 * Es la misma información que ve el ecosistema en la landing pública
 * (/compromisos/{token}), pero acá, logueada, Secretaría suma "Nueva actividad"
 * y la edición de los Datos Generales (tap en una tarjeta → abre el form).
 *
 * Muestra sólo las actividades con origen='secretaria' (la Agenda de
 * Compromisos). No toca nada operativo ni de Conectad@s — eso es de Comunicación.
 */
import { state } from '../state.js';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

function fmtTime(t) {
    if (!t || t === 'A definir' || t === '00:00') return null;
    return t;
}

function dayHeader(dateISO) {
    const [y, m, d] = dateISO.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    return { title: WEEKDAYS[dt.getDay()].toUpperCase(), date: `${d} de ${MONTHS[m - 1]}` };
}

function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function renderAgendaCompromisos(container) {
    const todayISO = (() => {
        const d = new Date(); d.setHours(0, 0, 0, 0);
        return d.toISOString().split('T')[0];
    })();

    const acts = state.activities
        .filter(a => !a.is_custom && a.origen === 'secretaria')
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            return (fmtTime(a.time) || '99:99').localeCompare(fmtTime(b.time) || '99:99');
        });

    const wrapper = document.createElement('div');
    wrapper.className = 'content-wrapper';

    const header = document.createElement('div');
    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;';
    header.innerHTML = `
        <div>
            <h2 style="font-weight: 700; margin: 0;">Agenda de Compromisos</h2>
            <p style="margin: 0.25rem 0 0; color: var(--text-muted); font-size: 0.85rem;">Actividades institucionales de la BCR.</p>
        </div>
        <button id="btn-nuevo-compromiso" class="btn-primary" style="width: auto; padding: 0.6rem 1.1rem;">
            <i data-lucide="plus"></i> Nueva actividad
        </button>
    `;
    wrapper.appendChild(header);

    if (acts.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'text-align: center; padding: 4rem; color: var(--text-muted);';
        empty.textContent = 'No hay actividades en la Agenda de Compromisos. Creá una con el botón de arriba.';
        wrapper.appendChild(empty);
    } else {
        // Agrupar por fecha (en orden ya ordenado)
        const groups = new Map();
        for (const act of acts) {
            if (!groups.has(act.date)) groups.set(act.date, []);
            groups.get(act.date).push(act);
        }

        for (const [date, items] of groups) {
            const h = dayHeader(date);
            const isPast = date < todayISO;

            const group = document.createElement('section');
            group.style.cssText = 'margin-bottom: 1.75rem;';
            group.style.opacity = isPast ? '0.6' : '1';

            const gh = document.createElement('div');
            gh.style.cssText = 'display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.75rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem;';
            gh.innerHTML = `
                <span style="font-weight: 700; font-size: 0.9rem; letter-spacing: 0.03em;">${h.title}</span>
                <span style="color: var(--text-muted); font-size: 0.85rem;">${h.date}</span>
            `;
            group.appendChild(gh);

            for (const act of items) {
                const time = fmtTime(act.time);
                const meta = [];
                if (act.location) meta.push(`<span><strong>Lugar:</strong> ${esc(act.location)}</span>`);
                if (act.participants) meta.push(`<span><strong>Autoridades:</strong> ${esc(act.participants)}</span>`);

                const card = document.createElement('div');
                card.className = 'compromiso-card';
                card.style.cssText = 'display: flex; gap: 1rem; padding: 0.9rem 1rem; border: 1px solid var(--border); border-radius: 0.6rem; background: white; cursor: pointer; margin-bottom: 0.6rem; transition: border-color 0.15s, box-shadow 0.15s;';
                card.innerHTML = `
                    <div style="flex-shrink: 0; width: 56px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--primary);">
                        ${time ? esc(time) : '<span style="font-size: 0.72rem; font-weight: 500; color: var(--text-muted); font-style: italic;">A definir</span>'}
                    </div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 600; margin-bottom: 0.2rem;">${esc(act.title) || '(Sin título)'}</div>
                        ${meta.length ? `<div style="display: flex; flex-wrap: wrap; gap: 0.15rem 1rem; font-size: 0.82rem; color: var(--text-muted); margin-bottom: ${act.description ? '0.3rem' : '0'};">${meta.join('')}</div>` : ''}
                        ${act.description ? `<div style="font-size: 0.85rem; color: var(--text-muted);">${esc(act.description)}</div>` : ''}
                    </div>
                    <div style="flex-shrink: 0; align-self: center; color: var(--text-muted);">
                        <i data-lucide="pencil" style="width: 16px; height: 16px;"></i>
                    </div>
                `;
                card.onmouseover = () => { card.style.borderColor = 'var(--primary)'; card.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)'; };
                card.onmouseout = () => { card.style.borderColor = 'var(--border)'; card.style.boxShadow = 'none'; };
                card.onclick = () => window.openActivityDetail(act.id);
                group.appendChild(card);
            }

            wrapper.appendChild(group);
        }
    }

    container.appendChild(wrapper);

    wrapper.querySelector('#btn-nuevo-compromiso').onclick = () => window.openNewActivity();

    if (window.lucide) window.lucide.createIcons();
}
