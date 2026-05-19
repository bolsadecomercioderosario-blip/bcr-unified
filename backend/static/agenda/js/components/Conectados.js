import { state, updateActivity, addActivity, deleteActivity } from '../state.js';
import { generateNewsletterBlock } from '../utils/ai-engine.js';
import { generateNewsletterHTML } from '../utils/NewsletterGenerator.js';

// --- Helpers de fecha (semana de newsletter = sábado a viernes) ---
function isCurrentNewsletterWeek(dateStr) {
    if (!dateStr) return false;
    const actDate = new Date(dateStr + "T00:00:00");
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const day = today.getDay();
    // Sábado=6: arranca hoy. Otro día: retrocede al último sábado.
    const diff = day === 6 ? 0 : -(day + 1);

    const saturday = new Date(today);
    saturday.setDate(today.getDate() + diff);

    const nextFriday = new Date(saturday);
    nextFriday.setDate(saturday.getDate() + 6);
    nextFriday.setHours(23, 59, 59, 999);

    return actDate >= saturday && actDate <= nextFriday;
}

/**
 * Decide el tipo de bloque a partir del activity:
 *   - block_type === 'fixed'    → bloque fijo (persistente)
 *   - block_type === 'variable' → bloque variable (sólo esta semana, pero
 *                                 el is_custom lo mantiene si volvés a
 *                                 abrir Conectados antes de borrarlo)
 *   - sin block_type            → bloque de actividad (la actividad real)
 */
function blockKind(act) {
    if (act.block_type === 'fixed') return 'fixed';
    if (act.block_type === 'variable') return 'variable';
    return 'activity';
}

const BLOCK_BADGE = {
    fixed:    { icon: '📌', label: 'Fijo',      color: '#7c3aed', bg: '#ede9fe' },
    variable: { icon: '🔄', label: 'Variable',  color: '#0891b2', bg: '#cffafe' },
    activity: { icon: '📅', label: 'Actividad', color: '#0742ab', bg: '#dbeafe' },
};

// Tomamos las primeras N palabras como vista previa del cuerpo.
function previewSnippet(text, maxWords = 22) {
    const clean = (text || '').trim().replace(/\s+/g, ' ');
    if (!clean) return '';
    const words = clean.split(' ');
    if (words.length <= maxWords) return clean;
    return words.slice(0, maxWords).join(' ') + '…';
}

// Texto que aparece como cuerpo del bloque: en bloques de actividad, el
// LinkedIn copy de la actividad pisa al conectados_text si está cargado.
function blockBodyText(act) {
    if (blockKind(act) === 'activity') {
        return (act.copy_linkedin && act.copy_linkedin.trim())
            || act.conectados_text
            || act.description
            || '';
    }
    return act.conectados_text || act.copy_linkedin || act.description || '';
}

// =================================================================
// MAIN RENDER
// =================================================================
export function renderConectados(container) {
    const conectadosActivities = state.activities
        .filter(a => {
            if (!a.channels.includes('Conectados')) return false;
            // Los bloques fijos persisten siempre, sin importar la fecha.
            if (a.block_type === 'fixed') return true;
            // Compat: si vino un legacy con observations='FIXED_BLOCK' (no
            // debería pasar tras la migración, pero por las dudas)
            if (a.is_custom && a.observations === 'FIXED_BLOCK') return true;
            return isCurrentNewsletterWeek(a.date);
        })
        .sort((a, b) => (a.order_index || 0) - (b.order_index || 0));

    const wrapper = document.createElement('div');
    wrapper.className = 'content-wrapper';

    const header = document.createElement('div');
    header.className = 'conectados-header-bar';
    header.innerHTML = `
        <h2 style="font-weight: 700; margin: 0;">Newsletter Conectados</h2>
        <div class="conectados-header-actions">
            <button id="btn-gen-newsletter" class="btn-primary" style="width: auto; padding: 0.5rem 1rem; background: #0742ab;">
                <i data-lucide="mail"></i> Generar Newsletter
            </button>
            <button id="btn-add-fixed-block" class="btn-primary" style="width: auto; padding: 0.5rem 1rem; background: #7c3aed;">
                <i data-lucide="pin"></i> Bloque Fijo
            </button>
            <button id="btn-add-var-block" class="btn-primary" style="width: auto; padding: 0.5rem 1rem; background: #0891b2;">
                <i data-lucide="plus-circle"></i> Bloque Variable
            </button>
        </div>
    `;
    wrapper.appendChild(header);

    if (conectadosActivities.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'text-align: center; padding: 4rem; color: var(--text-muted);';
        empty.textContent = 'No hay bloques para esta semana. Agregá uno con los botones de arriba.';
        wrapper.appendChild(empty);
    }

    const listContainer = document.createElement('div');
    listContainer.id = 'conectados-sortable-list';
    listContainer.className = 'conectados-grid';

    conectadosActivities.forEach(act => {
        const kind = blockKind(act);
        const badge = BLOCK_BADGE[kind];
        const bodyText = blockBodyText(act);
        const snippet = previewSnippet(bodyText);

        const item = document.createElement('div');
        item.className = `conectados-item kind-${kind}`;
        item.dataset.id = act.id;
        item.dataset.kind = kind;

        item.innerHTML = `
            <div class="conectados-mobile-row">
                <div class="conectados-mobile-handle">
                    <i data-lucide="grip-vertical"></i>
                </div>
                <div class="conectados-mobile-title">${(act.title || '').replace(/</g, '&lt;') || '<span style="color: var(--text-muted); font-weight: 400;">(sin título)</span>'}</div>
                <i class="conectados-mobile-chevron" data-lucide="chevron-down"></i>
            </div>
            <div class="drag-handle">
                <i data-lucide="grip-vertical" style="width: 16px;"></i>
            </div>
            <div class="conectados-action-buttons">
                <button class="btn-edit-conectados" title="Editar bloque" style="background: white; border: 1px solid var(--border); color: var(--primary); cursor: pointer; padding: 0.35rem 0.6rem; border-radius: 6px; display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; font-weight: 600;">
                    <i data-lucide="pencil" style="width: 14px; height: 14px;"></i> Editar
                </button>
                <button class="btn-delete-conectados" title="Eliminar bloque" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 0.25rem; display: flex; align-items: center; justify-content: center; opacity: 0.6;">
                    <i data-lucide="trash-2" style="width: 16px;"></i>
                </button>
            </div>
            <div class="conectados-content">
                <div class="conectados-image-area">
                    ${act.image_url
                        ? `<img src="${act.image_url}" class="newsletter-img-preview">`
                        : `<div class="newsletter-img-placeholder">
                                <i data-lucide="image"></i>
                                <span>Sin imagen</span>
                           </div>`
                    }
                </div>
                <div class="conectados-text-area">
                    <div class="conectados-block-badge" style="display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.15rem 0.55rem; background: ${badge.bg}; color: ${badge.color}; border-radius: 999px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.5rem;">
                        ${badge.icon} ${badge.label}
                    </div>
                    <div class="conectados-preview-title">${(act.title || '<span style="color: var(--text-muted); font-weight: 400;">(sin título)</span>').toString().replace(/</g, m => m === '<' ? '&lt;' : m)}</div>
                    <div class="conectados-preview-snippet">${snippet ? snippet.replace(/</g, '&lt;') : '<span style="color: var(--text-muted); font-style: italic;">(sin contenido)</span>'}</div>
                </div>
            </div>
        `;

        const btnEdit = item.querySelector('.btn-edit-conectados');
        const btnDelete = item.querySelector('.btn-delete-conectados');

        btnDelete.onmouseover = () => btnDelete.style.opacity = '1';
        btnDelete.onmouseout = () => btnDelete.style.opacity = '0.6';

        btnDelete.onclick = (e) => {
            e.stopPropagation();
            if (confirm('¿Estás seguro de que querés eliminar este bloque?')) {
                deleteActivity(act.id);
            }
        };

        btnEdit.onclick = (e) => {
            e.stopPropagation();
            openConectadosEditor(act);
        };

        // Mobile: tap en la fila colapsada abre el modal igualito (más simple
        // que mantener el acordeón viejo con un modal distinto).
        const mobileRow = item.querySelector('.conectados-mobile-row');
        mobileRow.addEventListener('click', (e) => {
            if (e.target.closest('.conectados-mobile-handle')) return;
            openConectadosEditor(act);
        });

        listContainer.appendChild(item);
    });

    wrapper.appendChild(listContainer);
    container.appendChild(wrapper);

    // SortableJS para reordenar bloques
    if (window.Sortable) {
        window.Sortable.create(listContainer, {
            handle: '.drag-handle, .conectados-mobile-handle',
            animation: 150,
            delay: 200,
            delayOnTouchOnly: true,
            touchStartThreshold: 5,
            onEnd: () => {
                const items = listContainer.querySelectorAll('.conectados-item');
                items.forEach((item, index) => {
                    updateActivity(item.dataset.id, { order_index: index }, false);
                });
            }
        });
    }

    // --- Botones del header ---
    wrapper.querySelector('#btn-add-var-block').onclick = () => {
        addActivity({
            title: 'Bloque Variable',
            copy_linkedin: '',
            description: '',
            channels: ['Conectados'],
            date: new Date().toISOString().split('T')[0],
            time: '00:00',
            is_custom: true,
            block_type: 'variable'
        });
    };

    wrapper.querySelector('#btn-add-fixed-block').onclick = () => {
        addActivity({
            title: 'Bloque Fijo',
            copy_linkedin: '',
            description: '',
            channels: ['Conectados'],
            date: '2099-12-31',  // far future para que no aparezca en otras vistas
            time: '00:00',
            is_custom: true,
            block_type: 'fixed'
        });
    };

    wrapper.querySelector('#btn-gen-newsletter').onclick = () => {
        openNewsletterPreview(listContainer);
    };

    if (window.lucide) window.lucide.createIcons();
}

// =================================================================
// MODAL DE EDICIÓN DE BLOQUE (desktop principalmente, sirve también en mobile)
// =================================================================
function openConectadosEditor(act) {
    const kind = blockKind(act);
    const isActivity = kind === 'activity';

    const overlay = document.createElement('div');
    overlay.className = 'login-overlay conectados-editor-overlay';
    overlay.innerHTML = `
        <div class="login-card conectados-editor-card" style="max-width: 720px; width: 92%; max-height: 92vh; display: flex; flex-direction: column; overflow: hidden; padding: 0;">
            <div style="padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
                <h3 style="margin: 0; display: inline-flex; align-items: center; gap: 0.5rem;">
                    <i data-lucide="pencil" style="width: 18px; height: 18px;"></i>
                    Editar bloque
                    <span style="display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.15rem 0.55rem; background: ${BLOCK_BADGE[kind].bg}; color: ${BLOCK_BADGE[kind].color}; border-radius: 999px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; margin-left: 0.25rem;">
                        ${BLOCK_BADGE[kind].icon} ${BLOCK_BADGE[kind].label}
                    </span>
                </h3>
                <button id="btn-editor-close" style="background: none; border: none; cursor: pointer; color: var(--text-muted);"><i data-lucide="x"></i></button>
            </div>

            <div style="flex: 1; overflow-y: auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.25rem;">
                <div>
                    <label style="display: block; font-weight: 600; font-size: 0.85rem; margin-bottom: 0.4rem;">Imagen del bloque</label>
                    <div id="editor-image-area" style="border: 2px dashed var(--border); border-radius: 0.75rem; padding: ${act.image_url ? '0.5rem' : '1.5rem'}; background: #fafafa; text-align: center; cursor: pointer; min-height: 120px; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 0.5rem; position: relative;">
                        ${act.image_url
                            ? `<img id="editor-image-preview" src="${act.image_url}" style="max-width: 100%; max-height: 220px; border-radius: 0.5rem; display: block;">`
                            : `<i data-lucide="image-up" style="width: 28px; height: 28px; color: var(--text-muted);"></i>
                               <span style="color: var(--text-muted); font-size: 0.85rem;">Click para subir una imagen</span>`
                        }
                        <input id="editor-image-input" type="file" accept="image/*" style="display: none;">
                    </div>
                    ${act.image_url ? '<button id="editor-image-remove" style="margin-top: 0.5rem; background: none; border: none; color: #ef4444; cursor: pointer; font-size: 0.8rem;">✕ Quitar imagen</button>' : ''}
                </div>

                <div>
                    <label for="editor-title" style="display: block; font-weight: 600; font-size: 0.85rem; margin-bottom: 0.4rem;">Título</label>
                    <input id="editor-title" type="text" value="${(act.title || '').replace(/"/g, '&quot;')}" style="width: 100%; padding: 0.65rem 0.8rem; border: 1px solid var(--border); border-radius: 0.5rem; font-size: 0.95rem;">
                </div>

                <div>
                    <label for="editor-body" style="display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 0.85rem; margin-bottom: 0.4rem;">
                        <span>Texto del bloque</span>
                        ${isActivity ? `
                            <button id="editor-ai" type="button" style="background: var(--primary); color: white; border: none; padding: 0.35rem 0.7rem; border-radius: 0.4rem; font-size: 0.75rem; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 0.35rem;">
                                <i data-lucide="sparkles" style="width: 14px; height: 14px;"></i> Generar con IA
                            </button>
                        ` : ''}
                    </label>
                    <textarea id="editor-body" rows="9" style="width: 100%; padding: 0.65rem 0.8rem; border: 1px solid var(--border); border-radius: 0.5rem; font-size: 0.9rem; resize: vertical; line-height: 1.5;">${blockBodyText(act)}</textarea>
                    ${isActivity ? '<div id="editor-ai-status" style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.4rem;"></div>' : ''}
                </div>
            </div>

            <div style="padding: 1rem 1.5rem; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 0.75rem; background: #fafafa;">
                <button id="btn-editor-cancel" style="background: white; border: 1px solid var(--border); padding: 0.6rem 1.2rem; border-radius: 0.5rem; font-weight: 600; cursor: pointer;">Cancelar</button>
                <button id="btn-editor-save" class="btn-primary" style="width: auto; padding: 0.6rem 1.5rem; background: var(--primary);">Guardar</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    if (window.lucide) window.lucide.createIcons();

    // --- State local del editor ---
    let currentImageUrl = act.image_url || '';

    const inputTitle = overlay.querySelector('#editor-title');
    const inputBody = overlay.querySelector('#editor-body');
    const imageArea = overlay.querySelector('#editor-image-area');
    const imageInput = overlay.querySelector('#editor-image-input');
    const removeBtn = overlay.querySelector('#editor-image-remove');

    // --- Imagen: click → file picker
    imageArea.onclick = () => imageInput.click();
    imageInput.onchange = async (e) => {
        if (!e.target.files.length) return;
        const file = e.target.files[0];
        const formData = new FormData();
        formData.append('file', file);

        imageArea.style.opacity = '0.5';
        try {
            const res = await fetch('/api/agenda/upload', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.url) {
                currentImageUrl = data.url;
                imageArea.innerHTML = `<img id="editor-image-preview" src="${data.url}" style="max-width: 100%; max-height: 220px; border-radius: 0.5rem; display: block;">
                    <input id="editor-image-input" type="file" accept="image/*" style="display: none;">`;
                imageArea.style.padding = '0.5rem';
                // Re-bindeo el nuevo input (porque cambió el DOM)
                const newInput = imageArea.querySelector('#editor-image-input');
                newInput.onchange = imageInput.onchange;
                imageArea.onclick = () => newInput.click();
                // Si no había botón remove, lo agrego
                if (!overlay.querySelector('#editor-image-remove')) {
                    const wrap = imageArea.parentElement;
                    const btn = document.createElement('button');
                    btn.id = 'editor-image-remove';
                    btn.style.cssText = 'margin-top: 0.5rem; background: none; border: none; color: #ef4444; cursor: pointer; font-size: 0.8rem;';
                    btn.textContent = '✕ Quitar imagen';
                    btn.onclick = () => {
                        currentImageUrl = '';
                        imageArea.innerHTML = `<i data-lucide="image-up" style="width: 28px; height: 28px; color: var(--text-muted);"></i>
                            <span style="color: var(--text-muted); font-size: 0.85rem;">Click para subir una imagen</span>
                            <input id="editor-image-input" type="file" accept="image/*" style="display: none;">`;
                        imageArea.style.padding = '1.5rem';
                        const ni = imageArea.querySelector('#editor-image-input');
                        ni.onchange = imageInput.onchange;
                        imageArea.onclick = () => ni.click();
                        btn.remove();
                        if (window.lucide) window.lucide.createIcons();
                    };
                    wrap.appendChild(btn);
                }
            }
        } catch (err) {
            console.error(err);
            alert('Error al subir imagen');
        } finally {
            imageArea.style.opacity = '1';
        }
    };

    if (removeBtn) {
        removeBtn.onclick = () => {
            currentImageUrl = '';
            imageArea.innerHTML = `<i data-lucide="image-up" style="width: 28px; height: 28px; color: var(--text-muted);"></i>
                <span style="color: var(--text-muted); font-size: 0.85rem;">Click para subir una imagen</span>
                <input id="editor-image-input" type="file" accept="image/*" style="display: none;">`;
            imageArea.style.padding = '1.5rem';
            const ni = imageArea.querySelector('#editor-image-input');
            ni.onchange = imageInput.onchange;
            imageArea.onclick = () => ni.click();
            removeBtn.remove();
            if (window.lucide) window.lucide.createIcons();
        };
    }

    // --- Botón IA (sólo en bloques de actividad) ---
    if (isActivity) {
        const btnAI = overlay.querySelector('#editor-ai');
        const status = overlay.querySelector('#editor-ai-status');
        btnAI.onclick = async () => {
            // Tomamos los datos más frescos: lo que ya está en la actividad +
            // lo que el usuario haya escrito en este modal (por si recién
            // pegó algo y le pega al botón).
            const liveAct = {
                ...act,
                title: inputTitle.value || act.title,
            };
            btnAI.disabled = true;
            const orig = btnAI.innerHTML;
            btnAI.innerHTML = '<i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Generando…';
            if (window.lucide) window.lucide.createIcons();

            const result = await generateNewsletterBlock(liveAct);
            if (result) {
                if (result.title) inputTitle.value = result.title;
                if (result.copy) inputBody.value = result.copy;
                const sourceTxt = {
                    linkedin: 'tomó como base el copy de LinkedIn',
                    instagram: 'tomó como base el copy de Instagram',
                    basic: 'tomó como base los datos de la actividad (sin copys cargados)',
                }[result.source] || '';
                status.textContent = `✓ IA ${sourceTxt}.`;
            }

            btnAI.innerHTML = orig;
            btnAI.disabled = false;
            if (window.lucide) window.lucide.createIcons();
        };
    }

    // --- Cerrar / Cancelar ---
    const close = () => overlay.remove();
    overlay.querySelector('#btn-editor-close').onclick = close;
    overlay.querySelector('#btn-editor-cancel').onclick = close;

    // --- Guardar ---
    overlay.querySelector('#btn-editor-save').onclick = () => {
        updateActivity(act.id, {
            title: inputTitle.value,
            copy_linkedin: inputBody.value,
            conectados_title: inputTitle.value,
            conectados_text: inputBody.value,
            image_url: currentImageUrl,
        }, true);
        close();
    };

    // Click en el backdrop también cierra (clic en el overlay pero no en la card)
    overlay.addEventListener('mousedown', (e) => { overlay._mdTarget = e.target; });
    overlay.addEventListener('mouseup', (e) => {
        if (e.target === overlay && overlay._mdTarget === overlay) close();
    });

    inputTitle.focus();
}

// =================================================================
// Vista previa del newsletter (igual que antes)
// =================================================================
function openNewsletterPreview(listContainer) {
    const items = Array.from(listContainer.querySelectorAll('.conectados-item'));
    const liveActivities = items.map(item => {
        const id = item.dataset.id;
        return state.activities.find(a => a.id === id);
    }).filter(Boolean).map(a => ({
        ...a,
        // El newsletter siempre toma copy_linkedin como cuerpo (la nueva
        // edición guarda allí). conectados_text lo dejamos por compat.
    }));

    const html = generateNewsletterHTML(liveActivities);

    const modal = document.createElement('div');
    modal.className = 'login-overlay';
    modal.innerHTML = `
        <div class="login-card" style="max-width: 800px; width: 90%; height: 90vh; display: flex; flex-direction: column;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <h3 style="margin: 0;">Vista Previa Newsletter</h3>
                <button id="close-newsletter" style="background: none; border: none; cursor: pointer;"><i data-lucide="x"></i></button>
            </div>
            <iframe id="newsletter-preview" style="flex: 1; border: 1px solid #eee; background: white;"></iframe>
            <div style="margin-top: 1rem; display: flex; gap: 1rem;">
                <button id="copy-newsletter-html" class="btn-primary" style="flex: 1; background: #0742ab;">
                    <i data-lucide="copy"></i> Copiar Código HTML
                </button>
                <button id="btn-close-preview" class="btn-primary" style="background: #64748b; padding: 0.5rem 1.5rem;">
                    Cerrar
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const iframe = modal.querySelector('#newsletter-preview');
    iframe.srcdoc = html;

    modal.querySelector('#close-newsletter').onclick = () => modal.remove();
    modal.querySelector('#btn-close-preview').onclick = () => modal.remove();
    modal.querySelector('#copy-newsletter-html').onclick = () => {
        navigator.clipboard.writeText(html);
        const btn = modal.querySelector('#copy-newsletter-html');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i data-lucide="check"></i> ¡Copiado!';
        setTimeout(() => btn.innerHTML = originalHTML, 2000);
    };

    if (window.lucide) window.lucide.createIcons();
}
