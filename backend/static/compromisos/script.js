/*
 * Vista pública de la Agenda de Compromisos institucionales BCR.
 *
 * El token de acceso está en la URL: /compromisos/{token}. Lo extraemos del
 * path y lo mandamos al backend, que valida que coincida con la env var
 * COMPROMISOS_PUBLIC_TOKEN. Si no coincide, devuelve 404 y mostramos error.
 */

const TOKEN = window.location.pathname.split('/compromisos/')[1] || '';
const API_URL = `/api/compromisos/${TOKEN}`;

// State
let activities = [];
let currentFilter = 'proximas';

// ---------- Date helpers (locales, zona horaria del browser) ----------
function todayISO() {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.toISOString().split('T')[0];
}
function endOfWeekISO() {
    // Domingo de esta semana (lun=1..dom=0 → cuando es dom, days=0).
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    const dow = d.getDay();
    const daysToSunday = dow === 0 ? 0 : 7 - dow;
    d.setDate(d.getDate() + daysToSunday);
    return d.toISOString().split('T')[0];
}
function plusDaysISO(n) {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() + n);
    return d.toISOString().split('T')[0];
}

const MONTHS = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
const WEEKDAYS = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];

function formatDayHeader(dateISO) {
    const [y, m, d] = dateISO.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    const dow = WEEKDAYS[dt.getDay()];
    return {
        title: dow.toUpperCase(),
        date: `${d} de ${MONTHS[m - 1]}`,
    };
}

function formatTime(t) {
    if (!t || t === 'A definir' || t === '00:00') return null;
    return t;
}

// ---------- Filter helpers ----------
function passesFilter(act, filter) {
    const today = todayISO();
    if (filter === 'todas') return true;
    if (filter === 'hoy') return act.date === today;
    if (filter === 'semana') return act.date >= today && act.date <= endOfWeekISO();
    if (filter === 'sem7') return act.date >= today && act.date <= plusDaysISO(7);
    if (filter === 'sem30') return act.date >= today && act.date <= plusDaysISO(30);
    // 'proximas' = hoy y futuro
    return act.date >= today;
}

// ---------- Render ----------
function render() {
    const content = document.getElementById('content');
    const filtered = activities
        .filter(a => passesFilter(a, currentFilter))
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            const aT = formatTime(a.time) || '99:99';
            const bT = formatTime(b.time) || '99:99';
            return aT.localeCompare(bT);
        });

    if (filtered.length === 0) {
        content.innerHTML = '<div class="empty">No hay actividades para este filtro.</div>';
        return;
    }

    // Agrupar por fecha
    const groups = new Map();
    for (const act of filtered) {
        if (!groups.has(act.date)) groups.set(act.date, []);
        groups.get(act.date).push(act);
    }

    let html = '';
    for (const [date, items] of groups) {
        const header = formatDayHeader(date);
        html += `<section class="day-group">`;
        html += `<h2 class="day-header">${header.title}<span class="day-date">${header.date}</span></h2>`;
        for (const act of items) {
            html += renderActivity(act);
        }
        html += `</section>`;
    }
    content.innerHTML = html;
}

function renderActivity(act) {
    const time = formatTime(act.time);
    const timeHtml = time
        ? `<div class="activity-time">${time}</div>`
        : `<div class="activity-time"><span class="tbd">A definir</span></div>`;

    const descHtml = act.description ? `<div class="activity-description">${esc(act.description)}</div>` : '';
    const meta = [];
    if (act.location) {
        meta.push(`<span class="activity-meta-item"><strong>Lugar:</strong> ${esc(act.location)}</span>`);
    }
    if (act.participants) {
        meta.push(`<span class="activity-meta-item"><strong>Participa:</strong> ${esc(act.participants)}</span>`);
    }
    const metaHtml = meta.length ? `<div class="activity-meta">${meta.join('')}</div>` : '';

    return `
        <article class="activity">
            ${timeHtml}
            <div class="activity-body">
                <h3 class="activity-title">${esc(act.title) || '(Sin título)'}</h3>
                ${descHtml}
                ${metaHtml}
            </div>
        </article>
    `;
}

function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ---------- Fetch ----------
async function loadAndRender() {
    const content = document.getElementById('content');
    try {
        const res = await fetch(API_URL);
        if (res.status === 404) {
            content.innerHTML = '<div class="error"><h2>Página no encontrada</h2><p>El enlace puede haber expirado. Pedile uno nuevo al equipo de Comunicación.</p></div>';
            return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        activities = await res.json();
        render();
    } catch (e) {
        console.error(e);
        content.innerHTML = '<div class="error"><h2>No se pudo cargar la agenda</h2><p>Refrescá la página en un rato.</p></div>';
    }
}

// ---------- Filter buttons ----------
document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter;
        render();
    });
});

// ---------- Imprimir (PDF por rango de fechas, vía el diálogo del navegador) ----------
function openPrintModal() {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.45);z-index:1000;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `
        <div style="background:#fff;border-radius:12px;padding:1.5rem;max-width:360px;width:90%;box-shadow:0 20px 40px rgba(0,0,0,0.2);">
            <h3 style="margin:0 0 0.35rem;font-size:1.1rem;">Imprimir agenda</h3>
            <p style="margin:0 0 1rem;color:#64748b;font-size:0.85rem;">Elegí el rango de fechas a incluir en el PDF.</p>
            <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:0.25rem;">Desde</label>
            <input id="pf" type="date" value="${todayISO()}" style="width:100%;padding:0.5rem 0.6rem;border:1px solid #e2e8f0;border-radius:0.4rem;margin-bottom:0.75rem;font-family:inherit;">
            <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:0.25rem;">Hasta</label>
            <input id="pt" type="date" value="${plusDaysISO(30)}" style="width:100%;padding:0.5rem 0.6rem;border:1px solid #e2e8f0;border-radius:0.4rem;margin-bottom:0.5rem;font-family:inherit;">
            <div id="pe" style="display:none;color:#b91c1c;font-size:0.78rem;margin-bottom:0.5rem;"></div>
            <div style="display:flex;gap:0.5rem;justify-content:flex-end;margin-top:0.75rem;">
                <button id="pc" style="background:#fff;border:1px solid #e2e8f0;padding:0.5rem 1rem;border-radius:0.4rem;font-weight:600;cursor:pointer;font-family:inherit;">Cancelar</button>
                <button id="pg" style="background:#0742ab;color:#fff;border:none;padding:0.5rem 1.1rem;border-radius:0.4rem;font-weight:600;cursor:pointer;font-family:inherit;">Imprimir</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.querySelector('#pc').onclick = close;
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
    overlay.querySelector('#pg').onclick = () => {
        const from = overlay.querySelector('#pf').value;
        const to = overlay.querySelector('#pt').value;
        const err = overlay.querySelector('#pe');
        if (!from || !to) { err.textContent = 'Completá las dos fechas.'; err.style.display = 'block'; return; }
        if (to < from) { err.textContent = 'La fecha "Hasta" debe ser posterior a "Desde".'; err.style.display = 'block'; return; }
        close();
        printRange(from, to);
    };
}

function printRange(from, to) {
    const inRange = activities
        .filter(a => a.date >= from && a.date <= to)
        .sort((a, b) => {
            if (a.date !== b.date) return a.date.localeCompare(b.date);
            return (formatTime(a.time) || '99:99').localeCompare(formatTime(b.time) || '99:99');
        });

    const groups = new Map();
    for (const act of inRange) {
        if (!groups.has(act.date)) groups.set(act.date, []);
        groups.get(act.date).push(act);
    }

    let body = '';
    if (inRange.length === 0) {
        body = '<p>No hay actividades en el rango elegido.</p>';
    } else {
        for (const [date, items] of groups) {
            const h = formatDayHeader(date);
            body += `<div class="cmp-pa-day"><h2>${h.title} · ${h.date}</h2>`;
            for (const act of items) {
                const t = formatTime(act.time);
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

    const fmtRange = (iso) => { const [y, m, d] = iso.split('-').map(Number); return `${d}/${m}/${y}`; };

    const area = document.createElement('div');
    area.id = 'cmp-print-area';
    area.innerHTML = `
        <div class="cmp-pa-head">
            <h1>Agenda de Compromisos — BCR</h1>
            <p>Período: ${fmtRange(from)} al ${fmtRange(to)}</p>
        </div>
        ${body}
    `;
    document.body.appendChild(area);

    const cleanup = () => { area.remove(); window.removeEventListener('afterprint', cleanup); };
    window.addEventListener('afterprint', cleanup);
    window.print();
    setTimeout(() => { if (document.getElementById('cmp-print-area')) cleanup(); }, 1000);
}

const printBtn = document.getElementById('print-btn');
if (printBtn) printBtn.addEventListener('click', openPrintModal);

// ---------- Auto-refresh cada 5 min ----------
setInterval(loadAndRender, 5 * 60 * 1000);

// ---------- Boot ----------
loadAndRender();
