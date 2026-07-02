/*
 * Vista pública de la Agenda de Compromisos institucionales BCR.
 *
 * El token de acceso está en la URL: /compromisos/{token}. Lo extraemos del
 * path y lo mandamos al backend, que valida que coincida con la env var
 * COMPROMISOS_PUBLIC_TOKEN. Si no coincide, devuelve 404 y mostramos error.
 */

const TOKEN = window.location.pathname.split('/compromisos/')[1] || '';
const API_URL = `/api/compromisos/${TOKEN}`;

// Ícono de descarga (inline) para el link "Ver Información Adicional".
const DOWNLOAD_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';

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
// Muestra la hora, o el rango "HH:MM a HH:MM" si hay end_time.
function formatTimeDisplay(act) {
    const start = formatTime(act.time);
    if (!start) return null;
    if (act.end_time && formatTime(act.end_time)) return `${start} a ${act.end_time}`;
    return start;
}

// ---------- Multi-día: una actividad con end_date se muestra en cada día ----------
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
function occurrencesOf(act) {
    if (act.end_date && act.end_date > act.date) {
        const days = eachDay(act.date, act.end_date);
        return days.map((d, i) => ({ act, occDate: d, dayIndex: i + 1, dayCount: days.length }));
    }
    return [{ act, occDate: act.date, dayIndex: 1, dayCount: 1 }];
}

// ---------- Filter helpers ----------
function passesFilter(dateISO, filter) {
    const today = todayISO();
    if (filter === 'todas') return true;
    if (filter === 'hoy') return dateISO === today;
    if (filter === 'semana') return dateISO >= today && dateISO <= endOfWeekISO();
    if (filter === 'sem7') return dateISO >= today && dateISO <= plusDaysISO(7);
    if (filter === 'sem30') return dateISO >= today && dateISO <= plusDaysISO(30);
    return dateISO >= today; // 'proximas'
}

// ---------- Render ----------
function render() {
    const content = document.getElementById('content');
    const occ = activities
        .flatMap(occurrencesOf)
        .filter(o => passesFilter(o.occDate, currentFilter))
        .sort((a, b) => {
            if (a.occDate !== b.occDate) return a.occDate.localeCompare(b.occDate);
            return (formatTime(a.act.time) || '99:99').localeCompare(formatTime(b.act.time) || '99:99');
        });

    if (occ.length === 0) {
        content.innerHTML = '<div class="empty">No hay actividades para este filtro.</div>';
        return;
    }

    // Agrupar por día (cada ocurrencia va bajo su fecha)
    const groups = new Map();
    for (const o of occ) {
        if (!groups.has(o.occDate)) groups.set(o.occDate, []);
        groups.get(o.occDate).push(o);
    }

    let html = '';
    for (const [date, items] of groups) {
        const header = formatDayHeader(date);
        html += `<section class="day-group">`;
        html += `<h2 class="day-header">${header.title}<span class="day-date">${header.date}</span></h2>`;
        for (const o of items) {
            html += renderActivity(o);
        }
        html += `</section>`;
    }
    content.innerHTML = html;
}

function renderActivity(occ) {
    const act = occ.act;
    const time = formatTimeDisplay(act);
    const timeHtml = time
        ? `<div class="activity-time">${esc(time)}</div>`
        : `<div class="activity-time"><span class="tbd">A definir</span></div>`;

    const dayBadge = occ.dayCount > 1 ? `<span class="activity-daybadge">Día ${occ.dayIndex} de ${occ.dayCount}</span>` : '';
    const descHtml = act.description ? `<div class="activity-description">${esc(act.description)}</div>` : '';
    const meta = [];
    if (act.location) {
        meta.push(`<span class="activity-meta-item"><strong>Lugar:</strong> ${esc(act.location)}</span>`);
    }
    if (act.participants) {
        meta.push(`<span class="activity-meta-item"><strong>Participa:</strong> ${esc(act.participants)}</span>`);
    }
    const metaHtml = meta.length ? `<div class="activity-meta">${meta.join('')}</div>` : '';
    const attachHtml = act.attachment_url
        ? `<div class="activity-attach"><a href="${esc(act.attachment_url)}" target="_blank" rel="noopener" download>${DOWNLOAD_ICON} Ver Información Adicional</a></div>`
        : '';

    return `
        <article class="activity">
            ${timeHtml}
            <div class="activity-body">
                <h3 class="activity-title">${esc(act.title) || '(Sin título)'}</h3>
                ${dayBadge}
                ${descHtml}
                ${metaHtml}
                ${attachHtml}
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
    const occ = activities
        .flatMap(occurrencesOf)
        .filter(o => o.occDate >= from && o.occDate <= to)
        .sort((a, b) => {
            if (a.occDate !== b.occDate) return a.occDate.localeCompare(b.occDate);
            return (formatTime(a.act.time) || '99:99').localeCompare(formatTime(b.act.time) || '99:99');
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
            const h = formatDayHeader(date);
            body += `<div class="cmp-pa-day"><h2>${h.title} · ${h.date}</h2>`;
            for (const o of items) {
                const act = o.act;
                const t = formatTimeDisplay(act);
                const meta = [];
                if (act.location) meta.push(`<strong>Lugar:</strong> ${esc(act.location)}`);
                if (act.participants) meta.push(`<strong>Participa:</strong> ${esc(act.participants)}`);
                const dayTag = o.dayCount > 1 ? ` (Día ${o.dayIndex} de ${o.dayCount})` : '';
                body += `<div class="cmp-pa-act">
                    <div class="cmp-pa-time">${t ? esc(t) : 'A definir'}</div>
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

    const fmtRange = (iso) => { const [y, m, d] = iso.split('-').map(Number); return `${d}/${m}/${y}`; };

    const area = document.createElement('div');
    area.id = 'cmp-print-area';
    area.innerHTML = `
        <div class="cmp-pa-head">
            <img class="cmp-pa-logo" src="/static/compromisos/logo_bcr_azul.png" alt="Bolsa de Comercio de Rosario">
            <h1>Agenda de Compromisos</h1>
            <p>Período: ${fmtRange(from)} al ${fmtRange(to)}</p>
        </div>
        ${body}
    `;
    document.body.appendChild(area);

    const cleanup = () => { area.remove(); window.removeEventListener('afterprint', cleanup); };
    window.addEventListener('afterprint', cleanup);

    // Esperamos a que el logo cargue antes de imprimir (si no, sale en blanco).
    let printed = false;
    const go = () => {
        if (printed) return;
        printed = true;
        window.print();
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

const printBtn = document.getElementById('print-btn');
if (printBtn) printBtn.addEventListener('click', openPrintModal);

// ---------- Auto-refresh cada 5 min ----------
setInterval(loadAndRender, 5 * 60 * 1000);

// ---------- Boot ----------
loadAndRender();
