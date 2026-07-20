/**
 * Vista "Agenda de Compromisos" — pantalla principal del rol Secretaría.
 *
 * Mismo diseño que la landing pública (header azul, pastillas, tarjetas por día),
 * pero acá se crea y edita, y cada tarjeta lleva un semáforo por estado.
 *
 * Actividades de varios días: si una actividad tiene end_date > date, se expande
 * y aparece en CADA día del rango, con un distintivo "Día X de N".
 *
 * Muestra sólo las actividades con origen='secretaria'.
 */
import { state } from '../state.js';
import { SEC_RESPONSABLES } from '../constants.js';

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

// Filtros activos. Module-level para que sobrevivan a los re-render del polling.
let currentFilter = 'proximas';
let searchQuery = '';        // buscador por texto
let responsableFilter = '';  // '' = todos; si no, un sec_responsible puntual
let showPast = false;        // incluir actividades pasadas (icono)

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

function passesFilter(dateISO, filter) {
    const today = todayISO();
    if (filter === 'todas') return true;
    if (filter === 'hoy') return dateISO === today;
    if (filter === 'semana') return dateISO >= today && dateISO <= endOfWeekISO();
    if (filter === 'sem7') return dateISO >= today && dateISO <= plusDaysISO(7);
    if (filter === 'sem30') return dateISO >= today && dateISO <= plusDaysISO(30);
    return dateISO >= today; // 'proximas'
}

function fmtTime(t) {
    if (!t || t === 'A definir' || t === 'Sin horario' || t === '00:00') return null;
    return t;
}
// Texto a mostrar en el slot de hora: hora, rango "HH:MM a HH:MM",
// "Todo el día" (sin horario) o "A definir".
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

function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Ícono de descarga (inline, no depende de lucide).
const DOWNLOAD_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';

function attachmentHTML(act) {
    if (!act.attachment_url) return '';
    return `<div class="cmp-attach"><a href="${esc(act.attachment_url)}" target="_blank" rel="noopener" download>${DOWNLOAD_ICON} Ver Información Adicional</a></div>`;
}

// --- Multi-día: enumera los días de un rango inclusive (con tope de seguridad) ---
function eachDay(from, to) {
    const days = [];
    const [fy, fm, fd] = from.split('-').map(Number);
    const [ty, tm, td] = to.split('-').map(Number);
    const cur = new Date(fy, fm - 1, fd);
    const end = new Date(ty, tm - 1, td);
    let guard = 0;
    while (cur <= end && guard < 400) {
        days.push(`${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, '0')}-${String(cur.getDate()).padStart(2, '0')}`);
        cur.setDate(cur.getDate() + 1);
        guard++;
    }
    return days;
}
// Convierte una actividad en 1 (o N) "ocurrencias", una por cada día que dura.
function occurrencesOf(act) {
    if (act.end_date && act.end_date > act.date) {
        const days = eachDay(act.date, act.end_date);
        return days.map((d, i) => ({ act, occDate: d, dayIndex: i + 1, dayCount: days.length }));
    }
    return [{ act, occDate: act.date, dayIndex: 1, dayCount: 1 }];
}
function secretariaOccurrences() {
    const occ = [];
    for (const a of state.activities) {
        if (a.is_custom || a.origen !== 'secretaria') continue;
        for (const o of occurrencesOf(a)) occ.push(o);
    }
    return occ;
}

function cardHTML(occ) {
    const act = occ.act;
    const isClock = !!fmtTime(act.time);
    const timeHtml = isClock ? esc(timeLabel(act)) : `<span class="cmp-tbd">${esc(timeLabel(act))}</span>`;
    const color = ESTADO_COLOR[act.estado] || '#cbd5e1';

    const descHtml = act.description ? `<div class="cmp-desc">${esc(act.description)}</div>` : '';
    const meta = [];
    if (act.location) meta.push(`<span><strong>Lugar:</strong> ${esc(act.location)}</span>`);
    if (act.participants) meta.push(`<span><strong>Participa:</strong> ${esc(act.participants)}</span>`);
    const metaHtml = meta.length ? `<div class="cmp-meta">${meta.join('')}</div>` : '';
    const dayBadge = occ.dayCount > 1 ? `<span class="cmp-daybadge">Día ${occ.dayIndex} de ${occ.dayCount}</span>` : '';

    return `
        <article class="cmp-card" data-id="${esc(act.id)}" style="border-left: 6px solid ${color};" title="Estado: ${esc(act.estado || 'Pendiente')}">
            <div class="cmp-time">${timeHtml}</div>
            <div class="cmp-body">
                <h3 class="cmp-title">${esc(act.title) || '(Sin título)'}</h3>
                ${dayBadge}
                ${descHtml}
                ${metaHtml}
                ${attachmentHTML(act)}
            </div>
            <div class="cmp-edit-hint"><i data-lucide="pencil" style="width: 16px; height: 16px;"></i></div>
        </article>
    `;
}

function matchesText(act, q) {
    if (!q) return true;
    const hay = `${act.title || ''} ${act.description || ''} ${act.location || ''} ${act.participants || ''}`.toLowerCase();
    return hay.includes(q);
}

// Fecha compacta para la lista de pasadas: "mar 24/6".
function shortDate(dateISO) {
    const [y, m, d] = dateISO.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    const wd = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'][dt.getDay()];
    return `${wd} ${d}/${m}`;
}

// Futuras/actuales: agrupadas por día, tarjeta completa (ASC).
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

// Pasadas: fila compacta y con menos peso visual (clickeable para ver detalle).
function pastItemHTML(occ) {
    const act = occ.act;
    const dayTag = occ.dayCount > 1 ? ` · Día ${occ.dayIndex}/${occ.dayCount}` : '';
    return `<div class="cmp-past-item" data-id="${esc(act.id)}">
        <span class="cmp-past-date">${esc(shortDate(occ.occDate))}</span>
        <span class="cmp-past-time">${esc(timeLabel(act))}</span>
        <span class="cmp-past-title">${esc(act.title) || '(Sin título)'}${dayTag}</span>
    </div>`;
}

function contentHTML(filter) {
    const q = searchQuery.trim().toLowerCase();
    const today = todayISO();
    const all = secretariaOccurrences()
        .filter(o => matchesText(o.act, q))
        .filter(o => !responsableFilter || o.act.sec_responsible === responsableFilter);

    // Futuras/actuales: de hoy en adelante, según la pastilla. ASC.
    const future = all
        .filter(o => o.occDate >= today && passesFilter(o.occDate, filter))
        .sort((a, b) => {
            if (a.occDate !== b.occDate) return a.occDate.localeCompare(b.occDate);
            return (fmtTime(a.act.time) || '99:99').localeCompare(fmtTime(b.act.time) || '99:99');
        });

    // Pasadas: sólo con el toggle activo, más recientes primero (DESC).
    const past = showPast
        ? all.filter(o => o.occDate < today).sort((a, b) => {
            if (a.occDate !== b.occDate) return b.occDate.localeCompare(a.occDate);
            return (fmtTime(a.act.time) || '99:99').localeCompare(fmtTime(b.act.time) || '99:99');
        })
        : [];

    if (future.length === 0 && past.length === 0) {
        return '<div class="cmp-empty">No hay actividades para estos filtros.</div>';
    }

    let html = renderDayGroups(future);
    if (past.length) {
        html += `<section class="cmp-past-section">
            <h2 class="cmp-past-header">Pasadas</h2>
            ${past.map(pastItemHTML).join('')}
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

        <div class="cmp-toolbar">
            <div class="cmp-search">
                <i data-lucide="search"></i>
                <input id="cmp-search" type="text" placeholder="Buscar actividad..." value="${(searchQuery || '').replace(/"/g, '&quot;')}">
            </div>
            <select id="cmp-resp-filter" class="cmp-resp-filter" title="Filtrar por responsable">
                <option value="">Todos los responsables</option>
                ${SEC_RESPONSABLES.map(r => `<option value="${r}" ${responsableFilter === r ? 'selected' : ''}>${r}</option>`).join('')}
            </select>
            <button id="cmp-past-toggle" class="cmp-icon-btn" type="button" title="${showPast ? 'Ocultar pasadas' : 'Ver pasadas'}">
                <i data-lucide="history"></i>
            </button>
        </div>

        <main class="cmp-content"></main>

        <footer class="cmp-footer">
            <small>Actualizado automáticamente. La información es de uso interno.</small>
        </footer>
    `;

    const content = wrapper.querySelector('.cmp-content');
    const filterBtns = wrapper.querySelectorAll('.cmp-filter-btn');

    const pastBtn = wrapper.querySelector('#cmp-past-toggle');

    const paint = () => {
        filterBtns.forEach(b => b.classList.toggle('active', b.dataset.filter === currentFilter));
        if (pastBtn) pastBtn.classList.toggle('active', showPast);
        content.innerHTML = contentHTML(currentFilter);
        if (window.lucide) window.lucide.createIcons();
    };

    filterBtns.forEach(btn => {
        btn.onclick = () => { currentFilter = btn.dataset.filter; paint(); };
    });

    // Buscador, filtro por responsable e icono "ver pasadas".
    const searchInput = wrapper.querySelector('#cmp-search');
    searchInput.addEventListener('input', () => { searchQuery = searchInput.value; paint(); });
    const respFilter = wrapper.querySelector('#cmp-resp-filter');
    respFilter.addEventListener('change', () => { responsableFilter = respFilter.value; paint(); });
    pastBtn.addEventListener('click', () => {
        showPast = !showPast;
        pastBtn.title = showPast ? 'Ocultar pasadas' : 'Ver pasadas';
        paint();
    });

    content.addEventListener('click', (e) => {
        // Si clickearon el link del adjunto, lo dejamos descargar (no abrimos el editor).
        if (e.target.closest('a')) return;
        const el = e.target.closest('.cmp-card, .cmp-past-item');
        if (el) window.openActivityDetail(el.dataset.id);
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
    const occ = secretariaOccurrences()
        .filter(o => o.occDate >= from && o.occDate <= to)
        .sort((a, b) => {
            if (a.occDate !== b.occDate) return a.occDate.localeCompare(b.occDate);
            return (fmtTime(a.act.time) || '99:99').localeCompare(fmtTime(b.act.time) || '99:99');
        });

    const groups = new Map();
    for (const o of occ) {
        if (!groups.has(o.occDate)) groups.set(o.occDate, []);
        groups.get(o.occDate).push(o);
    }

    let body = '';
    if (occ.length === 0) {
        body = '<p>No hay actividades en el rango elegido.</p>';
    } else {
        for (const [date, items] of groups) {
            const h = dayHeader(date);
            body += `<div class="cmp-pa-day"><h2>${h.title} · ${h.date}</h2>`;
            for (const o of items) {
                const act = o.act;
                const meta = [];
                if (act.location) meta.push(`<strong>Lugar:</strong> ${esc(act.location)}`);
                if (act.participants) meta.push(`<strong>Participa:</strong> ${esc(act.participants)}`);
                const dayTag = o.dayCount > 1 ? ` (Día ${o.dayIndex} de ${o.dayCount})` : '';
                body += `<div class="cmp-pa-act">
                    <div class="cmp-pa-time">${esc(timeLabel(act))}</div>
                    <div>
                        <div class="cmp-pa-title">${esc(act.title) || '(Sin título)'}${dayTag}</div>
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
