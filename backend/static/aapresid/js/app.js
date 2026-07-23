/* BCR en Aapresid 2026 — versión simple. Una sola vista: tablero.
   3 columnas (una por día), responsable por turno (texto libre) y reuniones. */
(function () {
  'use strict';

  const API = '/api/aapresid';
  let STATE = { event: null, shifts: [], areas: [], meetings: [] };

  const $ = (s) => document.querySelector(s);
  const el = (id) => document.getElementById(id);

  // ---------- utils ----------
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  const WEEKDAYS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
  const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  function dayName(iso) { const [y, m, d] = iso.split('-').map(Number); return WEEKDAYS[new Date(y, m - 1, d).getDay()]; }
  function dateLabel(iso) { const [y, m, d] = iso.split('-').map(Number); return `${d} de ${MONTHS[m - 1]}`; }
  function shiftClass(name) {
    const n = (name || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    if (n.includes('manana')) return 'turno-manana';
    if (n.includes('mediodia')) return 'turno-mediodia';
    if (n.includes('tarde')) return 'turno-tarde';
    return '';
  }
  const MEETING_STATUSES = ['Tentativa', 'Confirmada'];
  const statusClass = (s) => 'st-' + (s || 'Tentativa').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const areaById = (id) => STATE.areas.find(a => a.id === id);
  const areaName = (id) => { const a = areaById(id); return a ? a.name : ''; };
  const hasResp = (s) => s.responsible_name && s.responsible_name.trim();

  function toast(msg, type) {
    const t = el('toast'); t.textContent = msg; t.className = 'toast show ' + (type || '');
    setTimeout(() => { t.className = 'toast'; }, 2600);
  }

  // ---------- api (acceso abierto, sin token) ----------
  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    const res = await fetch(API + path, opts);
    let data = null; try { data = await res.json(); } catch (e) {}
    if (!res.ok) { const err = new Error((data && data.detail) || 'Error'); err.detail = (data && data.detail); throw err; }
    return data;
  }

  // ---------- boot / load ----------
  async function boot() {
    el('app').classList.remove('hidden');
    await loadState(false); startPolling();
  }
  async function loadState(silent) {
    try {
      const data = await api('/state');
      const compact = { event: data.event, shifts: data.shifts, areas: data.areas, meetings: data.meetings };
      const changed = JSON.stringify(STATE) !== JSON.stringify(compact);
      STATE = compact;
      if (el('event-name')) el('event-name').textContent = 'BCR en ' + (STATE.event ? STATE.event.name : 'Aapresid');
      if (el('event-sub')) el('event-sub').textContent = STATE.event ? STATE.event.location : '';
      if (!silent || changed) renderBoard();
    } catch (e) { console.error(e); }
  }
  let pollingOn = false;
  function startPolling() {
    if (pollingOn) return; pollingOn = true;
    setInterval(() => {
      if (document.hidden) return;
      if (!el('modal').classList.contains('hidden')) return;
      const a = document.activeElement; if (a && a.matches && a.matches('input,select,textarea')) return;
      loadState(true);
    }, 15000);
  }

  const meetingsForShift = (sid) => STATE.meetings.filter(mt => mt.shift_id === sid);

  // ---------- BOARD ----------
  function renderBoard() {
    const mtgs = STATE.meetings;
    const noResp = STATE.shifts.filter(s => !hasResp(s)).length;
    const kpis = [
      { n: mtgs.length, l: 'Reuniones' },
      { n: mtgs.filter(x => x.status === 'Confirmada').length, l: 'Confirmadas' },
      { n: mtgs.filter(x => x.status === 'Tentativa').length, l: 'Tentativas' },
      { n: noResp, l: 'Turnos sin responsable', warn: noResp > 0 },
    ];
    const kpiHtml = kpis.map(k => `<div class="kpi ${k.warn ? 'warn' : ''}"><div class="n">${k.n}</div><div class="l">${k.l}</div></div>`).join('');

    const dates = [...new Set(STATE.shifts.map(s => s.date))].sort();
    const cols = dates.map((d, i) => {
      const dayShifts = STATE.shifts.filter(s => s.date === d).sort((a, b) => a.display_order - b.display_order);
      const blocks = dayShifts.map(s => shiftBlock(s)).join('');
      return `<div class="day-col day-${i % 3}">
        <div class="day-col-head">${dayName(d)}<span>${dateLabel(d)}</span></div>
        ${blocks}
      </div>`;
    }).join('');

    $('#view').innerHTML = `<div class="kpis">${kpiHtml}</div><div class="columns">${cols}</div>`;
  }

  function shiftBlock(s) {
    const respHtml = hasResp(s)
      ? `<div class="turn-resp"><span class="resp-badge">★ ${esc(s.responsible_name)}</span><button class="link-btn" data-action="set-resp" data-shift="${s.id}">cambiar</button></div>`
      : `<div class="turn-resp"><span class="no-resp">⚠ Sin responsable</span><button class="btn-soft btn-sm" data-action="set-resp" data-shift="${s.id}">Designar responsable</button></div>`;
    const mrows = meetingsForShift(s.id).map(mt => {
      const meta = [mt.area_name, mt.responsible_name, mt.location].filter(Boolean).map(esc).join(' · ');
      return `<div class="mcard ${statusClass(mt.status)}" data-action="edit-meeting" data-id="${mt.id}">
        <div class="mcard-top"><span class="mtitle">${esc(mt.title)}</span><span class="mstatus ${statusClass(mt.status)}">${esc(mt.status)}</span></div>
        ${meta ? `<div class="mmeta">${meta}</div>` : ''}
      </div>`;
    }).join('');
    return `<div class="turn">
      <div class="turn-head"><span class="shift-badge ${shiftClass(s.name)}">${esc(s.name)}</span><span class="turn-time">${esc(s.start_time)}–${esc(s.end_time)}</span></div>
      ${respHtml}
      <div class="turn-meetings">${mrows || '<div class="turn-empty">Sin reuniones.</div>'}</div>
      <button class="btn-line btn-sm turn-add" data-action="add-meeting" data-shift="${s.id}">+ Reunión</button>
    </div>`;
  }

  // ---------- delegación ----------
  $('#view').addEventListener('click', (e) => {
    const b = e.target.closest('[data-action]'); if (!b) return;
    const act = b.dataset.action;
    if (act === 'set-resp') openRespForm(Number(b.dataset.shift));
    else if (act === 'add-meeting') openMeetingForm(Number(b.dataset.shift), null);
    else if (act === 'edit-meeting') openMeetingForm(null, STATE.meetings.find(x => x.id === Number(b.dataset.id)));
  });

  // ---------- modal ----------
  function openModal(html) { el('modal-card').innerHTML = html; el('modal').classList.remove('hidden'); }
  function closeModal() { el('modal').classList.add('hidden'); el('modal-card').innerHTML = ''; }
  el('modal').addEventListener('mousedown', (e) => { if (e.target === el('modal')) closeModal(); });

  // ---------- responsable del turno (texto libre) ----------
  function openRespForm(shiftId) {
    const s = STATE.shifts.find(x => x.id === shiftId); if (!s) return;
    openModal(`
      <div class="modal-head"><h3>Responsable del turno</h3><button class="modal-x" data-x>×</button></div>
      <p class="rmeta">${dayName(s.date)} ${dateLabel(s.date)} · ${esc(s.name)} (${esc(s.start_time)}–${esc(s.end_time)})</p>
      <label>¿Quién es el responsable?</label>
      <input id="rf-name" type="text" value="${esc(s.responsible_name || '')}" placeholder="Escribí el nombre">
      <div class="modal-foot">
        ${hasResp(s) ? '<button class="btn-danger left" data-clear>Quitar</button>' : ''}
        <button class="btn-line" data-x>Cancelar</button>
        <button class="btn-primary" data-save>Guardar</button>
      </div>`);
    el('rf-name').focus();
    el('modal-card').querySelectorAll('[data-x]').forEach(b => b.onclick = closeModal);
    const save = async (name) => {
      try { await api('/shifts/' + shiftId + '/responsible', { method: 'PUT', body: JSON.stringify({ responsible_name: name }) }); closeModal(); await loadState(false); toast('Guardado', 'ok'); }
      catch (err) { toast(err.detail || 'Error', 'err'); }
    };
    el('modal-card').querySelector('[data-save]').onclick = () => save(el('rf-name').value.trim());
    const clr = el('modal-card').querySelector('[data-clear]'); if (clr) clr.onclick = () => save('');
  }

  // ---------- reunión (simplificada) ----------
  function openMeetingForm(shiftId, mtg) {
    const editing = !!mtg;
    const sid = editing ? mtg.shift_id : shiftId;
    const s = STATE.shifts.find(x => x.id === sid);
    const statusOpts = MEETING_STATUSES.map(st => `<option ${editing && mtg.status === st ? 'selected' : ''}>${st}</option>`).join('');
    const isOtro = editing && mtg.location && mtg.location !== 'Stand BCR';
    openModal(`
      <div class="modal-head"><h3>${editing ? 'Editar reunión' : 'Nueva reunión'}</h3><button class="modal-x" data-x>×</button></div>
      <p class="rmeta">${s ? dayName(s.date) + ' ' + dateLabel(s.date) + ' · ' + esc(s.name) : ''}</p>
      <label>Descripción de la reunión</label>
      <textarea id="mf-title" rows="2" placeholder="¿De qué se trata?">${editing ? esc(mtg.title) : ''}</textarea>
      <div class="grid-2">
        <div><label>Responsable (quién carga)</label><input id="mf-resp" type="text" value="${editing ? esc(mtg.responsible_name || '') : ''}" placeholder="Nombre"></div>
        <div><label>Área de la BCR</label><input id="mf-area" type="text" value="${editing ? esc(mtg.area_name || '') : ''}" placeholder="Ej: Comunicación"></div>
      </div>
      <div class="grid-2">
        <div><label>Estado</label><select id="mf-status">${statusOpts}</select></div>
        <div><label>¿Dónde?</label><select id="mf-where"><option value="Stand BCR" ${!isOtro ? 'selected' : ''}>Stand BCR</option><option value="__otro" ${isOtro ? 'selected' : ''}>Otro espacio</option></select></div>
      </div>
      <div id="mf-otro-wrap" class="${isOtro ? '' : 'hidden'}"><label>¿Qué espacio?</label><input id="mf-otro" type="text" value="${isOtro ? esc(mtg.location) : ''}" placeholder="Ej: Sala 2 / Auditorio"></div>
      <div class="modal-foot">
        ${editing ? '<button class="btn-danger left" data-del>Eliminar</button>' : ''}
        <button class="btn-line" data-x>Cancelar</button>
        <button class="btn-primary" data-save>Guardar</button>
      </div>`);
    const whereSel = el('mf-where');
    whereSel.addEventListener('change', () => el('mf-otro-wrap').classList.toggle('hidden', whereSel.value !== '__otro'));
    el('modal-card').querySelectorAll('[data-x]').forEach(b => b.onclick = closeModal);
    el('modal-card').querySelector('[data-save]').onclick = async () => {
      const title = el('mf-title').value.trim();
      if (!title) { toast('Poné una descripción', 'err'); return; }
      const location = whereSel.value === '__otro' ? el('mf-otro').value.trim() : 'Stand BCR';
      const body = {
        shift_id: sid, title,
        responsible_name: el('mf-resp').value.trim(),
        area_name: el('mf-area').value.trim(),
        location, status: el('mf-status').value,
      };
      try {
        if (editing) await api('/meetings/' + mtg.id, { method: 'PUT', body: JSON.stringify(body) });
        else await api('/meetings', { method: 'POST', body: JSON.stringify(body) });
        closeModal(); await loadState(false); toast('Guardado', 'ok');
      } catch (err) { toast(err.detail || 'No se pudo guardar', 'err'); }
    };
    if (editing) el('modal-card').querySelector('[data-del]').onclick = async () => {
      if (!confirm('¿Eliminar esta reunión?')) return;
      try { await api('/meetings/' + mtg.id, { method: 'DELETE' }); closeModal(); await loadState(false); toast('Eliminada', 'ok'); }
      catch (err) { toast(err.detail || 'Error', 'err'); }
    };
  }

  // ---------- init ----------
  (async function init() { await boot(); })();
})();
