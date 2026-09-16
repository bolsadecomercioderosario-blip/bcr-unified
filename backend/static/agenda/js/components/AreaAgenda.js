/**
 * Vista del rol "área" (Funcionarios): DIyEE, Innova, CAC, BCR Digital…
 *
 * Dos solapas:
 *   - "Mi agenda": las actividades propias del área (origen='area', area=slug).
 *     Se cargan/editan acá y se pueden sugerir a la Agenda de la Mesa.
 *   - "Agenda completa": Mesa Ejecutiva + todas las áreas (lectura). Sirve para
 *     ver qué hacen las otras áreas y no pisarse.
 *
 * Reutiliza los estilos .cmp-* de la Agenda de Compromisos.
 */
import { state } from '../state.js';
import { getAreaSlug } from '../role.js';
import { AREA_NOMBRE, ownerLabel } from '../constants.js';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

// Estado de sugerencia a la Mesa → color e etiqueta.
const ME_COLOR = { '': '#cbd5e1', pendiente: '#f59e0b', aprobada: '#16a34a', rechazada: '#ef4444' };
const ME_LABEL = { pendiente: 'Sugerida a la Mesa', aprobada: 'En la Agenda de la Mesa', rechazada: 'No sumada a la Mesa' };

const FILTERS = [
    { key: 'proximas', label: 'Próximas' },
    { key: 'hoy', label: 'Hoy' },
    { key: 'semana', label: 'Esta semana' },
    { key: 'sem30', label: 'Próximos 30 días' },
    { key: 'todas', label: 'Todas' },
];

// Estado de la vista (module-level, sobrevive a los re-render del polling).
let currentTab = 'mias';       // 'mias' | 'completa'
let currentFilter = 'proximas';
let searchQuery = '';
let showPast = false;

function todayISO() { const d = new Date(); d.setHours(0, 0, 0, 0); return d.toISOString().split('T')[0]; }
function plusDaysISO(n) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return d.toISOString().split('T')[0]; }
function endOfWeekISO() { const d = new Date(); d.setHours(0, 0, 0, 0); const dow = d.getDay(); d.setDate(d.getDate() + (dow === 0 ? 0 : 7 - dow)); return d.toISOString().split('T')[0]; }

function passesFilter(dateISO, filter) {
    const today = todayISO();
    if (filter === 'todas') return true;
    if (filter === 'hoy') return dateISO === today;
    if (filter === 'semana') return dateISO >= today && dateISO <= endOfWeekISO();
    if (filter === 'sem30') return dateISO >= today && dateISO <= plusDaysISO(30);
    return dateISO >= today; // 'proximas'
}

function fmtTime(t) {
    if (!t || t === 'A definir' || t === 'Sin horario' || t === '00:00') return null;
    return t;
}
function timeLabel(act) {
    const start = fmtTime(act.time);
    if (start) return (act.end_time && fmtTime(act.end_time)) ? `${start} a ${act.end_time}` : start;
    return act.time === 'Sin horario' ? 'Todo el día' : 'A definir';
}
function dayHeader(dateISO) {
    const [y, m, d] = dateISO.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    return { title: WEEKDAYS[dt.getDay()].toUpperCase(), date: `${d} de ${MONTHS[m - 1]}` };
}
function shortDate(dateISO) {
    const [y, m, d] = dateISO.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    const wd = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'][dt.getDay()];
    return `${wd} ${d}/${m}`;
}
function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function eachDay(from, to) {
    const days = [];
    const [fy, fm, fd] = from.split('-').map(Number);
    const [ty, tm, td] = to.split('-').map(Number);
    const cur = new Date(fy, fm - 1, fd); const end = new Date(ty, tm - 1, td);
    let guard = 0;
    while (cur <= end && guard < 400) {
        days.push(`${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, '0')}-${String(cur.getDate()).padStart(2, '0')}`);
        cur.setDate(cur.getDate() + 1); guard++;
    }
    return days;
}
function occurrencesOf(act) {
    if (act.end_date && act.end_date > act.date) {
        const days = eachDay(act.date, act.end_date);
        return days.map((d, i) => ({ act, occDate: d, dayIndex: i + 1, dayCount: days.length }));
    }
    return [{ act, occDate: act.date, dayIndex: 1, dayCount: 1 }];
}

function mySlug() { return getAreaSlug(); }

// Predicado por solapa.
function belongsToTab(a) {
    if (a.is_custom) return false;
    if (currentTab === 'mias') return a.origen === 'area' && a.area === mySlug();
    // completa: Mesa Ejecutiva + todas las áreas (no Comunicación).
    return a.origen === 'secretaria' || a.origen === 'area';
}

function occurrences() {
    const occ = [];
    for (const a of state.activities) {
        if (!belongsToTab(a)) continue;
        for (const o of occurrencesOf(a)) occ.push(o);
    }
    return occ;
}

function matchesText(act, q) {
    if (!q) return true;
    const hay = `${act.title || ''} ${act.description || ''} ${act.location || ''} ${act.participants || ''} ${ownerLabel(act)}`.toLowerCase();
    return hay.includes(q);
}

function isMine(act) { return act.origen === 'area' && act.area === mySlug(); }

function cardHTML(occ) {
    const act = occ.act;
    const mine = isMine(act);
    const timeHtml = fmtTime(act.time) ? esc(timeLabel(act)) : `<span class="cmp-tbd">${esc(timeLabel(act))}</span>`;
    // Área → celeste fijo (mismo color en todo el proceso); Mesa → azul institucional.
    // El estado de la sugerencia se comunica por el chip, no por el color.
    const color = act.origen === 'area' ? '#0ea5e9' : '#193363';
    const descHtml = act.description ? `<div class="cmp-desc">${esc(act.description)}</div>` : '';
    const meta = [];
    if (currentTab === 'completa') meta.push(`<span><strong>${esc(ownerLabel(act))}</strong></span>`);
    if (act.location) meta.push(`<span><strong>Lugar:</strong> ${esc(act.location)}</span>`);
    if (act.participants) meta.push(`<span><strong>${act.origen === 'area' ? 'Participa (por el área)' : 'Participa'}:</strong> ${esc(act.participants)}</span>`);
    if (act.participants_me) meta.push(`<span><strong>Participa (por Mesa Ejecutiva):</strong> ${esc(act.participants_me)}</span>`);
    const metaHtml = meta.length ? `<div class="cmp-meta">${meta.join('')}</div>` : '';
    const dayBadge = occ.dayCount > 1 ? `<span class="cmp-daybadge">Día ${occ.dayIndex} de ${occ.dayCount}</span>` : '';
    // Chip de estado de sugerencia (sólo en "Mi agenda").
    let meChip = '';
    if (currentTab === 'mias' && act.me_estado && ME_LABEL[act.me_estado]) {
        const c = ME_COLOR[act.me_estado];
        meChip = `<span class="cmp-daybadge" style="background:${c}1a;color:${c};border:1px solid ${c}55;">${ME_LABEL[act.me_estado]}</span>`;
    }
    const clickable = mine ? ' cmp-clickable' : '';
    const editHint = mine ? '<div class="cmp-edit-hint"><i data-lucide="pencil" style="width:16px;height:16px;"></i></div>' : '';
    return `
        <article class="cmp-card${clickable}" data-id="${esc(act.id)}"${mine ? '' : ' data-readonly="1"'} style="border-left: 6px solid ${color};">
            <div class="cmp-time">${timeHtml}</div>
            <div class="cmp-body">
                <h3 class="cmp-title">${esc(act.title) || '(Sin título)'}</h3>
                ${dayBadge}${meChip}
                ${descHtml}
                ${metaHtml}
            </div>
            ${editHint}
        </article>`;
}

function pastItemHTML(occ) {
    const act = occ.act;
    const dayTag = occ.dayCount > 1 ? ` · Día ${occ.dayIndex}/${occ.dayCount}` : '';
    const owner = currentTab === 'completa' ? ` · ${esc(ownerLabel(act))}` : '';
    return `<div class="cmp-past-item${isMine(act) ? ' cmp-clickable' : ''}" data-id="${esc(act.id)}">
        <span class="cmp-past-date">${esc(shortDate(occ.occDate))}</span>
        <span class="cmp-past-time">${esc(timeLabel(act))}</span>
        <span class="cmp-past-title">${esc(act.title) || '(Sin título)'}${dayTag}${owner}</span>
    </div>`;
}

function renderDayGroups(occList) {
    const groups = new Map();
    for (const o of occList) {
        if (!groups.has(o.occDate)) groups.set(o.occDate, []);
        groups.get(o.occDate).push(o);
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

function contentHTML() {
    const q = searchQuery.trim().toLowerCase();
    const today = todayISO();
    const all = occurrences().filter(o => matchesText(o.act, q));

    const future = all
        .filter(o => o.occDate >= today && passesFilter(o.occDate, currentFilter))
        .sort((a, b) => a.occDate !== b.occDate ? a.occDate.localeCompare(b.occDate)
            : (fmtTime(a.act.time) || '99:99').localeCompare(fmtTime(b.act.time) || '99:99'));

    const past = showPast
        ? all.filter(o => o.occDate < today).sort((a, b) => a.occDate !== b.occDate ? b.occDate.localeCompare(a.occDate)
            : (fmtTime(a.act.time) || '99:99').localeCompare(fmtTime(b.act.time) || '99:99'))
        : [];

    if (future.length === 0 && past.length === 0) {
        const msg = currentTab === 'mias'
            ? 'Todavía no cargaste actividades. Usá "Nueva actividad".'
            : 'No hay actividades para estos filtros.';
        return `<div class="cmp-empty">${msg}</div>`;
    }
    let html = renderDayGroups(future);
    if (past.length) {
        html += `<section class="cmp-past-section"><h2 class="cmp-past-header">Pasadas</h2>${past.map(pastItemHTML).join('')}</section>`;
    }
    return html;
}

export function renderAreaAgenda(container) {
    const areaName = AREA_NOMBRE[mySlug()] || 'Área';
    const wrapper = document.createElement('div');
    wrapper.className = 'cmp-view';
    wrapper.innerHTML = `
        <header class="cmp-topbar">
            <div class="cmp-topbar-inner">
                <div class="cmp-brand">
                    <img class="cmp-brand-logo" src="/static/agenda/logo_bcr.png" alt="BCR">
                    <div><div class="cmp-brand-title">Agenda · ${esc(areaName)}</div></div>
                </div>
                <div class="cmp-actions">
                    <button id="area-new-btn" class="cmp-new-btn"><i data-lucide="plus" style="width:16px;height:16px;"></i> Nueva actividad</button>
                </div>
            </div>
        </header>

        <nav class="cmp-filters" style="gap:.75rem;">
            <button class="cmp-filter-btn area-tab" data-tab="mias">Mi agenda</button>
            <button class="cmp-filter-btn area-tab" data-tab="completa">Agenda completa</button>
        </nav>

        <nav class="cmp-filters"></nav>

        <div class="cmp-toolbar">
            <div class="cmp-search">
                <i data-lucide="search"></i>
                <input id="area-search" type="text" placeholder="Buscar actividad..." value="${(searchQuery || '').replace(/"/g, '&quot;')}">
            </div>
            <button id="area-past-toggle" class="cmp-icon-btn" type="button" title="${showPast ? 'Ocultar pasadas' : 'Ver pasadas'}"><i data-lucide="history"></i></button>
        </div>

        <main class="cmp-content"></main>

        <footer class="cmp-footer"><small>La agenda completa es de lectura. Cargás y editás sólo lo de tu área.</small></footer>
    `;

    const content = wrapper.querySelector('.cmp-content');
    const tabBtns = wrapper.querySelectorAll('.area-tab');
    const filtersNav = wrapper.querySelectorAll('.cmp-filters')[1];
    const newBtn = wrapper.querySelector('#area-new-btn');
    const pastBtn = wrapper.querySelector('#area-past-toggle');

    filtersNav.innerHTML = FILTERS.map(f => `<button class="cmp-filter-btn" data-filter="${f.key}">${f.label}</button>`).join('');
    const filterBtns = filtersNav.querySelectorAll('.cmp-filter-btn');

    const paint = () => {
        tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === currentTab));
        filterBtns.forEach(b => b.classList.toggle('active', b.dataset.filter === currentFilter));
        if (pastBtn) pastBtn.classList.toggle('active', showPast);
        // "Nueva actividad" sólo tiene sentido en Mi agenda.
        newBtn.style.display = currentTab === 'mias' ? '' : 'none';
        content.innerHTML = contentHTML();
        if (window.lucide) window.lucide.createIcons();
    };

    tabBtns.forEach(b => b.onclick = () => { currentTab = b.dataset.tab; paint(); });
    filterBtns.forEach(b => b.onclick = () => { currentFilter = b.dataset.filter; paint(); });

    const searchInput = wrapper.querySelector('#area-search');
    searchInput.addEventListener('input', () => { searchQuery = searchInput.value; paint(); });
    pastBtn.addEventListener('click', () => {
        showPast = !showPast;
        pastBtn.title = showPast ? 'Ocultar pasadas' : 'Ver pasadas';
        paint();
    });

    content.addEventListener('click', (e) => {
        if (e.target.closest('a')) return;
        const el = e.target.closest('.cmp-card, .cmp-past-item');
        if (!el || el.dataset.readonly) return;   // sólo las propias son editables
        window.openActivityDetail(el.dataset.id);
    });

    newBtn.onclick = () => window.openNewActivity();

    container.appendChild(wrapper);
    paint();
}
