/**
 * Vista "Agenda de Compromisos" — pantalla principal del rol Secretaría.
 *
 * Reproduce EL MISMO diseño que la landing pública (/compromisos/{token}):
 * header azul (con logo BCR), pastillas de filtro y tarjetas por día. Diferencias
 * respecto de la pública:
 *   - Se puede crear ("Nueva actividad") y editar (tap en una tarjeta → form).
 *   - Cada tarjeta lleva un semáforo (barra de color a la izquierda) según el
 *     estado de avance, para ver el panorama de un vistazo.
 *   - No tiene botón al Hub.
 *
 * Muestra sólo las actividades con origen='secretaria'.
 */
import { state } from '../state.js';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

// Colores del semáforo por estado de avance.
const ESTADO_COLOR = {
    'Pendiente': '#ef4444',   // rojo
    'En Proceso': '#f59e0b',  // naranja
    'Avanzado': '#2563eb',    // azul
    'Finalizado': '#16a34a',  // verde
};

const FILTERS = [
    { key: 'proximas', label: 'Próximas' },
    { key: 'hoy', label: 'Hoy' },
    { key: 'semana', label: 'Esta semana' },
    { key: 'sem7', label: 'Próximos 7 días' },
    { key: 'sem30', label: 'Próximos 30 días' },
    { key: 'todas', label: 'Todas' },
];

// Filtro activo. Module-level para que sobreviva a los re-render del polling.
let currentFilter = 'proximas';

function todayISO() {
    const d = new Date(); d.setHours(0, 0, 0, 0);
    return d.toISOString().split('T')[0];
}
function plusDaysISO(n) {
    const d = new Date(); d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() + n);
    return d.toISOString().split('T')[0];
}
function endOfWeekISO() {
    const d = new Date(); d.setHours(0, 0, 0, 0);
    const dow = d.getDay();
    const daysToSunday = dow === 0 ? 0 : 7 - dow;
    d.setDate(d.getDate() + daysToSunday);
    return d.toISOString().split('T')[0];
}

function passesFilter(act, filter) {
    const today = todayISO();
    if (filter === 'todas') return true;
    if (filter === 'hoy') return act.date === today;
    if (filter === 'semana') return act.date >= today && act.date <= endOfWeekISO();
    if (filter === 'sem7') return act.date >= today && act.date <= plusDaysISO(7);
    if (filter === 'sem30') return act.date >= today && act.date <= plusDaysISO(30);
    return act.date >= today; // 'proximas'
}

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

function secretariaActivities() {
    return state.activities
        .filter(a => !a.is_custom && a.origen === 'secretaria')
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            return (fmtTime(a.time) || '99:99').localeCompare(fmtTime(b.time) || '99:99');
        });
}

function cardHTML(act) {
    const time = fmtTime(act.time);
    const timeHtml = time ? esc(time) : '<span class="cmp-tbd">A definir</span>';
    const color = ESTADO_COLOR[act.estado] || '#cbd5e1';

    const descHtml = act.description ? `<div class="cmp-desc">${esc(act.description)}</div>` : '';
    const meta = [];
    if (act.location) meta.push(`<span><strong>Lugar:</strong> ${esc(act.location)}</span>`);
    if (act.participants) meta.push(`<span><strong>Participa:</strong> ${esc(act.participants)}</span>`);
    const metaHtml = meta.length ? `<div class="cmp-meta">${meta.join('')}</div>` : '';

    return `
        <article class="cmp-card" data-id="${esc(act.id)}" style="border-left: 6px solid ${color};" title="Estado: ${esc(act.estado || 'Pendiente')}">
            <div class="cmp-time">${timeHtml}</div>
            <div class="cmp-body">
                <h3 class="cmp-title">${esc(act.title) || '(Sin título)'}</h3>
                ${descHtml}
                ${metaHtml}
            </div>
            <div class="cmp-edit-hint"><i data-lucide="pencil" style="width: 16px; height: 16px;"></i></div>
        </article>
    `;
}

function contentHTML(filter) {
    const acts = secretariaActivities().filter(a => passesFilter(a, filter));

    if (acts.length === 0) {
        return '<div class="cmp-empty">No hay actividades para este filtro. Creá una con “Nueva actividad”.</div>';
    }

    const groups = new Map();
    for (const act of acts) {
        if (!groups.has(act.date)) groups.set(act.date, []);
        groups.get(act.date).push(act);
    }

    let html = '';
    for (const [date, items] of groups) {
        const h = dayHeader(date);
        html += `<section class="cmp-day-group">
            <h2 class="cmp-day-header">${h.title}<span class="cmp-day-date">${h.date}</span></h2>
            ${items.map(cardHTML).join('')}
        </section>`;
    }
    return html;
}

export function renderAgendaCompromisos(container) {
    const wrapper = document.createElement('div');
    wrapper.className = 'cmp-view';
    wrapper.innerHTML = `
        <header class="cmp-topbar">
            <div class="cmp-topbar-inner">
                <div class="cmp-brand">
                    <img class="cmp-brand-logo" src="/static/agenda/logo_bcr.png" alt="BCR">
                    <div>
                        <div class="cmp-brand-title">Agenda de Compromisos</div>
                    </div>
                </div>
                <div class="cmp-actions">
                    <button id="cmp-print-btn" class="cmp-ghost-btn"><i data-lucide="printer" style="width: 16px; height: 16px;"></i> Imprimir</button>
                    <button id="cmp-new-btn" class="cmp-new-btn"><i data-lucide="plus" style="width: 16px; height: 16px;"></i> Nueva actividad</button>
                </div>
            </div>
        </header>

        <nav class="cmp-filters">
            ${FILTERS.map(f => `<button class="cmp-filter-btn" data-filter="${f.key}">${f.label}</button>`).join('')}
        </nav>

        <main class="cmp-content"></main>

        <footer class="cmp-footer">
            <small>Actualizado automáticamente. La información es de uso interno.</small>
        </footer>
    `;

    const content = wrapper.querySelector('.cmp-content');
    const filterBtns = wrapper.querySelectorAll('.cmp-filter-btn');

    const paint = () => {
        filterBtns.forEach(b => b.classList.toggle('active', b.dataset.filter === currentFilter));
        content.innerHTML = contentHTML(currentFilter);
        if (window.lucide) window.lucide.createIcons();
    };

    filterBtns.forEach(btn => {
        btn.onclick = () => { currentFilter = btn.dataset.filter; paint(); };
    });

    content.addEventListener('click', (e) => {
        const card = e.target.closest('.cmp-card');
        if (card) window.openActivityDetail(card.dataset.id);
    });

    wrapper.querySelector('#cmp-new-btn').onclick = () => window.openNewActivity();
    wrapper.querySelector('#cmp-print-btn').onclick = () => openPrintModal();

    container.appendChild(wrapper);
    paint();
}

// =================================================================
// Impresión a PDF (vía el diálogo del navegador) por rango de fechas.
// =================================================================
function openPrintModal() {
    const overlay = document.createElement('div');
    overlay.className = 'login-overlay';
    overlay.style.zIndex = '1000';
    overlay.innerHTML = `
        <div class="login-card" style="max-width: 380px; width: 90%; text-align: left;">
            <h3 style="margin: 0 0 0.35rem;">Imprimir agenda</h3>
            <p style="margin: 0 0 1rem; color: var(--text-muted); font-size: 0.85rem;">Elegí el rango de fechas a incluir en el PDF.</p>
            <label style="display: block; font-size: 0.8rem; font-weight: 600; margin-bottom: 0.25rem;">Desde</label>
            <input id="print-from" type="date" value="${todayISO()}" style="width: 100%; padding: 0.5rem 0.6rem; border: 1px solid var(--border); border-radius: 0.4rem; margin-bottom: 0.75rem;">
            <label style="display: block; font-size: 0.8rem; font-weight: 600; margin-bottom: 0.25rem;">Hasta</label>
            <input id="print-to" type="date" value="${plusDaysISO(30)}" style="width: 100%; padding: 0.5rem 0.6rem; border: 1px solid var(--border); border-radius: 0.4rem; margin-bottom: 0.5rem;">
            <div id="print-err" style="display: none; color: #b91c1c; font-size: 0.78rem; margin-bottom: 0.5rem;"></div>
            <div style="display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.75rem;">
                <button id="print-cancel" style="background: white; border: 1px solid var(--border); padding: 0.5rem 1rem; border-radius: 0.4rem; font-weight: 600; cursor: pointer;">Cancelar</button>
                <button id="print-go" class="btn-primary" style="width: auto; padding: 0.5rem 1.1rem;">Imprimir</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#print-cancel').onclick = close;
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });

    overlay.querySelector('#print-go').onclick = () => {
        const from = overlay.querySelector('#print-from').value;
        const to = overlay.querySelector('#print-to').value;
        const err = overlay.querySelector('#print-err');
        if (!from || !to) { err.textContent = 'Completá las dos fechas.'; err.style.display = 'block'; return; }
        if (to < from) { err.textContent = 'La fecha "Hasta" debe ser posterior a "Desde".'; err.style.display = 'block'; return; }
        close();
        printRange(from, to);
    };
}

function printRange(from, to) {
    const acts = secretariaActivities().filter(a => a.date >= from && a.date <= to);

    const groups = new Map();
    for (const act of acts) {
        if (!groups.has(act.date)) groups.set(act.date, []);
        groups.get(act.date).push(act);
    }

    let body = '';
    if (acts.length === 0) {
        body = '<p>No hay actividades en el rango elegido.</p>';
    } else {
        for (const [date, items] of groups) {
            const h = dayHeader(date);
            body += `<div class="cmp-pa-day"><h2>${h.title} · ${h.date}</h2>`;
            for (const act of items) {
                const t = fmtTime(act.time);
                const meta = [];
                if (act.location) meta.push(`<strong>Lugar:</strong> ${esc(act.location)}`);
                if (act.participants) meta.push(`<strong>Participa:</strong> ${esc(act.participants)}`);
                body += `<div class="cmp-pa-act">
                    <div class="cmp-pa-time">${t ? esc(t) : 'A definir'}</div>
                    <div>
                        <div class="cmp-pa-title">${esc(act.title) || '(Sin título)'}</div>
                        ${act.description ? `<div class="cmp-pa-desc">${esc(act.description)}</div>` : ''}
                        ${meta.length ? `<div class="cmp-pa-meta">${meta.join('<br>')}</div>` : ''}
                    </div>
                </div>`;
            }
            body += `</div>`;
        }
    }

    const fmtRange = (iso) => {
        const [y, m, d] = iso.split('-').map(Number);
        return `${d}/${m}/${y}`;
    };

    const area = document.createElement('div');
    area.id = 'cmp-print-area';
    area.innerHTML = `
        <div class="cmp-pa-head">
            <img class="cmp-pa-logo" src="/static/agenda/logo_bcr_azul.png" alt="Bolsa de Comercio de Rosario">
            <h1>Agenda de Compromisos</h1>
            <p>Período: ${fmtRange(from)} al ${fmtRange(to)}</p>
        </div>
        ${body}
    `;
    document.body.appendChild(area);

    // El título del documento aparece en el encabezado del PDF y como nombre de
    // archivo por defecto. La app se llama "Agenda de Comunicación", así que lo
    // pisamos con "Agenda de Compromisos" mientras dura la impresión.
    const prevTitle = document.title;
    document.title = 'Agenda de Compromisos';

    const cleanup = () => {
        area.remove();
        document.title = prevTitle;
        window.removeEventListener('afterprint', cleanup);
    };
    window.addEventListener('afterprint', cleanup);

    // Esperamos a que el logo cargue antes de imprimir (si no, sale en blanco).
    let printed = false;
    const go = () => {
        if (printed) return;
        printed = true;
        window.print();
        // Fallback por si afterprint no dispara (algunos browsers).
        setTimeout(() => { if (document.getElementById('cmp-print-area')) cleanup(); }, 1000);
    };
    const logo = area.querySelector('.cmp-pa-logo');
    if (logo && !logo.complete) {
        logo.addEventListener('load', go, { once: true });
        logo.addEventListener('error', go, { once: true });
        setTimeout(go, 1500);
    } else {
        go();
    }
}
