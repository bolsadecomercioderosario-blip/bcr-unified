import { loadArchived, restoreActivity } from '../state.js';
import { isSecretaria } from '../role.js';

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
// archived_at es ISO UTC (ej. 2026-07-25T13:05:22). Mostramos fecha + hora local prolija.
function fmtArchivedAt(iso) {
    if (!iso) return '';
    const dt = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    if (isNaN(dt)) return iso;
    const dd = String(dt.getDate()).padStart(2, '0');
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const hh = String(dt.getHours()).padStart(2, '0');
    const mi = String(dt.getMinutes()).padStart(2, '0');
    return `${dd}/${mm}/${dt.getFullYear()} ${hh}:${mi}`;
}

export async function renderArchivedModal(container) {
    const isSec = isSecretaria();

    container.innerHTML = `
        <div class="ef-modal-header">
            <h2>Archivados</h2>
            <button id="arch-close" style="background: none; border: none; cursor: pointer; color: var(--text-muted);">
                <i data-lucide="x"></i>
            </button>
        </div>
        <p style="margin: 0 0 1rem; font-size: 0.85rem; color: var(--text-muted);">
            Actividades eliminadas. Se guardan como registro y podés restaurarlas
            (vuelven a la agenda y su carpeta de Drive sale de la papelera).
        </p>
        <div id="arch-list" style="display: flex; flex-direction: column; gap: 0.5rem;">
            <div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">Cargando…</div>
        </div>
    `;
    if (window.lucide) window.lucide.createIcons();
    container.querySelector('#arch-close').onclick = () => window.closeArchivedSheet();

    const all = await loadArchived();
    // Cada rol ve lo que puede archivar/restaurar: Secretaría las suyas,
    // Comunicación el resto (coincide con quién puede eliminarlas).
    const items = all
        .filter(a => !a.is_custom)
        .filter(a => isSec ? a.origen === 'secretaria' : a.origen !== 'secretaria')
        .sort((a, b) => (b.archived_at || '').localeCompare(a.archived_at || ''));

    const listEl = container.querySelector('#arch-list');
    if (!items.length) {
        listEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">No hay actividades archivadas.</div>`;
        return;
    }

    listEl.innerHTML = items.map(a => `
        <div class="arch-row" data-id="${esc(a.id)}" style="display: flex; align-items: center; gap: 0.75rem; padding: 0.65rem 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: white;">
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 600; display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                    ${esc(a.title)}
                    ${a.origen === 'secretaria' ? '<span style="font-weight: 600; font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.03em; color: #0742ab; background: #dbeafe; padding: 0.1rem 0.4rem; border-radius: 999px;">Secretaría</span>' : ''}
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 0.15rem;">
                    ${fmtDate(a.date)}${a.time && a.time !== 'Sin horario' && a.time !== 'A definir' ? ' · ' + esc(a.time) : ''}
                    ${a.archived_at ? ` · archivada el ${fmtArchivedAt(a.archived_at)}` : ''}
                </div>
            </div>
            <button class="btn-restore" data-id="${esc(a.id)}" style="display: inline-flex; align-items: center; gap: 0.35rem; background: white; border: 1px solid var(--border); color: var(--primary); border-radius: 0.5rem; padding: 0.4rem 0.75rem; font-weight: 600; font-size: 0.85rem; cursor: pointer; white-space: nowrap;">
                <i data-lucide="rotate-ccw" style="width: 15px; height: 15px;"></i> Restaurar
            </button>
        </div>
    `).join('');
    if (window.lucide) window.lucide.createIcons();

    listEl.querySelectorAll('.btn-restore').forEach(btn => {
        btn.onclick = async () => {
            const id = btn.dataset.id;
            btn.disabled = true;
            btn.textContent = 'Restaurando…';
            const ok = await restoreActivity(id);
            if (ok) {
                const row = listEl.querySelector(`.arch-row[data-id="${id}"]`);
                if (row) row.remove();
                if (!listEl.querySelector('.arch-row')) {
                    listEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem; padding: 1rem 0;">No hay actividades archivadas.</div>`;
                }
            } else {
                btn.disabled = false;
                btn.innerHTML = '<i data-lucide="rotate-ccw" style="width: 15px; height: 15px;"></i> Restaurar';
                if (window.lucide) window.lucide.createIcons();
            }
        };
    });
}
