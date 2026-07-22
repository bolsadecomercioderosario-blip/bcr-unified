/* BCR en Aapresid 2026 — app (Fase 1). Vanilla JS, sin build.
   Login por usuario, tablero de 8 bloques, ABM de personas/áreas, presencias. */
(function () {
  'use strict';

  const TOKEN_KEY = 'aapresid_token';
  const API = '/api/aapresid';
  let STATE = { event: null, shifts: [], areas: [], people: [], attendance: [], meetings: [] };
  let ME = null;
  let currentView = 'board';
  let FILTERS = { q: '', day: '', shift: '', area: '', responsible: '', status: '', noResp: false };
  let detailPersonId = null, detailAreaId = null;
  const filtersActive = () => FILTERS.q || FILTERS.day || FILTERS.shift || FILTERS.area || FILTERS.responsible || FILTERS.status || FILTERS.noResp;

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
  const meetingsForShift = (sid) => STATE.meetings.filter(mt => mt.shift_id === sid);

  // --- Reuniones: estados y validaciones (advertencias, no bloqueantes) ---
  const MEETING_STATUSES = ['Tentativa', 'Confirmada', 'Realizada', 'Cancelada'];
  function statusClass(s) {
    return 'st-' + (s || 'Tentativa').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }
  function shiftForClient(date, start) {
    return STATE.shifts.find(s => s.date === date && s.start_time <= (start || '') && (start || '') < s.end_time) || null;
  }
  function timeOverlap(aS, aE, bS, bE) { return aS < bE && bS < aE; }
  function personShiftIds(pid) { return STATE.attendance.filter(a => a.person_id === pid).map(a => a.shift_id); }
  function meetingWarnings(mtg) {
    const w = [];
    const shift = shiftForClient(mtg.date, mtg.start_time);
    if (mtg.start_time && !shift) w.push('La hora de inicio no cae dentro de ningún turno.');
    const people = [...new Set([mtg.responsible_person_id, ...(mtg.participant_ids || [])].filter(Boolean))];
    if (mtg.responsible_person_id && shift && !personShiftIds(mtg.responsible_person_id).includes(shift.id)) {
      const p = personById(mtg.responsible_person_id);
      w.push(`El responsable (${p ? p.full_name : '—'}) no figura presente en ese turno.`);
    }
    people.forEach(pid => {
      if (shift && !personShiftIds(pid).includes(shift.id)) {
        const p = personById(pid);
        w.push(`${p ? p.full_name : 'Una persona'} tiene la reunión fuera de su horario de presencia.`);
      }
      STATE.meetings.filter(mm => mm.id !== mtg.id && mm.date === mtg.date &&
        (mm.responsible_person_id === pid || (mm.participant_ids || []).includes(pid)))
        .forEach(mm => {
          if (timeOverlap(mtg.start_time, mtg.end_time || mtg.start_time, mm.start_time, mm.end_time || mm.start_time)) {
            const p = personById(pid);
            w.push(`${p ? p.full_name : 'Una persona'} tiene otra reunión superpuesta ("${mm.title}").`);
          }
        });
    });
    return [...new Set(w)];
  }

  // --- Filtros ---
  const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const contentFilterActive = () => FILTERS.area || FILTERS.q || FILTERS.status;
  function shiftPassesLevel(s) {
    if (FILTERS.day && s.date !== FILTERS.day) return false;
    if (FILTERS.shift && s.name !== FILTERS.shift) return false;
    if (FILTERS.noResp && STATE.attendance.some(a => a.shift_id === s.id && a.is_shift_responsible)) return false;
    if (FILTERS.responsible && !STATE.attendance.some(a => a.shift_id === s.id && a.person_id === Number(FILTERS.responsible) && a.is_shift_responsible)) return false;
    return true;
  }
  function attPasses(a) {
    const p = personById(a.person_id); if (!p) return false;
    if (FILTERS.area && p.area_id !== Number(FILTERS.area)) return false;
    if (FILTERS.q && !norm(p.full_name).includes(norm(FILTERS.q))) return false;
    return true;
  }
  function mtgAreas(mt) {
    return [mt.responsible_person_id, ...(mt.participant_ids || [])].filter(Boolean)
      .map(id => { const p = personById(id); return p ? p.area_id : null; }).filter(Boolean);
  }
  function mtgPasses(mt) {
    if (FILTERS.status && mt.status !== FILTERS.status) return false;
    if (FILTERS.area && !mtgAreas(mt).includes(Number(FILTERS.area))) return false;
    if (FILTERS.responsible && mt.responsible_person_id !== Number(FILTERS.responsible)) return false;
    if (FILTERS.q && !norm(`${mt.title || ''} ${mt.organization || ''} ${mt.external_participants || ''}`).includes(norm(FILTERS.q))) return false;
    return true;
  }
  function fullKpis() {
    const att = STATE.attendance, mtgs = STATE.meetings;
    const distinct = new Set(att.map(a => a.person_id)).size;
    const byDay = [...new Set(STATE.shifts.map(s => s.date))].sort().map(d => {
      const sids = STATE.shifts.filter(s => s.date === d).map(s => s.id);
      return { date: d, n: new Set(att.filter(a => sids.includes(a.shift_id)).map(a => a.person_id)).size };
    });
    const noResp = STATE.shifts.filter(s => !att.some(a => a.shift_id === s.id && a.is_shift_responsible)).length;
    const overlap = new Set();
    STATE.people.forEach(p => {
      const mine = mtgs.filter(mt => mt.responsible_person_id === p.id || (mt.participant_ids || []).includes(p.id));
      for (let i = 0; i < mine.length; i++) for (let j = i + 1; j < mine.length; j++) {
        const a = mine[i], b = mine[j];
        if (a.date === b.date && timeOverlap(a.start_time, a.end_time || a.start_time, b.start_time, b.end_time || b.start_time)) overlap.add(p.id);
      }
    });
    return {
      distinct, byDay, noResp, totalMtg: mtgs.length,
      tent: mtgs.filter(x => x.status === 'Tentativa').length,
      conf: mtgs.filter(x => x.status === 'Confirmada').length,
      overlap: overlap.size, presencias: att.length,
    };
  }

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
    if (currentView === 'agenda') return renderAgenda();
    if (currentView === 'people') return renderPeople();
    if (currentView === 'areas') return renderAreas();
    if (currentView === 'person-detail') return renderPersonDetail(detailPersonId);
    if (currentView === 'area-detail') return renderAreaDetail(detailAreaId);
  }

  function goView(v) {
    currentView = v;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === v));
    renderView();
  }

  // ---------------- BOARD ----------------
  function renderBoard() {
    const k = fullKpis();
    const kpiCards = [
      { n: k.distinct, l: 'Personas' }, { n: k.presencias, l: 'Presencias' },
      { n: k.totalMtg, l: 'Reuniones' }, { n: k.tent, l: 'Tentativas' },
      { n: k.conf, l: 'Confirmadas' }, { n: k.noResp, l: 'Turnos sin responsable', warn: k.noResp > 0 },
      { n: k.overlap, l: 'Personas superpuestas', warn: k.overlap > 0 },
    ];
    const kpiHtml = kpiCards.map(c => `<div class="kpi ${c.warn ? 'warn' : ''}"><div class="n">${c.n}</div><div class="l">${c.l}</div></div>`).join('');
    const byDayHtml = k.byDay.map(d => `<span class="chip">${dayName(d.date)}: <b>${d.n}</b></span>`).join('');
    const dates = [...new Set(STATE.shifts.map(s => s.date))].sort();
    const shiftNames = [...new Set(STATE.shifts.map(s => s.name))];
    const sel = (v, cur) => v === cur ? 'selected' : '';
    $('#view').innerHTML = `
      <div class="view-head"><h2>Tablero de cobertura</h2></div>
      <div class="kpis">${kpiHtml}</div>
      ${byDayHtml ? `<div class="byday">Personas por día — ${byDayHtml}</div>` : ''}
      <div class="filterbar">
        <input id="f-q" class="f-search" type="text" placeholder="Buscar persona, reunión, empresa…" value="${esc(FILTERS.q)}">
        <select id="f-day"><option value="">Todos los días</option>${dates.map(d => `<option value="${d}" ${sel(d, FILTERS.day)}>${dayName(d)} ${dateLabel(d)}</option>`).join('')}</select>
        <select id="f-shift"><option value="">Todos los turnos</option>${shiftNames.map(n => `<option value="${n}" ${sel(n, FILTERS.shift)}>${esc(n)}</option>`).join('')}</select>
        <select id="f-area"><option value="">Todas las áreas</option>${STATE.areas.filter(a => a.active).map(a => `<option value="${a.id}" ${sel(String(a.id), FILTERS.area)}>${esc(a.name)}</option>`).join('')}</select>
        <select id="f-resp"><option value="">Cualquier responsable</option>${STATE.people.map(p => `<option value="${p.id}" ${sel(String(p.id), FILTERS.responsible)}>${esc(p.full_name)}</option>`).join('')}</select>
        <select id="f-status"><option value="">Todos los estados</option>${MEETING_STATUSES.map(s => `<option value="${s}" ${sel(s, FILTERS.status)}>${s}</option>`).join('')}</select>
        <label class="f-check"><input type="checkbox" id="f-noresp" ${FILTERS.noResp ? 'checked' : ''}> Sin responsable</label>
        <button class="btn-line btn-sm ${filtersActive() ? '' : 'hidden'}" id="f-clear">Limpiar filtros</button>
      </div>
      <div id="board-content"></div>`;
    const wire = (id, prop, ev) => { const e = el(id); if (e) e.addEventListener(ev || 'change', () => { FILTERS[prop] = (e.type === 'checkbox') ? e.checked : e.value; el('f-clear').classList.toggle('hidden', !filtersActive()); renderBoardContent(); }); };
    wire('f-q', 'q', 'input'); wire('f-day', 'day'); wire('f-shift', 'shift'); wire('f-area', 'area'); wire('f-resp', 'responsible'); wire('f-status', 'status'); wire('f-noresp', 'noResp');
    el('f-clear').onclick = () => { FILTERS = { q: '', day: '', shift: '', area: '', responsible: '', status: '', noResp: false }; renderBoard(); };
    renderBoardContent();
  }

  function renderBoardContent() {
    const dayIdx = dayIndexMap();
    const blocks = STATE.shifts.filter(shiftPassesLevel).map(s => {
      const attsAll = STATE.attendance.filter(a => a.shift_id === s.id);
      const atts = attsAll.filter(attPasses);
      const mtgs = meetingsForShift(s.id).filter(mtgPasses);
      if (contentFilterActive() && atts.length === 0 && mtgs.length === 0) return '';
      const resps = attsAll.filter(a => a.is_shift_responsible).map(a => personById(a.person_id)).filter(Boolean);
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
        : `<div class="block-empty">Sin personas${contentFilterActive() ? ' (con estos filtros)' : ' asignadas'}.</div>`;
      const mrows = mtgs.map(mt =>
        `<div class="mrow ${statusClass(mt.status)}" data-action="edit-meeting" data-id="${mt.id}">
          <span class="mtime">${esc(mt.start_time)}</span>
          <span class="mtitle">${esc(mt.title)}</span>
          <span class="mstatus ${statusClass(mt.status)}">${esc(mt.status)}</span>
        </div>`).join('');
      const meetingsSection = mrows ? `<div class="block-meetings"><div class="block-sub">Reuniones</div>${mrows}</div>` : '';
      return `<div class="block day-${dayIdx[s.date]}">
        <div class="block-head">
          <div class="block-day">${dayName(s.date)} <span class="block-date">· ${dateLabel(s.date)}</span></div>
          <div class="block-shift"><span class="shift-badge ${shiftClass(s.name)}">${esc(s.name)}</span><span class="block-time">${esc(s.start_time)}–${esc(s.end_time)}</span></div>
          <div class="block-resp">${respHtml}</div>
        </div>
        <div class="block-people">${peopleHtml}</div>
        ${meetingsSection}
        <div class="block-foot">
          <span class="block-count">Personas: <b>${atts.length}</b></span>
          <div class="block-actions">
            <button class="btn-soft" data-action="add-person" data-shift="${s.id}">+ Persona</button>
            <button class="btn-soft" data-action="add-meeting" data-shift="${s.id}">+ Reunión</button>
          </div>
        </div>
      </div>`;
    }).filter(Boolean).join('');
    el('board-content').innerHTML = blocks ? `<div class="board">${blocks}</div>` : `<div class="empty-state">No hay resultados para estos filtros.</div>`;
  }

  // ---------------- PEOPLE ----------------
  function renderPeople() {
    const rows = STATE.people.map(p => `
      <div class="list-row">
        <div class="grow clickable" data-action="view-person" data-id="${p.id}">
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
        <div class="grow clickable" data-action="view-area" data-id="${a.id}">
          <div class="rname">${esc(a.name)} ${a.active ? '<span class="badge on">activa</span>' : '<span class="badge off">inactiva</span>'}</div>
          <div class="rmeta">${esc(a.description || '')}${a.responsible ? ' · Ref: ' + esc(a.responsible) : ''}</div>
        </div>
        <button class="btn-line btn-sm" data-action="edit-area" data-id="${a.id}">Editar</button>
      </div>`).join('') || `<div class="empty-state">No hay áreas cargadas.</div>`;
    $('#view').innerHTML = `
      <div class="view-head"><h2>Áreas de la BCR</h2><button class="btn-primary" data-action="new-area">+ Nueva área</button></div>
      <div class="card">${rows}</div>`;
  }

  // ---------------- DETALLE POR PERSONA ----------------
  function renderPersonDetail(pid) {
    const p = personById(pid);
    if (!p) { $('#view').innerHTML = `<div class="empty-state">Persona no encontrada.</div>`; return; }
    const myAtt = STATE.attendance.filter(a => a.person_id === pid);
    const shiftsHtml = myAtt.length ? myAtt.map(a => {
      const s = shiftById(a.shift_id); if (!s) return '';
      const hrs = (a.start_time || a.end_time) ? ` <span class="rmeta">(ingreso ${esc(a.start_time || '?')} · salida ${esc(a.end_time || '?')})</span>` : '';
      return `<div class="d-row">${a.is_shift_responsible ? '<span class="pstar">★</span> ' : ''}${dayName(s.date)} ${dateLabel(s.date)} · ${esc(s.name)} ${esc(s.start_time)}–${esc(s.end_time)}${hrs}${a.event_role ? ' · ' + esc(a.event_role) : ''}${a.notes ? ' · <i>' + esc(a.notes) + '</i>' : ''}</div>`;
    }).join('') : '<div class="rmeta">Sin turnos asignados.</div>';
    const asResp = STATE.meetings.filter(mt => mt.responsible_person_id === pid);
    const asPart = STATE.meetings.filter(mt => (mt.participant_ids || []).includes(pid) && mt.responsible_person_id !== pid);
    const mline = (mt) => `<div class="d-row clickable" data-action="edit-meeting" data-id="${mt.id}">${dayName(mt.date)} ${esc(mt.start_time)} · ${esc(mt.title)} <span class="mstatus ${statusClass(mt.status)}">${esc(mt.status)}</span>${mt.organization ? ' · ' + esc(mt.organization) : ''}</div>`;
    $('#view').innerHTML = `
      <div class="view-head"><h2>${esc(p.full_name)}</h2><button class="btn-line" data-action="back-people">← Volver</button></div>
      <div class="card detail">
        <div class="d-meta">${p.area_id ? '<span class="badge area">' + esc(areaName(p.area_id)) + '</span> ' : ''}${p.role ? esc(p.role) + ' · ' : ''}${p.email ? esc(p.email) + ' · ' : ''}${p.phone ? esc(p.phone) : ''}${p.active ? '' : ' <span class="badge off">inactiva</span>'}</div>
        <div class="d-sec"><h4>Días y turnos asignados</h4>${shiftsHtml}</div>
        <div class="d-sec"><h4>Responsable de reuniones (${asResp.length})</h4>${asResp.length ? asResp.map(mline).join('') : '<div class="rmeta">Ninguna.</div>'}</div>
        <div class="d-sec"><h4>Participa en reuniones (${asPart.length})</h4>${asPart.length ? asPart.map(mline).join('') : '<div class="rmeta">Ninguna.</div>'}</div>
      </div>`;
  }

  // ---------------- DETALLE POR ÁREA ----------------
  function renderAreaDetail(aid) {
    const a = areaById(aid);
    if (!a) { $('#view').innerHTML = `<div class="empty-state">Área no encontrada.</div>`; return; }
    const people = STATE.people.filter(p => p.area_id === aid);
    const pids = new Set(people.map(p => p.id));
    const peopleHtml = people.length ? people.map(p => `<div class="d-row clickable" data-action="view-person" data-id="${p.id}">${esc(p.full_name)}${p.active ? '' : ' <span class="badge off">inactiva</span>'}</div>`).join('') : '<div class="rmeta">Sin personas.</div>';
    const covHtml = STATE.shifts.map(s => {
      const n = STATE.attendance.filter(x => x.shift_id === s.id && pids.has(x.person_id)).length;
      return `<div class="d-row ${n === 0 ? 'nocov' : ''}">${dayName(s.date)} ${dateLabel(s.date)} · ${esc(s.name)} → <b>${n}</b>${n === 0 ? ' <span class="no-resp">sin representantes del área</span>' : ''}</div>`;
    }).join('');
    const mtgs = STATE.meetings.filter(mt => mtgAreas(mt).includes(aid));
    const mtgHtml = mtgs.length ? mtgs.map(mt => `<div class="d-row clickable" data-action="edit-meeting" data-id="${mt.id}">${dayName(mt.date)} ${esc(mt.start_time)} · ${esc(mt.title)} <span class="mstatus ${statusClass(mt.status)}">${esc(mt.status)}</span></div>`).join('') : '<div class="rmeta">Ninguna.</div>';
    $('#view').innerHTML = `
      <div class="view-head"><h2>${esc(a.name)}</h2><button class="btn-line" data-action="back-areas">← Volver</button></div>
      <div class="card detail">
        ${a.description ? `<div class="d-meta">${esc(a.description)}</div>` : ''}
        <div class="d-sec"><h4>Personas del área (${people.length})</h4>${peopleHtml}</div>
        <div class="d-sec"><h4>Cobertura por turno</h4>${covHtml}</div>
        <div class="d-sec"><h4>Reuniones del área (${mtgs.length})</h4>${mtgHtml}</div>
      </div>`;
  }

  // ---------------- delegación de acciones ----------------
  $('#view').addEventListener('click', (e) => {
    const b = e.target.closest('[data-action]'); if (!b) return;
    const act = b.dataset.action;
    if (act === 'add-person') openAttendanceForm(Number(b.dataset.shift), null);
    else if (act === 'edit-att') openAttendanceForm(null, STATE.attendance.find(a => a.id === Number(b.dataset.id)));
    else if (act === 'add-meeting') openMeetingForm(Number(b.dataset.shift), null);
    else if (act === 'edit-meeting') openMeetingForm(null, STATE.meetings.find(x => x.id === Number(b.dataset.id)));
    else if (act === 'new-meeting') openMeetingForm(null, null);
    else if (act === 'new-person') openPersonForm(null);
    else if (act === 'edit-person') openPersonForm(personById(Number(b.dataset.id)));
    else if (act === 'new-area') openAreaForm(null);
    else if (act === 'edit-area') openAreaForm(areaById(Number(b.dataset.id)));
    else if (act === 'view-person') { detailPersonId = Number(b.dataset.id); goView('person-detail'); }
    else if (act === 'view-area') { detailAreaId = Number(b.dataset.id); goView('area-detail'); }
    else if (act === 'back-people') goView('people');
    else if (act === 'back-areas') goView('areas');
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

  // ---------------- AGENDA ----------------
  function renderAgenda() {
    const mtgs = [...STATE.meetings].sort((a, b) => a.date !== b.date ? a.date.localeCompare(b.date) : (a.start_time || '').localeCompare(b.start_time || ''));
    let html = '';
    if (!mtgs.length) html = `<div class="empty-state">No hay reuniones cargadas todavía.</div>`;
    else {
      const groups = new Map();
      mtgs.forEach(mt => { if (!groups.has(mt.date)) groups.set(mt.date, []); groups.get(mt.date).push(mt); });
      for (const [date, items] of groups) {
        html += `<div class="agenda-day"><div class="agenda-day-head">${dayName(date)} · ${dateLabel(date)}</div>`;
        items.forEach(mt => {
          const resp = personById(mt.responsible_person_id);
          const parts = (mt.participant_ids || []).map(personById).filter(Boolean).map(p => p.full_name);
          html += `<div class="agenda-item ${statusClass(mt.status)}" data-action="edit-meeting" data-id="${mt.id}">
            <div class="ai-time">${esc(mt.start_time)}${mt.end_time ? '–' + esc(mt.end_time) : ''}</div>
            <div class="ai-body">
              <div class="ai-title">${esc(mt.title)} <span class="mstatus ${statusClass(mt.status)}">${esc(mt.status)}</span></div>
              <div class="ai-meta">${mt.organization ? `<b>${esc(mt.organization)}</b> · ` : ''}${resp ? 'Resp: ' + esc(resp.full_name) : '<span style="color:var(--warn)">sin responsable</span>'}${parts.length ? ' · BCR: ' + esc(parts.join(', ')) : ''}${mt.location ? ' · ' + esc(mt.location) : ''}</div>
            </div>
          </div>`;
        });
        html += `</div>`;
      }
    }
    $('#view').innerHTML = `
      <div class="view-head"><h2>Agenda de reuniones</h2><button class="btn-primary" data-action="new-meeting">+ Nueva reunión</button></div>
      ${html}`;
  }

  // ---------------- meeting form ----------------
  function openMeetingForm(shiftId, mtg) {
    const editing = !!mtg;
    const shift = shiftId ? shiftById(shiftId) : null;
    const defDate = editing ? mtg.date : (shift ? shift.date : (STATE.event ? STATE.event.start_date : ''));
    const defStart = editing ? mtg.start_time : (shift ? shift.start_time : '');
    const respSel = editing ? mtg.responsible_person_id : null;
    const peopleOpts = STATE.people.filter(p => p.active || (editing && p.id === respSel))
      .map(p => `<option value="${p.id}" ${respSel === p.id ? 'selected' : ''}>${esc(p.full_name)}</option>`).join('');
    const partChecks = STATE.people.filter(p => p.active || (editing && (mtg.participant_ids || []).includes(p.id)))
      .map(p => `<label class="chk"><input type="checkbox" class="mf-part" value="${p.id}" ${editing && (mtg.participant_ids || []).includes(p.id) ? 'checked' : ''}> ${esc(p.full_name)}</label>`).join('');
    const statusOpts = MEETING_STATUSES.map(s => `<option ${editing && mtg.status === s ? 'selected' : ''}>${s}</option>`).join('');

    openModal(`
      <div class="modal-head"><h3>${editing ? 'Editar reunión' : 'Nueva reunión'}</h3><button class="modal-x" data-x>×</button></div>
      <label>Título / tema</label>
      <input id="mf-title" type="text" value="${editing ? esc(mtg.title) : ''}" placeholder="Ej: Reunión con Aapresid">
      <div class="grid-2">
        <div><label>Fecha</label><input id="mf-date" type="date" value="${defDate}"></div>
        <div><label>Estado</label><select id="mf-status">${statusOpts}</select></div>
      </div>
      <div class="grid-2">
        <div><label>Hora inicio</label><input id="mf-start" type="time" value="${defStart}"></div>
        <div><label>Hora fin (opcional)</label><input id="mf-end" type="time" value="${editing ? esc(mtg.end_time || '') : ''}"></div>
      </div>
      <label>Responsable de la reunión</label>
      <select id="mf-resp"><option value="">— Elegir —</option>${peopleOpts}</select>
      <div class="grid-2">
        <div><label>Empresa / institución</label><input id="mf-org" type="text" value="${editing ? esc(mtg.organization || '') : ''}"></div>
        <div><label>Lugar / stand</label><input id="mf-loc" type="text" value="${editing ? esc(mtg.location || '') : ''}"></div>
      </div>
      <label>Participantes externos (opcional)</label>
      <input id="mf-ext" type="text" value="${editing ? esc(mtg.external_participants || '') : ''}">
      <label>Participantes de la BCR</label>
      <div class="chk-grid">${partChecks || '<span class="rmeta">No hay personas cargadas.</span>'}</div>
      <label>Objetivo / descripción (opcional)</label>
      <textarea id="mf-desc" rows="2">${editing ? esc(mtg.description || '') : ''}</textarea>
      <label>Observaciones (opcional)</label>
      <textarea id="mf-notes" rows="2">${editing ? esc(mtg.notes || '') : ''}</textarea>
      <div id="mf-warn" class="form-warn hidden"></div>
      <div class="modal-foot">
        ${editing ? '<button class="btn-danger left" data-del>Eliminar</button>' : ''}
        <button class="btn-line" data-x>Cancelar</button>
        <button class="btn-primary" data-save>Guardar</button>
      </div>`);

    const draft = () => ({
      id: editing ? mtg.id : -1, title: el('mf-title').value,
      date: el('mf-date').value, start_time: el('mf-start').value, end_time: el('mf-end').value,
      responsible_person_id: el('mf-resp').value ? Number(el('mf-resp').value) : null,
      participant_ids: [...document.querySelectorAll('.mf-part:checked')].map(c => Number(c.value)),
    });
    const refreshWarnings = () => {
      const w = meetingWarnings(draft()); const box = el('mf-warn');
      if (w.length) { box.innerHTML = '⚠ ' + w.join('<br>⚠ '); box.classList.remove('hidden'); }
      else box.classList.add('hidden');
    };
    ['mf-date', 'mf-start', 'mf-end', 'mf-resp'].forEach(id => { const e = el(id); if (e) e.addEventListener('change', refreshWarnings); });
    document.querySelectorAll('.mf-part').forEach(c => c.addEventListener('change', refreshWarnings));
    refreshWarnings();

    el('modal-card').querySelectorAll('[data-x]').forEach(b => b.onclick = closeModal);
    el('modal-card').querySelector('[data-save]').onclick = async () => {
      const body = {
        title: el('mf-title').value.trim(), organization: el('mf-org').value, external_participants: el('mf-ext').value,
        date: el('mf-date').value, start_time: el('mf-start').value, end_time: el('mf-end').value, location: el('mf-loc').value,
        responsible_person_id: el('mf-resp').value ? Number(el('mf-resp').value) : null,
        description: el('mf-desc').value, notes: el('mf-notes').value, status: el('mf-status').value,
        participant_ids: [...document.querySelectorAll('.mf-part:checked')].map(c => Number(c.value)),
      };
      if (!body.title) { toast('Falta el título', 'err'); return; }
      if (!body.date || !body.start_time) { toast('Faltan fecha y hora de inicio', 'err'); return; }
      if (!body.responsible_person_id) { toast('Elegí un responsable', 'err'); return; }
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

  // ---------------- init ----------------
  (async function init() {
    if (getToken()) { try { await boot(); return; } catch (e) { clearToken(); } }
    showLogin();
  })();
})();
