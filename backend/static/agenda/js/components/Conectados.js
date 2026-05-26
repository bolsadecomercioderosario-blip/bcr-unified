import { state, updateActivity, addActivity, deleteActivity } from '../state.js';
// Nota: la generación con IA (botón "Generar con IA" en cada bloque) se sacó
// porque los resultados no eran lo suficientemente buenos. Por ahora los copys
// se redactan a mano o en ChatGPT externo. La función generateNewsletterBlock
// sigue exportada en utils/ai-engine.js por si querés re-habilitarlo.
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

    const overlay = document.createElement('div');
    overlay.className = 'login-overlay conectados-editor-overlay';
    overlay.innerHTML = `
        <div class="login-card conectados-editor-card" style="position: relative; max-width: 760px; width: 92%; height: 88vh; display: flex; flex-direction: column; overflow: hidden; padding: 0;">

            <!-- X flotante (no ocupa una fila propia) -->
            <button id="btn-editor-close" style="position: absolute; top: 0.5rem; right: 0.6rem; background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 0.25rem; line-height: 0; z-index: 5;" title="Cerrar"><i data-lucide="x" style="width: 18px; height: 18px;"></i></button>

            <!-- Cuerpo: strip imagen, título, textarea -->
            <div style="flex: 1; padding: 0.9rem 1.1rem 0.5rem; display: flex; flex-direction: column; gap: 0.65rem; min-height: 0;">

                <!-- Fila 1: strip de imagen -->
                <div id="editor-image-strip" style="display: flex; align-items: center; gap: 0.6rem; padding-right: 1.5rem; /* deja aire para la X */">
                    <input id="editor-image-input" type="file" accept="image/*" style="display: none;">
                    ${act.image_url ? `
                        <img id="editor-image-thumb" src="${act.image_url}" style="width: 80px; height: 54px; object-fit: cover; border-radius: 0.4rem; border: 1px solid var(--border); flex-shrink: 0; cursor: pointer;">
                        <button id="editor-image-change" type="button" style="background: white; border: 1px solid var(--border); color: var(--text-main); padding: 0.4rem 0.7rem; border-radius: 0.4rem; font-size: 0.8rem; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 0.35rem;">
                            <i data-lucide="image" style="width: 14px; height: 14px;"></i> Cambiar
                        </button>
                        <button id="editor-image-remove" type="button" style="background: none; border: none; color: #ef4444; padding: 0.4rem; font-size: 0.8rem; cursor: pointer;" title="Quitar imagen">
                            <i data-lucide="trash-2" style="width: 14px; height: 14px;"></i>
                        </button>
                    ` : `
                        <button id="editor-image-add" type="button" style="background: white; border: 1px dashed var(--border); color: var(--text-muted); padding: 0.5rem 0.85rem; border-radius: 0.4rem; font-size: 0.8rem; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 0.4rem;">
                            <i data-lucide="image-up" style="width: 16px; height: 16px;"></i> Agregar imagen
                        </button>
                    `}
                </div>

                <!-- Título sin label -->
                <input id="editor-title" type="text"
                    value="${(act.title || '').replace(/"/g, '&quot;')}"
                    placeholder="Título del bloque"
                    style="width: 100%; padding: 0.55rem 0.7rem; border: 1px solid var(--border); border-radius: 0.5rem; font-size: 1.05rem; font-weight: 600;">

                <!-- Textarea: protagonista, llena todo el alto disponible -->
                <textarea id="editor-body"
                    placeholder="Texto del bloque…"
                    style="flex: 1; width: 100%; padding: 0.75rem 0.85rem; border: 1px solid var(--border); border-radius: 0.5rem; font-size: 0.95rem; line-height: 1.55; resize: none; font-family: inherit; min-height: 0;">${blockBodyText(act)}</textarea>
            </div>

            <!-- Footer fijo -->
            <div style="padding: 0.75rem 1.1rem; border-top: 1px solid #f1f5f9; display: flex; justify-content: flex-end; gap: 0.6rem; background: #fafafa;">
                <button id="btn-editor-cancel" style="background: white; border: 1px solid var(--border); padding: 0.55rem 1.1rem; border-radius: 0.5rem; font-weight: 600; cursor: pointer;">Cancelar</button>
                <button id="btn-editor-save" class="btn-primary" style="width: auto; padding: 0.55rem 1.4rem; background: var(--primary);">Guardar</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    if (window.lucide) window.lucide.createIcons();

    // --- State local del editor ---
    let currentImageUrl = act.image_url || '';

    const inputTitle = overlay.querySelector('#editor-title');
    const inputBody = overlay.querySelector('#editor-body');
    const strip = overlay.querySelector('#editor-image-strip');
    const imageInput = overlay.querySelector('#editor-image-input');

    // Re-pinta la tira de imagen según haya o no imagen actual.
    function rerenderImageStrip() {
        const existingInput = strip.querySelector('#editor-image-input');
        if (currentImageUrl) {
            strip.innerHTML = `
                <img id="editor-image-thumb" src="${currentImageUrl}" style="width: 80px; height: 54px; object-fit: cover; border-radius: 0.4rem; border: 1px solid var(--border); flex-shrink: 0; cursor: pointer;">
                <button id="editor-image-change" type="button" style="background: white; border: 1px solid var(--border); color: var(--text-main); padding: 0.4rem 0.7rem; border-radius: 0.4rem; font-size: 0.8rem; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 0.35rem;">
                    <i data-lucide="image" style="width: 14px; height: 14px;"></i> Cambiar
                </button>
                <button id="editor-image-remove" type="button" style="background: none; border: none; color: #ef4444; padding: 0.4rem; font-size: 0.8rem; cursor: pointer;" title="Quitar imagen">
                    <i data-lucide="trash-2" style="width: 14px; height: 14px;"></i>
                </button>
            `;
        } else {
            strip.innerHTML = `
                <button id="editor-image-add" type="button" style="background: white; border: 1px dashed var(--border); color: var(--text-muted); padding: 0.5rem 0.85rem; border-radius: 0.4rem; font-size: 0.8rem; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 0.4rem;">
                    <i data-lucide="image-up" style="width: 16px; height: 16px;"></i> Agregar imagen
                </button>
            `;
        }
        // El input file siempre vive en el strip (lo recolocamos)
        strip.insertBefore(existingInput, strip.firstChild);
        bindImageButtons();
        if (window.lucide) window.lucide.createIcons();
    }

    // Asocia los handlers a los botones actuales del strip.
    function bindImageButtons() {
        const add = strip.querySelector('#editor-image-add');
        const change = strip.querySelector('#editor-image-change');
        const remove = strip.querySelector('#editor-image-remove');
        const thumb = strip.querySelector('#editor-image-thumb');
        if (add) add.onclick = () => imageInput.click();
        if (change) change.onclick = () => imageInput.click();
        if (thumb) thumb.onclick = () => imageInput.click();
        if (remove) remove.onclick = () => {
            currentImageUrl = '';
            rerenderImageStrip();
        };
    }

    imageInput.onchange = async (e) => {
        if (!e.target.files.length) return;
        const file = e.target.files[0];
        const formData = new FormData();
        formData.append('file', file);

        strip.style.opacity = '0.5';
        try {
            const res = await fetch('/api/agenda/upload', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.url) {
                currentImageUrl = data.url;
                rerenderImageStrip();
            }
        } catch (err) {
            console.error(err);
            alert('Error al subir imagen');
        } finally {
            strip.style.opacity = '1';
            imageInput.value = '';  // permite re-elegir el mismo archivo
        }
    };

    bindImageButtons();

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
