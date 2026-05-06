import { state, addEfemeride, updateEfemeride, deleteEfemeride } from '../state.js';

const MES_NAMES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
];

export function renderEfemeridesModal(container) {
    // Estado local del modal: mes seleccionado (default = mes actual)
    if (!container.dataset.selectedMonth) {
        container.dataset.selectedMonth = String(new Date().getMonth() + 1);
    }

    function rerender() {
        container.innerHTML = '';
        build(container);
        if (window.lucide) window.lucide.createIcons();
    }

    function build(root) {
        const selectedMonth = parseInt(root.dataset.selectedMonth, 10);

        const filtered = state.efemerides
            .filter(e => e.mes === selectedMonth)
            .sort((a, b) => a.dia - b.dia);

        // Header
        const header = document.createElement('div');
        header.className = 'ef-modal-header';
        header.innerHTML = `
            <h2>Efemérides y Aniversarios</h2>
            <button id="ef-close" style="background: none; border: none; cursor: pointer; color: var(--text-muted);">
                <i data-lucide="x"></i>
            </button>
        `;
        root.appendChild(header);

        // Toolbar (selector de mes + botón nuevo)
        const toolbar = document.createElement('div');
        toolbar.className = 'ef-modal-toolbar';
        toolbar.innerHTML = `
            <label style="font-size: 0.85rem; color: var(--text-muted);">Mes:</label>
            <select id="ef-month-select">
                ${MES_NAMES.slice(1).map((name, idx) => `
                    <option value="${idx + 1}" ${idx + 1 === selectedMonth ? 'selected' : ''}>${name}</option>
                `).join('')}
            </select>
            <div class="ef-spacer"></div>
            <button id="ef-new" class="btn-primary" style="padding: 0.4rem 0.85rem; font-size: 0.85rem;">
                <i data-lucide="plus" style="width: 16px; height: 16px;"></i>
                Nueva
            </button>
        `;
        root.appendChild(toolbar);

        // Lista
        const list = document.createElement('div');
        list.className = 'ef-modal-list';

        if (filtered.length === 0) {
            list.innerHTML = `<div class="ef-empty">No hay efemérides en ${MES_NAMES[selectedMonth]}.</div>`;
        } else {
            filtered.forEach(e => {
                const row = document.createElement('div');
                row.className = 'ef-row';
                row.dataset.id = e.id;
                row.innerHTML = `
                    <input class="ef-day" type="number" min="1" max="31" value="${e.dia}" data-field="dia" />
                    <select data-field="tipo">
                        <option value="Efeméride" ${e.tipo === 'Efeméride' ? 'selected' : ''}>Efeméride</option>
                        <option value="Aniversario" ${e.tipo === 'Aniversario' ? 'selected' : ''}>Aniversario</option>
                    </select>
                    <input type="text" value="${(e.motivo || '').replace(/"/g, '&quot;')}" data-field="motivo" />
                    <div class="ef-actions">
                        <button class="ef-delete" title="Eliminar">
                            <i data-lucide="trash-2" style="width: 16px; height: 16px;"></i>
                        </button>
                    </div>
                `;

                // Auto-save al editar (con debounce simple en blur)
                row.querySelectorAll('[data-field]').forEach(inp => {
                    inp.addEventListener('change', () => {
                        const updates = {};
                        const f = inp.dataset.field;
                        let v = inp.value;
                        if (f === 'dia') {
                            v = parseInt(v, 10);
                            if (isNaN(v) || v < 1 || v > 31) {
                                inp.value = e.dia;
                                return;
                            }
                        }
                        if (f === 'motivo' && !v.trim()) {
                            inp.value = e.motivo;
                            return;
                        }
                        updates[f] = v;
                        updateEfemeride(e.id, updates);
                    });
                });

                row.querySelector('.ef-delete').onclick = () => {
                    if (confirm(`¿Eliminar "${e.motivo}"?`)) {
                        deleteEfemeride(e.id);
                    }
                };

                list.appendChild(row);
            });
        }

        root.appendChild(list);

        // Wire eventos
        root.querySelector('#ef-close').onclick = () => {
            if (window.closeEfemeridesSheet) window.closeEfemeridesSheet();
        };

        root.querySelector('#ef-month-select').onchange = (ev) => {
            root.dataset.selectedMonth = ev.target.value;
            rerender();
        };

        root.querySelector('#ef-new').onclick = async () => {
            await addEfemeride({
                mes: selectedMonth,
                dia: 1,
                tipo: 'Efeméride',
                motivo: 'Nueva efeméride'
            });
            rerender();
        };
    }

    rerender();

    // Cuando cambia el state global (alta/edición/baja desde otro lado), re-render
    // pero sin perder el mes seleccionado (lo guardamos en dataset).
    // El subscribe global ya re-renderiza la vista activa, pero el modal no se re-monta
    // automáticamente. Hacemos un refresco manual periódico minimal: escuchamos cambios
    // disparando rerender solo si el modal sigue abierto.
    const subscribed = () => {
        if (!container.closest('.sheet-overlay').classList.contains('hidden')) {
            // Mantener foco si estaba editando un input
            const active = document.activeElement;
            const activeId = active && active.closest('.ef-row') ? active.closest('.ef-row').dataset.id : null;
            const activeField = active && active.dataset ? active.dataset.field : null;
            rerender();
            if (activeId && activeField) {
                const r = container.querySelector(`.ef-row[data-id="${activeId}"]`);
                if (r) {
                    const inp = r.querySelector(`[data-field="${activeField}"]`);
                    if (inp) inp.focus();
                }
            }
        }
    };
    // Guardamos el handler en el container para no acumular suscripciones cada vez que abre
    if (container._efSubscribed) {
        // Ya hay uno, no re-suscribimos
    } else {
        container._efSubscribed = true;
        import('../state.js').then(({ subscribe }) => subscribe(subscribed));
    }
}
