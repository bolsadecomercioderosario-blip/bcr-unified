/**
 * Vista "Traslados" — David Cardone (rol 'traslados').
 *
 * Listado READ-ONLY de las actividades donde Secretaría pidió transporte. Se
 * trae su propio endpoint acotado (/api/agenda/actividades/traslados), que NO
 * expone campos internos. No permite editar nada.
 */
const DAYS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];

function esc(s) {
    return (s == null ? '' : String(s))
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.split('-');
    const date = new Date(y, m - 1, d);
    return `${DAYS[date.getDay()]} ${parseInt(d)}/${parseInt(m)}`;
}

function fmtWhen(a) {
    const multi = a.end_date && a.end_date > a.date;
    const dateStr = multi ? `${fmtDate(a.date)} → ${fmtDate(a.end_date)}` : fmtDate(a.date);
    let hora = a.time || '';
    if (hora === 'Sin horario') hora = 'Todo el día';
    else if (hora === 'A definir') hora = 'Horario a definir';
    else if (a.end_time) hora = `${a.time} a ${a.end_time}`;
    return { dateStr, hora };
}

function cardHTML(a) {
    const { dateStr, hora } = fmtWhen(a);
    const partes = [a.participants, a.participants_me].filter(Boolean).join(' · ');
    return `
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px 18px;margin-bottom:12px;">
      <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:baseline;">
        <div style="font-weight:700;color:#0742ab;min-width:170px;">${esc(dateStr)}</div>
        <div style="font-weight:600;color:#111827;">${esc(hora)}</div>
      </div>
      <div style="font-weight:700;font-size:1.02rem;margin:6px 0 4px;color:#111827;">${esc(a.title)}</div>
      ${a.location ? `<div style="color:#374151;font-size:0.92rem;"><strong>Lugar:</strong> ${esc(a.location)}</div>` : ''}
      ${partes ? `<div style="color:#374151;font-size:0.92rem;"><strong>Participa:</strong> ${esc(partes)}</div>` : ''}
      ${a.traslado_indicaciones ? `<div style="margin-top:8px;padding:10px 12px;background:#eef4ff;border:1px solid #cfe0ff;border-radius:8px;color:#1e3a8a;font-size:0.92rem;white-space:pre-wrap;"><strong>Indicaciones:</strong> ${esc(a.traslado_indicaciones)}</div>` : ''}
    </div>`;
}

async function fetchTraslados() {
    const r = await fetch('/api/agenda/actividades/traslados');
    if (!r.ok) throw new Error('No se pudo cargar el listado.');
    return await r.json();
}

function listHTML(items) {
    if (!items.length) {
        return `<div style="text-align:center;color:#6b7280;padding:48px 16px;">
            No hay traslados solicitados por el momento.</div>`;
    }
    return items.map(cardHTML).join('');
}

let _pollStarted = false;

export async function renderTraslados(container) {
    container.innerHTML = `
      <div style="max-width:860px;margin:0 auto;padding:22px 18px;">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
          <div style="width:40px;height:40px;border-radius:10px;background:#0742ab;display:flex;align-items:center;justify-content:center;">
            <i data-lucide="bus" style="color:#fff;"></i>
          </div>
          <div>
            <h1 style="margin:0;font-size:1.25rem;color:#111827;">Servicio de Traslados</h1>
            <div style="color:#6b7280;font-size:0.88rem;">Actividades en las que se solicita traslado · Bolsa de Comercio de Rosario</div>
          </div>
        </div>
        <div id="trs-list" style="margin-top:18px;">
          <div style="text-align:center;color:#6b7280;padding:40px;">Cargando…</div>
        </div>
      </div>`;
    if (window.lucide) window.lucide.createIcons();

    const listEl = container.querySelector('#trs-list');
    async function paint() {
        try {
            const items = await fetchTraslados();
            listEl.innerHTML = listHTML(items);
        } catch (e) {
            listEl.innerHTML = `<div style="text-align:center;color:#b91c1c;padding:40px;">${esc(e.message || 'Error')}</div>`;
        }
    }
    await paint();

    // Auto-refresco cada 60s (una sola vez por carga de página).
    if (!_pollStarted) {
        _pollStarted = true;
        setInterval(() => {
            const el = document.querySelector('#trs-list');
            if (el && !document.hidden) {
                fetchTraslados().then(items => { el.innerHTML = listHTML(items); }).catch(() => {});
            }
        }, 60000);
    }
}
