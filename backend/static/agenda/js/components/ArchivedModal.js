import { loadArchived, restoreActivity, loadHidden, unhideActivity } from '../state.js';
import { isSecretaria, isComunicacion } from '../role.js';
import { ownerLabel } from '../constants.js';

const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const WEEKDAYS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
function fmtDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.split('-').map(Number);
    if (!y || !m || !d) return iso;
    const dt = new Date(y, m - 1, d);
    return `${WEEKDAYS[dt.getDay()]} ${d}/${m}`;
}
// Los timestamps son ISO UTC (ej. 2026-07-25T13:05:22). Mostramos fecha + hora local.
function fmtStamp(iso) {
    if (!iso) return '';
    const dt = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    if (isNaN(dt)) return iso;
    const dd = String(dt.getDate()).padStart(2, '0');
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const hh = String(dt.getHours()).padStart(2, '0');
    const mi = String(dt.getMinutes()).padStart(2, '0');
    return `${dd}/${mm}/${dt.getFullYear()} ${hh}:${mi}`;
}

function ownerBadge(a) {
    if (a.origen === 'secretaria') {
        return '<span style="font-weight: 600; font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.03em; color: #0742ab; background: #dbeafe; padding: 0.1rem 0.4rem; border-radius: 999px;">Secretaría</span>';
    }
    if (a.origen === 'area') {
        return `<span style="font-weight: 600; font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.03em; color: #0742ab; background: #dbeafe; padding: 0.1rem 0.4rem; border-radius: 999px;">${esc(ownerLabel(a))}</span>`;
    }
    return '';
}

// Dibuja una fila (archivada u oculta). `action` define el botón de la derecha.
function rowHtml(a, stampLabel, stampIso, action) {
    return `
        <div class="arch-row" data-id="${esc(a.id)}" style="display: flex; align-items: center; gap: 0.75rem; padding: 0.65rem 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: white;">
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 600; display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                    ${esc(a.title)}
                    ${ownerBadge(a)}
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 0.15rem;">
                    ${fmtDate(a.date)}${a.time && a.time !== 'Sin horario' && a.time !== 'A definir' ? ' · ' + esc(a.time) : ''}
                    ${stampIso ? ` · ${stampLabel} ${fmtStamp(stampIso)}` : ''}
                </div>
            </div>
            <button class="${action.cls}" data-id="${esc(a.id)}" style="display: inline-flex; align-items: center; gap: 0.35rem; background: white; border: 1px solid var(--border); color: var(--primary); border-radius: 0.5rem; padding: 0.4rem 0.75rem; font-weight: 600; font-size: 0.85rem; cursor: pointer; white-space: nowrap;">
                <i data-lucide="${action.icon}" style="width: 15px; height: 15px;"></i> ${action.label}
            </button>
        </div>
    `;
}

// Pinta una lista dentro de `listEl`, ya filtrada/ordenada, con su acción.
function renderInto(listEl, items, { stampLabel, stampKey, emptyMsg, action, onAction }) {
    if (!items.length) {
        listEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">${emptyMsg}</div>`;
        return;
    }
    listEl.innerHTML = items.map(a => rowHtml(a, stampLabel, a[stampKey], action)).join('');
    if (window.lucide) window.lucide.createIcons();

    listEl.querySelectorAll(`.${action.cls}`).forEach(btn => {
        btn.onclick = async () => {
            const id = btn.dataset.id;
            btn.disabled = true;
            btn.textContent = action.busyLabel;
            const ok = await onAction(id);
            if (ok) {
                const row = listEl.querySelector(`.arch-row[data-id="${id}"]`);
                if (row) row.remove();
                if (!listEl.querySelector('.arch-row')) {
                    listEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">${emptyMsg}</div>`;
                }
            } else {
                btn.disabled = false;
                btn.innerHTML = `<i data-lucide="${action.icon}" style="width: 15px; height: 15px;"></i> ${action.label}`;
                if (window.lucide) window.lucide.createIcons();
            }
        };
    });
}

export async function renderArchivedModal(container) {
    const isSec = isSecretaria();
    const isCom = isComunicacion();

    container.innerHTML = `
        <div class="ef-modal-header">
            <h2>Archivados</h2>
            <button id="arch-close" style="background: none; border: none; cursor: pointer; color: var(--text-muted);">
                <i data-lucide="x"></i>
            </button>
        </div>
        ${isCom ? `
        <div id="arch-tabs" style="display: flex; gap: 0.4rem; margin-bottom: 0.9rem;">
            <button class="arch-tab" data-tab="arch" style="flex: 1; padding: 0.5rem; border: 1px solid var(--border); border-radius: 0.5rem; background: var(--primary); color: white; font-weight: 600; font-size: 0.85rem; cursor: pointer;">Archivadas</button>
            <button class="arch-tab" data-tab="hidden" style="flex: 1; padding: 0.5rem; border: 1px solid var(--border); border-radius: 0.5rem; background: white; color: var(--text-muted); font-weight: 600; font-size: 0.85rem; cursor: pointer;">Ocultas</button>
        </div>` : ''}
        <p id="arch-help" style="margin: 0 0 1rem; font-size: 0.85rem; color: var(--text-muted);"></p>
        <div id="arch-list" style="display: flex; flex-direction: column; gap: 0.5rem;">
            <div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">Cargando…</div>
        </div>
    `;
    if (window.lucide) window.lucide.createIcons();
    container.querySelector('#arch-close').onclick = () => window.closeArchivedSheet();

    const listEl = container.querySelector('#arch-list');
    const helpEl = container.querySelector('#arch-help');

    // --- Pestaña Archivadas (comportamiento de siempre) -------------------------
    async function showArchived() {
        helpEl.textContent = 'Actividades eliminadas. Se guardan como registro y podés restaurarlas (vuelven a la agenda y su carpeta de Drive sale de la papelera).';
        listEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">Cargando…</div>`;
        const all = await loadArchived();
        // Cada rol ve lo que puede archivar/restaurar: Secretaría las suyas,
        // Comunicación el resto (coincide con quién puede eliminarlas).
        const items = all
            .filter(a => !a.is_custom)
            .filter(a => isSec ? a.origen === 'secretaria' : a.origen !== 'secretaria')
            .sort((a, b) => (b.archived_at || '').localeCompare(a.archived_at || ''));
        renderInto(listEl, items, {
            stampLabel: 'archivada el', stampKey: 'archived_at',
            emptyMsg: 'No hay actividades archivadas.',
            action: { cls: 'btn-restore', icon: 'rotate-ccw', label: 'Restaurar', busyLabel: 'Restaurando…' },
            onAction: restoreActivity,
        });
    }

    // --- Pestaña Ocultas (sólo Comunicación) ------------------------------------
    async function showHidden() {
        helpEl.textContent = 'Actividades que sacaste de tu vista (de Secretaría o de las áreas). NO están eliminadas: siguen vivas para el resto y en la agenda pública. Volvé a mostrarlas cuando quieras.';
        listEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">Cargando…</div>`;
        const all = await loadHidden();
        const items = all
            .filter(a => !a.is_custom)
            .sort((a, b) => (b.oculta_comunicacion_at || '').localeCompare(a.oculta_comunicacion_at || ''));
        renderInto(listEl, items, {
            stampLabel: 'ocultada el', stampKey: 'oculta_comunicacion_at',
            emptyMsg: 'No hay actividades ocultas.',
            action: { cls: 'btn-unhide', icon: 'eye', label: 'Mostrar', busyLabel: 'Mostrando…' },
            onAction: unhideActivity,
        });
    }

    // Tabs (si Comunicación): alternan la lista y resaltan el botón activo.
    if (isCom) {
        const tabs = container.querySelectorAll('.arch-tab');
        const setActive = (name) => {
            tabs.forEach(t => {
                const on = t.dataset.tab === name;
                t.style.background = on ? 'var(--primary)' : 'white';
                t.style.color = on ? 'white' : 'var(--text-muted)';
            });
        };
        tabs.forEach(t => {
            t.onclick = () => {
                setActive(t.dataset.tab);
                if (t.dataset.tab === 'hidden') showHidden(); else showArchived();
            };
        });
    }

    // Arranca en Archivadas (comportamiento previo intacto).
    showArchived();
}
