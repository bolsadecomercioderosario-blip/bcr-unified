/* BCR en Aapresid 2026 — app (Fase 1). Vanilla JS, sin build.
   Login por usuario, tablero de 8 bloques, ABM de personas/áreas, presencias. */
(function () {
  'use strict';

  const TOKEN_KEY = 'aapresid_token';
  const API = '/api/aapresid';
  let STATE = { event: null, shifts: [], areas: [], people: [], attendance: [] };
  let ME = null;
  let currentView = 'board';

  const $ = (s) => document.querySelector(s);
  const el = (id) => document.getElementById(id);

  // ---------------- utils ----------------
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  const WEEKDAYS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
  const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  function dayName(iso) { const [y, m, d] = iso.split('-').map(Number); return WEEKDAYS[new Date(y, m - 1, d).getDay()]; }
  function dateLabel(iso) { const [y, m, d] = iso.split('-').map(Number); return `${d} de ${MONTHS[m - 1]}`; }
  function dayIndexMap() {
    const dates = [...new Set(STATE.shifts.map(s => s.date))].sort();
    const map = {}; dates.forEach((d, i) => map[d] = i % 3); return map;
  }
  function shiftClass(name) {
    const n = (name || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    if (n.includes('manana')) return 'turno-manana';
    if (n.includes('mediodia')) return 'turno-mediodia';
    if (n.includes('tarde')) return 'turno-tarde';
    return '';
  }
  const personById = (id) => STATE.people.find(p => p.id === id);
  const areaById = (id) => STATE.areas.find(a => a.id === id);
  const shiftById = (id) => STATE.shifts.find(s => s.id === id);
  const areaName = (id) => { const a = areaById(id); return a ? a.name : ''; };

  function toast(msg, type) {
    const t = el('toast'); t.textContent = msg; t.className = 'toast show ' + (type || '');
    setTimeout(() => { t.className = 'toast'; }, 2600);
  }

  // ---------------- token / api ----------------
  const getToken = () => localStorage.getItem(TOKEN_KEY) || '';
  const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
  const clearToken = () => localStorage.removeItem(TOKEN_KEY);

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    const tk = getToken();
    if (tk) opts.headers.Authorization = 'Bearer ' + tk;
    const res = await fetch(API + path, opts);
    if (res.status === 401) { clearToken(); showLogin('La sesión expiró. Ingresá de nuevo.'); throw new Error('401'); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* puede no haber body */ }
    if (!res.ok) { const err = new Error((data && data.detail) || 'Error'); err.detail = (data && data.detail); throw err; }
    return data;
  }

  // ---------------- login ----------------
  function showLogin(msg) {
    el('app').classList.add('hidden');
    el('login').classList.remove('hidden');
    el('login-err').textContent = msg || '';
  }
  function hideLogin() { el('login').classList.add('hidden'); }

  el('login-card').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = el('login-email').value.trim();
    const password = el('login-pass').value;
    el('login-err').textContent = '';
    const btn = el('login-btn'); btn.disabled = true; btn.textContent = 'Ingresando…';
    try {
      const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
      setToken(data.token); ME = data.user;
      el('login-pass').value = '';
      hideLogin(); await boot();
    } catch (err) {
      el('login-err').textContent = err.detail || 'Email o contraseña incorrectos';
    } finally { btn.disabled = false; btn.textContent = 'Ingresar'; }
  });

  el('btn-logout').addEventListener('click', () => { clearToken(); ME = null; showLogin(); });

  // ---------------- boot / load ----------------
  async function boot() {
    if (!ME) { ME = await api('/auth/me'); }
    el('app').classList.remove('hidden');
    document.body.dataset.role = ME.role;
    el('user-chip').textContent = ME.full_name || ME.email;
    await loadState(false);
    startPolling();
  }

  async function loadState(silent) {
    try {
      const data = await api('/state');
      const changed = JSON.stringify(STATE) !== JSON.stringify(data);
      STATE = data;
      if (el('event-name')) el('event-name').textContent = 'BCR en ' + (STATE.event ? STATE.event.name : 'Aapresid');
      if (el('event-sub')) el('event-sub').textContent = STATE.event ? STATE.event.location : '';
      if (!silent || changed) renderView();
    } catch (e) { if (e.message !== '401') console.error(e); }
  }

  let pollingOn = false;
  function startPolling() {
    if (pollingOn) return; pollingOn = true;
    setInterval(() => {
      if (document.hidden) return;
      if (!el('modal').classList.contains('hidden')) return; // no pisar un form abierto
      const a = document.activeElement;
      if (a && a.matches && a.matches('input,select,textarea')) return;
      loadState(true);
    }, 15000);
  }

  // ---------------- nav ----------------
  el('topnav').addEventListener('click', (e) => {
    const b = e.target.closest('.nav-item'); if (!b) return;
    currentView = b.dataset.view;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === currentView));
    renderView();
  });

  function renderView() {
    if (currentView === 'board') return renderBoard();
    if (currentView === 'people') return renderPeople();
    if (currentView === 'areas') return renderAreas();
  }

  // ---------------- BOARD ----------------
  function renderBoard() {
    const dayIdx = dayIndexMap();
    const att = STATE.attendance;
    const distinctPeople = new Set(att.map(a => a.person_id)).size;
    const shiftsNoResp = STATE.shifts.filter(s => !att.some(a => a.shift_id === s.id && a.is_shift_responsible)).length;
    const kpis = [
      { n: distinctPeople, l: 'Personas participantes' },
      { n: att.length, l: 'Presencias asignadas' },
      { n: shiftsNoResp, l: 'Turnos sin responsable', warn: shiftsNoResp > 0 },
      { n: STATE.areas.filter(a => a.active).length, l: 'Áreas activas' },
    ];
    const kpiHtml = kpis.map(k => `<div class="kpi ${k.warn ? 'warn' : ''}"><div class="n">${k.n}</div><div class="l">${k.l}</div></div>`).join('');

    const blocks = STATE.shifts.map(s => {
      const atts = att.filter(a => a.shift_id === s.id);
      const resps = atts.filter(a => a.is_shift_responsible).map(a => personById(a.person_id)).filter(Boolean);
      const respHtml = resps.length
        ? resps.map(p => `<span class="resp-badge">★ ${esc(p.full_name)}</span>`).join('')
        : `<span class="no-resp">⚠ Sin responsable</span>`;
      const peopleHtml = atts.length
        ? atts.map(a => {
            const p = personById(a.person_id); if (!p) return '';
            return `<div class="prow" data-action="edit-att" data-id="${a.id}">
              ${a.is_shift_responsible ? '<span class="pstar">★</span>' : ''}
              <span class="pname">${esc(p.full_name)}</span>
              ${p.area_id ? `<span class="parea">${esc(areaName(p.area_id))}</span>` : ''}
            </div>`;
          }).join('')
        : `<div class="block-empty">Sin personas asignadas.</div>`;
      return `<div class="block day-${dayIdx[s.date]}">
        <div class="block-head">
          <div class="block-day">${dayName(s.date)} <span class="block-date">· ${dateLabel(s.date)}</span></div>
          <div class="block-shift"><span class="shift-badge ${shiftClass(s.name)}">${esc(s.name)}</span><span class="block-time">${esc(s.start_time)}–${esc(s.end_time)}</span></div>
          <div class="block-resp">${respHtml}</div>
        </div>
        <div class="block-people">${peopleHtml}</div>
        <div class="block-foot">
          <span class="block-count">Total: <b>${atts.length}</b></span>
          <button class="btn-soft" data-action="add-person" data-shift="${s.id}">+ Persona</button>
        </div>
      </div>`;
    }).join('');

    $('#view').innerHTML = `
      <div class="view-head"><h2>Tablero de cobertura</h2></div>
      <div class="kpis">${kpiHtml}</div>
      <div class="board">${blocks}</div>`;
  }

  // ---------------- PEOPLE ----------------
  function renderPeople() {
    const rows = STATE.people.map(p => `
      <div class="list-row">
        <div class="grow">
          <div class="rname">${esc(p.full_name)} ${p.active ? '' : '<span class="badge off">inactiva</span>'}</div>
          <div class="rmeta">${p.area_id ? esc(areaName(p.area_id)) : 'Sin área'}${p.role ? ' · ' + esc(p.role) : ''}${p.email ? ' · ' + esc(p.email) : ''}</div>
        </div>
        <button class="btn-line btn-sm" data-action="edit-person" data-id="${p.id}">Editar</button>
      </div>`).join('') || `<div class="empty-state">No hay personas cargadas todavía.</div>`;
    $('#view').innerHTML = `
      <div class="view-head"><h2>Personas</h2><button class="btn-primary" data-action="new-person">+ Nueva persona</button></div>
      <div class="card">${rows}</div>`;
  }

  // ---------------- AREAS ----------------
  function renderAreas() {
    const rows = STATE.areas.map(a => `
      <div class="list-row">
        <div class="grow">
          <div class="rname">${esc(a.name)} ${a.active ? '<span class="badge on">activa</span>' : '<span class="badge off">inactiva</span>'}</div>
          <div class="rmeta">${esc(a.description || '')}${a.responsible ? ' · Ref: ' + esc(a.responsible) : ''}</div>
        </div>
        <button class="btn-line btn-sm" data-action="edit-area" data-id="${a.id}">Editar</button>
      </div>`).join('') || `<div class="empty-state">No hay áreas cargadas.</div>`;
    $('#view').innerHTML = `
      <div class="view-head"><h2>Áreas de la BCR</h2><button class="btn-primary" data-action="new-area">+ Nueva área</button></div>
      <div class="card">${rows}</div>`;
  }

  // ---------------- delegación de acciones ----------------
  $('#view').addEventListener('click', (e) => {
    const b = e.target.closest('[data-action]'); if (!b) return;
    const act = b.dataset.action;
    if (act === 'add-person') openAttendanceForm(Number(b.dataset.shift), null);
    else if (act === 'edit-att') openAttendanceForm(null, STATE.attendance.find(a => a.id === Number(b.dataset.id)));
    else if (act === 'new-person') openPersonForm(null);
    else if (act === 'edit-person') openPersonForm(personById(Number(b.dataset.id)));
    else if (act === 'new-area') openAreaForm(null);
    else if (act === 'edit-area') openAreaForm(areaById(Number(b.dataset.id)));
  });

  // ---------------- modal helpers ----------------
  function openModal(html) { el('modal-card').innerHTML = html; el('modal').classList.remove('hidden'); }
  function closeModal() { el('modal').classList.add('hidden'); el('modal-card').innerHTML = ''; }
  el('modal').addEventListener('mousedown', (e) => { if (e.target === el('modal')) closeModal(); });

  function shiftOptions(selectedId) {
    const dayIdx = dayIndexMap();
    return STATE.shifts.map(s =>
      `<option value="${s.id}" ${s.id === selectedId ? 'selected' : ''}>${dayName(s.date)} ${dateLabel(s.date)} · ${esc(s.name)} (${s.start_time}–${s.end_time})</option>`
    ).join('');
  }

  // ---------------- attendance form ----------------
  function openAttendanceForm(shiftId, att) {
    const editing = !!att;
    const sid = editing ? att.shift_id : shiftId;
    // Para "agregar", excluir personas ya asignadas a ese turno.
    const assigned = new Set(STATE.attendance.filter(a => a.shift_id === sid && (!editing || a.id !== att.id)).map(a => a.person_id));
    const peopleOpts = STATE.people.filter(p => p.active && (editing || !assigned.has(p.id)))
      .map(p => `<option value="${p.id}" ${editing && att.person_id === p.id ? 'selected' : ''}>${esc(p.full_name)}${p.area_id ? ' — ' + esc(areaName(p.area_id)) : ''}</option>`).join('');
    const areaOpts = STATE.areas.filter(a => a.active).map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join('');

    openModal(`
      <div class="modal-head"><h3>${editing ? 'Editar presencia' : 'Agregar persona al turno'}</h3><button class="modal-x" data-x>×</button></div>
      <label>Turno</label>
      <select id="af-shift">${shiftOptions(sid)}</select>
      <label>Persona</label>
      <select id="af-person">${peopleOpts || '<option value="">(sin personas disponibles)</option>'}
        ${editing ? '' : '<option value="__new">➕ Crear nueva persona…</option>'}
      </select>
      <div id="af-newperson" class="hidden" style="background:#f8fafc;border:1px solid var(--border);border-radius:.5rem;padding:.7rem;margin-bottom:.8rem;">
        <label>Nombre y apellido</label>
        <input id="af-np-name" type="text" placeholder="Ej: María García">
        <label>Área</label>
        <select id="af-np-area"><option value="">(sin área)</option>${areaOpts}</select>
      </div>
      <label class="check-line"><input type="checkbox" id="af-resp" ${editing && att.is_shift_responsible ? 'checked' : ''}> Es responsable del turno</label>
      <div class="grid-2">
        <div><label>Hora ingreso (opcional)</label><input id="af-in" type="time" value="${editing ? esc(att.start_time || '') : ''}"></div>
        <div><label>Hora salida (opcional)</label><input id="af-out" type="time" value="${editing ? esc(att.end_time || '') : ''}"></div>
      </div>
      <label>Función durante el evento (opcional)</label>
      <input id="af-role" type="text" value="${editing ? esc(att.event_role || '') : ''}" placeholder="Ej: Cobertura de prensa">
      <label>Observaciones (opcional)</label>
      <textarea id="af-notes" rows="2">${editing ? esc(att.notes || '') : ''}</textarea>
      <div class="modal-foot">
        ${editing ? '<button class="btn-danger left" data-del>Eliminar</button>' : ''}
        ${editing ? '<button class="btn-line" data-dup>Duplicar en…</button>' : ''}
        <button class="btn-line" data-x>Cancelar</button>
        <button class="btn-primary" data-save>Guardar</button>
      </div>
    `);

    const personSel = el('af-person');
    if (personSel) personSel.addEventListener('change', () => {
      el('af-newperson').classList.toggle('hidden', personSel.value !== '__new');
    });

    el('modal-card').querySelectorAll('[data-x]').forEach(b => b.onclick = closeModal);

    el('modal-card').querySelector('[data-save]').onclick = async () => {
      try {
        let personId = personSel ? personSel.value : String(att.person_id);
        if (personId === '__new') {
          const name = el('af-np-name').value.trim();
          if (!name) { toast('Poné el nombre de la persona nueva', 'err'); return; }
          const np = await api('/people', { method: 'POST', body: JSON.stringify({ full_name: name, area_id: el('af-np-area').value ? Number(el('af-np-area').value) : null }) });
          personId = String(np.id);
        }
        if (!personId) { toast('Elegí una persona', 'err'); return; }
        const body = {
          shift_id: Number(el('af-shift').value),
          person_id: Number(personId),
          is_shift_responsible: el('af-resp').checked,
          start_time: el('af-in').value, end_time: el('af-out').value,
          event_role: el('af-role').value, notes: el('af-notes').value,
        };
        if (editing) await api('/attendance/' + att.id, { method: 'PUT', body: JSON.stringify(body) });
        else await api('/attendance', { method: 'POST', body: JSON.stringify(body) });
        closeModal(); await loadState(false); toast('Guardado', 'ok');
      } catch (err) { toast(err.detail || 'No se pudo guardar', 'err'); }
    };

    if (editing) {
      el('modal-card').querySelector('[data-del]').onclick = async () => {
        if (!confirm('¿Eliminar esta presencia?')) return;
        try { await api('/attendance/' + att.id, { method: 'DELETE' }); closeModal(); await loadState(false); toast('Eliminada', 'ok'); }
        catch (err) { toast(err.detail || 'Error', 'err'); }
      };
      el('modal-card').querySelector('[data-dup]').onclick = async () => {
        const target = prompt('Duplicar en otro turno. Pegá el número de turno destino:\n\n' +
          STATE.shifts.map(s => `${s.id} = ${dayName(s.date)} ${dateLabel(s.date)} ${s.name}`).join('\n'));
        if (!target) return;
        try { await api('/attendance/' + att.id + '/duplicate', { method: 'POST', body: JSON.stringify({ shift_id: Number(target) }) }); closeModal(); await loadState(false); toast('Duplicada', 'ok'); }
        catch (err) { toast(err.detail || 'Error', 'err'); }
      };
    }
  }

  // ---------------- person form ----------------
  function openPersonForm(person) {
    const editing = !!person;
    const areaOpts = STATE.areas.filter(a => a.active || (editing && a.id === person.area_id))
      .map(a => `<option value="${a.id}" ${editing && person.area_id === a.id ? 'selected' : ''}>${esc(a.name)}</option>`).join('');
    openModal(`
      <div class="modal-head"><h3>${editing ? 'Editar persona' : 'Nueva persona'}</h3><button class="modal-x" data-x>×</button></div>
      <label>Nombre y apellido</label>
      <input id="pf-name" type="text" value="${editing ? esc(person.full_name) : ''}">
      <div class="grid-2">
        <div><label>Área</label><select id="pf-area"><option value="">(sin área)</option>${areaOpts}</select></div>
        <div><label>Cargo / función</label><input id="pf-role" type="text" value="${editing ? esc(person.role || '') : ''}"></div>
      </div>
      <div class="grid-2">
        <div><label>Email</label><input id="pf-email" type="email" value="${editing ? esc(person.email || '') : ''}"></div>
        <div><label>Teléfono</label><input id="pf-phone" type="text" value="${editing ? esc(person.phone || '') : ''}"></div>
      </div>
      <label class="check-line"><input type="checkbox" id="pf-active" ${!editing || person.active ? 'checked' : ''}> Activa</label>
      <div class="modal-foot">
        ${editing ? '<button class="btn-danger left" data-del>Eliminar</button>' : ''}
        <button class="btn-line" data-x>Cancelar</button>
        <button class="btn-primary" data-save>Guardar</button>
      </div>`);
    el('modal-card').querySelectorAll('[data-x]').forEach(b => b.onclick = closeModal);
    el('modal-card').querySelector('[data-save]').onclick = async () => {
      const name = el('pf-name').value.trim();
      if (!name) { toast('El nombre es obligatorio', 'err'); return; }
      const body = { full_name: name, area_id: el('pf-area').value ? Number(el('pf-area').value) : null, role: el('pf-role').value, email: el('pf-email').value, phone: el('pf-phone').value, active: el('pf-active').checked };
      try {
        if (editing) await api('/people/' + person.id, { method: 'PUT', body: JSON.stringify(body) });
        else await api('/people', { method: 'POST', body: JSON.stringify(body) });
        closeModal(); await loadState(false); toast('Guardado', 'ok');
      } catch (err) { toast(err.detail || 'Error', 'err'); }
    };
    if (editing) el('modal-card').querySelector('[data-del]').onclick = async () => {
      if (!confirm('¿Eliminar esta persona? (si tiene presencias, no se podrá; desactivala)')) return;
      try { await api('/people/' + person.id, { method: 'DELETE' }); closeModal(); await loadState(false); toast('Eliminada', 'ok'); }
      catch (err) { toast(err.detail || 'Error', 'err'); }
    };
  }

  // ---------------- area form ----------------
  function openAreaForm(area) {
    const editing = !!area;
    openModal(`
      <div class="modal-head"><h3>${editing ? 'Editar área' : 'Nueva área'}</h3><button class="modal-x" data-x>×</button></div>
      <label>Nombre</label>
      <input id="arf-name" type="text" value="${editing ? esc(area.name) : ''}">
      <label>Descripción (opcional)</label>
      <input id="arf-desc" type="text" value="${editing ? esc(area.description || '') : ''}">
      <label>Responsable de referencia (opcional)</label>
      <input id="arf-resp" type="text" value="${editing ? esc(area.responsible || '') : ''}">
      <label class="check-line"><input type="checkbox" id="arf-active" ${!editing || area.active ? 'checked' : ''}> Activa</label>
      <div class="modal-foot">
        ${editing ? '<button class="btn-danger left" data-del>Eliminar</button>' : ''}
        <button class="btn-line" data-x>Cancelar</button>
        <button class="btn-primary" data-save>Guardar</button>
      </div>`);
    el('modal-card').querySelectorAll('[data-x]').forEach(b => b.onclick = closeModal);
    el('modal-card').querySelector('[data-save]').onclick = async () => {
      const name = el('arf-name').value.trim();
      if (!name) { toast('El nombre es obligatorio', 'err'); return; }
      const body = { name, description: el('arf-desc').value, responsible: el('arf-resp').value, active: el('arf-active').checked };
      try {
        if (editing) await api('/areas/' + area.id, { method: 'PUT', body: JSON.stringify(body) });
        else await api('/areas', { method: 'POST', body: JSON.stringify(body) });
        closeModal(); await loadState(false); toast('Guardado', 'ok');
      } catch (err) { toast(err.detail || 'Error', 'err'); }
    };
    if (editing) el('modal-card').querySelector('[data-del]').onclick = async () => {
      if (!confirm('¿Eliminar esta área? (si tiene personas, no se podrá; desactivala)')) return;
      try { await api('/areas/' + area.id, { method: 'DELETE' }); closeModal(); await loadState(false); toast('Eliminada', 'ok'); }
      catch (err) { toast(err.detail || 'Error', 'err'); }
    };
  }

  // ---------------- init ----------------
  (async function init() {
    if (getToken()) { try { await boot(); return; } catch (e) { clearToken(); } }
    showLogin();
  })();
})();
