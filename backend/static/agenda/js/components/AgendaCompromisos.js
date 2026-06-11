/**
 * Vista "Agenda de Compromisos" — pantalla principal del rol Secretaría.
 *
 * Reproduce EL MISMO diseño que la landing pública (/compromisos/{token}):
 * header azul, pastillas de filtro y tarjetas por día. La única diferencia es
 * que acá, logueada, Secretaría puede crear ("Nueva actividad") y editar (tap en
 * una tarjeta → abre el form). La landing pública sólo mira.
 *
 * Para que el header azul quede a todo el ancho (como en la landing), el CSS
 * oculta la top-bar de la app y saca el padding del view-container cuando
 * body[data-role="secretaria"] (ver style.css).
 *
 * Muestra sólo las actividades con origen='secretaria'.
 */
import { state } from '../state.js';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

// Filtro activo. Module-level para que sobreviva a los re-render del polling.
let currentFilter = 'proximas';

function todayISO() {
    const d = new Date(); d.setHours(0, 0, 0, 0);
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

function cardHTML(act) {
    const time = fmtTime(act.time);
    const timeHtml = time
        ? esc(time)
        : '<span class="cmp-tbd">A definir</span>';

    const meta = [];
    if (act.location) meta.push(`<span><strong>Lugar:</strong> ${esc(act.location)}</span>`);
    if (act.participants) meta.push(`<span><strong>Autoridades:</strong> ${esc(act.participants)}</span>`);
    const metaHtml = meta.length ? `<div class="cmp-meta">${meta.join('')}</div>` : '';
    const descHtml = act.description ? `<div class="cmp-desc">${esc(act.description)}</div>` : '';

    return `
        <article class="cmp-card" data-id="${esc(act.id)}">
            <div class="cmp-time">${timeHtml}</div>
            <div class="cmp-body">
                <h3 class="cmp-title">${esc(act.title) || '(Sin título)'}</h3>
                ${metaHtml}
                ${descHtml}
            </div>
            <div class="cmp-edit-hint"><i data-lucide="pencil" style="width: 16px; height: 16px;"></i></div>
        </article>
    `;
}

function contentHTML(filter) {
    const acts = state.activities
        .filter(a => !a.is_custom && a.origen === 'secretaria')
        .filter(a => passesFilter(a, filter))
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            return (fmtTime(a.time) || '99:99').localeCompare(fmtTime(b.time) || '99:99');
        });

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
                    <div class="cmp-brand-mark">BCR</div>
                    <div>
                        <div class="cmp-brand-title">Agenda de Compromisos</div>
                        <div class="cmp-brand-sub">Bolsa de Comercio de Rosario</div>
                    </div>
                </div>
                <div class="cmp-actions">
                    <a href="/" class="cmp-hub" title="Volver al Hub"><i data-lucide="arrow-left" style="width: 14px; height: 14px;"></i> Hub</a>
                    <button id="cmp-new-btn" class="cmp-new-btn"><i data-lucide="plus" style="width: 16px; height: 16px;"></i> Nueva actividad</button>
                </div>
            </div>
        </header>

        <nav class="cmp-filters">
            <button class="cmp-filter-btn" data-filter="proximas">Próximas</button>
            <button class="cmp-filter-btn" data-filter="hoy">Hoy</button>
            <button class="cmp-filter-btn" data-filter="semana">Esta semana</button>
            <button class="cmp-filter-btn" data-filter="todas">Todas</button>
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

    // Tap en una tarjeta → editar (delegación, así sobrevive a re-pintar el contenido).
    content.addEventListener('click', (e) => {
        const card = e.target.closest('.cmp-card');
        if (card) window.openActivityDetail(card.dataset.id);
    });

    wrapper.querySelector('#cmp-new-btn').onclick = () => window.openNewActivity();

    container.appendChild(wrapper);
    paint();
}
