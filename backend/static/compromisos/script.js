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
    if (filter === 'semana') {
        return act.date >= today && act.date <= endOfWeekISO();
    }
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

    const meta = [];
    if (act.location) {
        meta.push(`<span class="activity-meta-item"><strong>Lugar:</strong> ${esc(act.location)}</span>`);
    }
    if (act.participants) {
        meta.push(`<span class="activity-meta-item"><strong>Autoridades:</strong> ${esc(act.participants)}</span>`);
    }
    const metaHtml = meta.length ? `<div class="activity-meta">${meta.join('')}</div>` : '';
    const descHtml = act.description ? `<div class="activity-description">${esc(act.description)}</div>` : '';

    return `
        <article class="activity">
            ${timeHtml}
            <div class="activity-body">
                <h3 class="activity-title">${esc(act.title) || '(Sin título)'}</h3>
                ${metaHtml}
                ${descHtml}
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

function setUpdatedAt() {
    const el = document.getElementById('updated-at');
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    el.textContent = `Actualizado ${hh}:${mm}`;
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
        setUpdatedAt();
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

// ---------- Auto-refresh cada 5 min ----------
setInterval(loadAndRender, 5 * 60 * 1000);

// ---------- Boot ----------
loadAndRender();
