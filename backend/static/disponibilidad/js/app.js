/* Relevamiento de Disponibilidad.
   Público (sin login): carga su nombre + marca franjas (L-V, bloques de 1h 8-20).
   Admin (contraseña): ve el mapa de calor y las coincidencias. Los que completan
   NO ven los resultados. */
(function () {
  'use strict';

  const API = '/api/disponibilidad';
  const ADMIN_KEY = 'disp_admin';
  const DAYS = [
    { k: 'mon', label: 'Lunes', short: 'Lun' },
    { k: 'tue', label: 'Martes', short: 'Mar' },
    { k: 'wed', label: 'Miércoles', short: 'Mié' },
    { k: 'thu', label: 'Jueves', short: 'Jue' },
    { k: 'fri', label: 'Viernes', short: 'Vie' },
  ];
  const HOURS = [];
  for (let h = 8; h < 20; h++) HOURS.push(h);   // 8-9 ... 19-20

  const slotKey = (day, hour) => day + '-' + hour;
  const hourLabel = (h) => h + '–' + (h + 1);          // rango completo (tooltips/resultados)
  const hourShort = (h) => String(h).padStart(2, '0'); // etiqueta compacta en la grilla
  const el = (id) => document.getElementById(id);

  const selected = new Set();     // franjas de la persona actual
  let RESPONSES = [];             // solo se llena en modo admin
  let ADMIN = localStorage.getItem(ADMIN_KEY) || '';

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function toast(msg, type) {
    const t = el('toast'); t.textContent = msg; t.className = 'toast show ' + (type || '');
    setTimeout(() => { t.className = 'toast'; }, 2800);
  }

  async function api(path, opts, admin) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (admin && ADMIN) opts.headers.Authorization = 'Bearer ' + ADMIN;
    const res = await fetch(API + path, opts);
    if (admin && res.status === 401) { lockAdmin(); const e = new Error('401'); e.detail = 'Sesión de admin vencida'; throw e; }
    let data = null; try { data = await res.json(); } catch (e) {}
    if (!res.ok) { const err = new Error((data && data.detail) || 'Error'); err.detail = data && data.detail; throw err; }
    return data;
  }

  // ================= GRILLA DE CARGA (público) =================
  function buildGrid() {
    let html = '<div class="dcorner"></div>';
    DAYS.forEach(d => { html += `<div class="dhead" data-day="${d.k}" title="Marcar/limpiar toda la columna">${d.short}</div>`; });
    HOURS.forEach(h => {
      html += `<div class="hlabel" data-hour="${h}" title="Marcar/limpiar toda la fila (${hourLabel(h)} hs)">${hourShort(h)}</div>`;
      DAYS.forEach(d => {
        html += `<button type="button" class="cell" data-slot="${slotKey(d.k, h)}" aria-label="${d.label} ${hourLabel(h)}"></button>`;
      });
    });
    el('grid').innerHTML = html;
  }
  function refreshGridSelection() {
    el('grid').querySelectorAll('.cell').forEach(c => c.classList.toggle('on', selected.has(c.dataset.slot)));
    const n = selected.size;
    el('sel-count').textContent = n ? `${n} franja${n === 1 ? '' : 's'} marcada${n === 1 ? '' : 's'}` : 'Sin franjas marcadas';
  }
  function toggleColumn(day) {
    const keys = HOURS.map(h => slotKey(day, h));
    const allOn = keys.every(k => selected.has(k));
    keys.forEach(k => allOn ? selected.delete(k) : selected.add(k));
    refreshGridSelection();
  }
  function toggleRow(hour) {
    const keys = DAYS.map(d => slotKey(d.k, hour));
    const allOn = keys.every(k => selected.has(k));
    keys.forEach(k => allOn ? selected.delete(k) : selected.add(k));
    refreshGridSelection();
  }
  el('grid').addEventListener('click', (e) => {
    const cell = e.target.closest('.cell');
    if (cell) { selected.has(cell.dataset.slot) ? selected.delete(cell.dataset.slot) : selected.add(cell.dataset.slot); refreshGridSelection(); return; }
    const dh = e.target.closest('.dhead'); if (dh) { toggleColumn(dh.dataset.day); return; }
    const hl = e.target.closest('.hlabel'); if (hl) { toggleRow(Number(hl.dataset.hour)); return; }
  });

  // precargar la propia carga (por nombre) para poder editarla
  async function loadOwnIfExists() {
    const name = el('name').value.trim();
    const note = el('edit-note');
    if (!name) { note.classList.add('hidden'); return; }
    try {
      const data = await api('/mine?name=' + encodeURIComponent(name));
      const existing = data && data.response;
      if (existing) {
        selected.clear();
        (existing.slots || []).forEach(s => selected.add(s));
        refreshGridSelection();
        note.textContent = `Ya cargaste antes: estás editando la disponibilidad de ${existing.name}. Guardá para actualizar.`;
        note.classList.remove('hidden');
      } else {
        note.classList.add('hidden');
      }
    } catch (e) { /* silencioso */ }
  }
  el('name').addEventListener('change', loadOwnIfExists);

  // guardar (público)
  el('btn-save').addEventListener('click', async () => {
    const name = el('name').value.trim();
    if (!name) { toast('Poné tu nombre', 'err'); el('name').focus(); return; }
    const btn = el('btn-save'); btn.disabled = true; const prev = btn.textContent; btn.textContent = 'Guardando…';
    try {
      await api('/responses', { method: 'POST', body: JSON.stringify({ name, slots: [...selected] }) });
      toast('¡Guardado! Gracias.', 'ok');
      await loadOwnIfExists();
      if (ADMIN) loadState().catch(() => {});
    } catch (err) { toast(err.detail || 'No se pudo guardar', 'err'); }
    finally { btn.disabled = false; btn.textContent = prev; }
  });

  // ================= ADMIN (resultados) =================
  function showOverlay() { el('admin-err').textContent = ''; el('admin-pass').value = ''; el('admin-ov').classList.remove('hidden'); el('admin-pass').focus(); }
  function hideOverlay() { el('admin-ov').classList.add('hidden'); }
  function showResults() { el('results').classList.remove('hidden'); el('btn-admin').classList.add('hidden'); }
  function lockAdmin() {
    ADMIN = ''; localStorage.removeItem(ADMIN_KEY); RESPONSES = [];
    el('results').classList.add('hidden'); el('btn-admin').classList.remove('hidden');
  }

  el('btn-admin').addEventListener('click', () => {
    if (ADMIN) { showResults(); loadState().catch(() => {}); }
    else showOverlay();
  });
  el('admin-cancel').addEventListener('click', hideOverlay);
  el('admin-ov').addEventListener('mousedown', (e) => { if (e.target === el('admin-ov')) hideOverlay(); });
  el('btn-lock').addEventListener('click', lockAdmin);
  el('admin-card').addEventListener('submit', async (e) => {
    e.preventDefault();
    const pass = el('admin-pass').value;
    el('admin-err').textContent = '';
    try {
      await api('/admin/login', { method: 'POST', body: JSON.stringify({ password: pass }) });
      ADMIN = pass; localStorage.setItem(ADMIN_KEY, pass);
      hideOverlay(); showResults(); await loadState(); startPolling();
    } catch (err) { el('admin-err').textContent = err.detail || 'Contraseña incorrecta'; }
  });

  function countsBySlot() {
    const counts = {};
    RESPONSES.forEach(r => (r.slots || []).forEach(s => { (counts[s] = counts[s] || []).push(r.name); }));
    return counts;
  }
  function renderResults() {
    const total = RESPONSES.length;
    el('resp-total').textContent = total;
    el('people-count').textContent = total ? `· ${total} persona${total === 1 ? '' : 's'}` : '';

    const counts = countsBySlot();
    let max = 0; Object.values(counts).forEach(a => { if (a.length > max) max = a.length; });

    let html = '<div class="dcorner"></div>';
    DAYS.forEach(d => { html += `<div class="dhead" style="cursor:default">${d.short}</div>`; });
    HOURS.forEach(hr => {
      html += `<div class="hlabel" style="cursor:default" title="${hourLabel(hr)} hs">${hourShort(hr)}</div>`;
      DAYS.forEach(d => {
        const k = slotKey(d.k, hr);
        const c = (counts[k] || []).length;
        const ratio = max ? c / max : 0;
        const bg = c === 0 ? '#fff' : `rgba(22,163,74,${(0.15 + 0.85 * ratio).toFixed(3)})`;
        const col = ratio > 0.55 ? '#fff' : '#0f172a';
        html += `<div class="rcell ${c === 0 ? 'zero' : ''}" data-slot="${k}" style="background:${bg};color:${col}" title="${esc(d.label)} ${hourLabel(hr)}">${c || '·'}</div>`;
      });
    });
    el('heat').innerHTML = html;

    const ranked = Object.keys(counts).map(k => ({ k, c: counts[k].length }))
      .filter(x => x.c > 0).sort((a, b) => b.c - a.c || a.k.localeCompare(b.k)).slice(0, 6);
    el('best').innerHTML = ranked.length
      ? ranked.map((x, i) => {
          const [day, hr] = x.k.split('-'); const d = DAYS.find(z => z.k === day);
          return `<div class="best-item"><span class="best-rank">${i + 1}</span><span class="best-when">${d ? d.label : day} · ${hourLabel(Number(hr))} hs</span><span class="best-count">${x.c} disponible${x.c === 1 ? '' : 's'}</span></div>`;
        }).join('')
      : '<div class="best-empty">Todavía no hay respuestas.</div>';

    el('people').innerHTML = RESPONSES.length
      ? RESPONSES.map(r => {
          const n = (r.slots || []).length;
          return `<span class="person-chip">${esc(r.name)} <span class="pcount">${n} franja${n === 1 ? '' : 's'}</span> <button class="pdel" data-del="${r.id}" title="Eliminar">×</button></span>`;
        }).join('')
      : '<div class="people-empty">Nadie cargó su disponibilidad todavía.</div>';
  }

  el('heat').addEventListener('click', (e) => {
    const cell = e.target.closest('.rcell'); if (!cell) return;
    const names = countsBySlot()[cell.dataset.slot] || [];
    const [day, hr] = cell.dataset.slot.split('-'); const d = DAYS.find(z => z.k === day);
    const when = `${d ? d.label : day} ${hourLabel(Number(hr))} hs`;
    toast(names.length ? `${when}: ${names.join(', ')}` : `${when}: nadie disponible`, names.length ? 'ok' : '');
  });
  el('people').addEventListener('click', async (e) => {
    const b = e.target.closest('.pdel'); if (!b) return;
    const r = RESPONSES.find(x => x.id === Number(b.dataset.del)); if (!r) return;
    if (!confirm(`¿Eliminar la disponibilidad de ${r.name}?`)) return;
    try { await api('/responses/' + r.id, { method: 'DELETE' }, true); await loadState(); toast('Eliminada', 'ok'); }
    catch (err) { toast(err.detail || 'Error', 'err'); }
  });

  async function loadState() {
    if (!ADMIN) return;
    const data = await api('/state', {}, true);
    RESPONSES = data.responses || [];
    renderResults();
  }

  let pollingOn = false;
  function startPolling() {
    if (pollingOn) return; pollingOn = true;
    setInterval(() => {
      if (!ADMIN || document.hidden) return;
      const a = document.activeElement; if (a && a.id === 'name') return;
      loadState().catch(() => {});
    }, 20000);
  }

  // ================= init =================
  (async function init() {
    buildGrid();
    refreshGridSelection();
    if (ADMIN) {
      try { await loadState(); showResults(); startPolling(); }
      catch (e) { lockAdmin(); }
    }
  })();
})();
