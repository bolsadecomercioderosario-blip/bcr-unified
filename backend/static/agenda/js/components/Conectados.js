import { state, updateActivity, addActivity, deleteActivity, suggestJournalisticTitle } from '../state.js';
import { generateLICopy } from '../utils/ai-engine.js';
import { generateNewsletterHTML } from '../utils/NewsletterGenerator.js';

function isCurrentNewsletterWeek(dateStr) {
    if (!dateStr) return false;
    const actDate = new Date(dateStr + "T00:00:00");
    const today = new Date();
    today.setHours(0,0,0,0);
    
    const day = today.getDay();
    // Newsletter week: Saturday to Friday
    // Sat = 6, Sun = 0, Mon = 1, etc.
    const diff = day === 6 ? 0 : -(day + 1);
    
    const saturday = new Date(today);
    saturday.setDate(today.getDate() + diff);
    
    const nextFriday = new Date(saturday);
    nextFriday.setDate(saturday.getDate() + 6);
    nextFriday.setHours(23, 59, 59, 999);
    
    return actDate >= saturday && actDate <= nextFriday;
}

export function renderConectados(container) {
    const conectadosActivities = state.activities
        .filter(a => {
            if (!a.channels.includes('Conectados')) return false;
            if (a.is_custom && a.observations === 'FIXED_BLOCK') return true;
            return isCurrentNewsletterWeek(a.date);
        })
        .sort((a, b) => (a.order_index || 0) - (b.order_index || 0));

    const wrapper = document.createElement('div');
    wrapper.className = 'content-wrapper';

    if (conectadosActivities.length === 0) {
        wrapper.innerHTML = '<div style="text-align: center; padding: 4rem; color: var(--text-muted);">No hay actividades marcadas para "Conectados" esta semana.</div>';
    }

    const header = document.createElement('div');
    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;';
    header.innerHTML = `
        <h2 style="font-weight: 700; margin: 0;">Newsletter Conectados</h2>
        <div style="display: flex; gap: 0.5rem;">
            <button id="btn-gen-newsletter" class="btn-primary" style="width: auto; padding: 0.5rem 1rem; background: #0742ab;">
                <i data-lucide="mail"></i> Generar Newsletter
            </button>
            <button id="btn-add-fixed-block" class="btn-primary" style="width: auto; padding: 0.5rem 1rem; background: #64748b;">
                <i data-lucide="pin"></i> Bloque Fijo
            </button>
            <button id="btn-add-var-block" class="btn-primary" style="width: auto; padding: 0.5rem 1rem;">
                <i data-lucide="plus-circle"></i> Bloque Variable
            </button>
        </div>
    `;
    if (conectadosActivities.length > 0 || true) {
        wrapper.appendChild(header);
    }

    const listContainer = document.createElement('div');
    listContainer.id = 'conectados-sortable-list';
    listContainer.className = 'conectados-grid';

    conectadosActivities.forEach((act) => {
        const item = document.createElement('div');
        item.className = 'conectados-item';
        item.dataset.id = act.id;

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
                <button class="btn-gen-conectados" title="Generar texto con IA" style="background: none; border: none; color: var(--primary); cursor: pointer; padding: 0.2rem; display: flex; align-items: center; justify-content: center; transition: opacity 0.2s;">
                    <i data-lucide="sparkles" style="width: 16px; height: 16px;"></i>
                </button>
                <button class="btn-delete-conectados" title="Eliminar Bloque" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 0.2rem; display: flex; align-items: center; justify-content: center; opacity: 0.6; transition: opacity 0.2s;">
                    <i data-lucide="trash-2" style="width: 14px;"></i>
                </button>
            </div>
            <div class="conectados-content">
                <div class="conectados-image-area">
                    ${act.image_url ? 
                        `<img src="${act.image_url}" class="newsletter-img-preview">` : 
                        `<div class="newsletter-img-placeholder">
                            <i data-lucide="image"></i>
                            <span>Arrastrar imagen</span>
                         </div>`
                    }
                    <input type="file" class="input-newsletter-file" style="display: none;" accept="image/*">
                </div>
                <div class="conectados-text-area">
                    <textarea class="input-conectados-title" rows="1" 
                              placeholder="Título del bloque...">${act.title || ''}</textarea>
                    <textarea class="input-conectados-text" rows="1" 
                              placeholder="Texto del bloque...">${act.copy_linkedin || act.conectados_text || act.description || ''}</textarea>
                </div>
            </div>
        `;

        // Auto-save logic
        const titleInput = item.querySelector('.input-conectados-title');
        const textInput = item.querySelector('.input-conectados-text');
        const btnDelete = item.querySelector('.btn-delete-conectados');
        const btnGen = item.querySelector('.btn-gen-conectados');

        btnDelete.onmouseover = () => btnDelete.style.opacity = '1';
        btnDelete.onmouseout = () => btnDelete.style.opacity = '0.6';

        btnDelete.onclick = () => {
            if (confirm('¿Estás seguro de que querés eliminar este bloque?')) {
                deleteActivity(act.id);
            }
        };

        btnGen.onclick = async () => {
            btnGen.disabled = true;
            btnGen.innerHTML = '<i data-lucide="loader" class="spin" style="width: 16px; height: 16px;"></i>';
            if (window.lucide) window.lucide.createIcons();
            
            const title = act.title || '';
            const desc = act.description || '';
            const obs = act.observations || '';
            const participants = act.participants || '';
            
            const copy = await generateLICopy(title, desc, obs, participants);
            if (copy) {
                textInput.value = copy;
                autoGrow(textInput);
                saveChanges(true);
            }
            
            btnGen.innerHTML = '<i data-lucide="sparkles" style="width: 16px; height: 16px;"></i>';
            btnGen.disabled = false;
            if (window.lucide) window.lucide.createIcons();
        };

        const saveChanges = (silent = true) => {
            updateActivity(act.id, {
                title: titleInput.value,
                copy_linkedin: textInput.value,
                conectados_title: titleInput.value, // Keep for backwards compatibility
                conectados_text: textInput.value
            }, !silent);
        };

        // Image Upload logic
        const imgArea = item.querySelector('.conectados-image-area');
        const fileInput = item.querySelector('.input-newsletter-file');

        imgArea.onclick = () => fileInput.click();
        
        fileInput.onchange = async (e) => {
            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                const formData = new FormData();
                formData.append('file', file);
                
                imgArea.style.opacity = '0.5';
                try {
                    const res = await fetch('/api/agenda/upload', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    if (data.url) {
                        updateActivity(act.id, { image_url: data.url }, false);
                        imgArea.innerHTML = `<img src="${data.url}" class="newsletter-img-preview">`;
                        imgArea.style.opacity = '1';
                    }
                } catch (err) {
                    console.error(err);
                    alert('Error al subir imagen');
                    imgArea.style.opacity = '1';
                }
            }
        };

        const autoGrow = (el) => {
            el.style.height = 'auto';
            el.style.height = el.scrollHeight + 'px';
        };

        const mobileTitle = item.querySelector('.conectados-mobile-title');
        const mobileRow = item.querySelector('.conectados-mobile-row');

        titleInput.oninput = () => {
            autoGrow(titleInput);
            // Sync el título visible en la fila colapsada mobile
            if (mobileTitle) {
                const v = titleInput.value.trim();
                mobileTitle.textContent = v || '(sin título)';
                mobileTitle.style.color = v ? '' : 'var(--text-muted)';
                mobileTitle.style.fontWeight = v ? '' : '400';
            }
            saveChanges(true);
        };
        textInput.oninput = () => {
            autoGrow(textInput);
            saveChanges(true);
        };

        // Toggle expand/colapse en mobile (tap en la fila, ignorando el handle)
        mobileRow.addEventListener('click', (e) => {
            if (e.target.closest('.conectados-mobile-handle')) return;
            item.classList.toggle('expanded');
            // Recalcular auto-grow al abrir, ya que un textarea oculto reporta scrollHeight 0
            if (item.classList.contains('expanded')) {
                autoGrow(titleInput);
                autoGrow(textInput);
            }
        });

        // Initial grow
        setTimeout(() => {
            autoGrow(titleInput);
            autoGrow(textInput);
        }, 0);

        listContainer.appendChild(item);
    });

    wrapper.appendChild(listContainer);
    container.appendChild(wrapper);
    
    // Initialize SortableJS
    if (window.Sortable) {
        window.Sortable.create(listContainer, {
            handle: '.drag-handle, .conectados-mobile-handle',
            animation: 150,
            // Long-press en touch para no confundir con scroll vertical
            delay: 200,
            delayOnTouchOnly: true,
            touchStartThreshold: 5,
            onEnd: () => {
                // Update order_index for all items
                const items = listContainer.querySelectorAll('.conectados-item');
                items.forEach((item, index) => {
                    updateActivity(item.dataset.id, { order_index: index }, false); // Silent update
                });
                // No notify() here to keep the SortableJS DOM state stable
                console.log('Order updated silently');
            }
        });
    }

    // Add Variable Block
    wrapper.querySelector('#btn-add-var-block').onclick = () => {
        addActivity({
            title: 'Bloque Variable',
            copy_linkedin: 'Contenido específico de esta semana...',
            description: 'Contenido específico de esta semana...',
            channels: ['Conectados'],
            date: new Date().toISOString().split('T')[0],
            time: '00:00',
            is_custom: true
        });
    };

    // Add Fixed Block
    wrapper.querySelector('#btn-add-fixed-block').onclick = () => {
        addActivity({
            title: 'Bloque Fijo',
            copy_linkedin: 'Sección permanente...',
            description: 'Sección permanente...',
            channels: ['Conectados'],
            date: '2099-12-31', // Far future so it doesn't mess with chronological sorting in other views if ever visible
            time: '00:00',
            is_custom: true,
            observations: 'FIXED_BLOCK'
        });
    };

    // Generate Newsletter
    wrapper.querySelector('#btn-gen-newsletter').onclick = () => {
        // Obtenemos los datos actuales de la interfaz para que sea 100% real-time
        const items = Array.from(listContainer.querySelectorAll('.conectados-item'));
        const liveActivities = items.map(item => {
            const id = item.dataset.id;
            const originalAct = state.activities.find(a => a.id === id);
            return {
                ...originalAct,
                title: item.querySelector('.input-conectados-title').value,
                copy_linkedin: item.querySelector('.input-conectados-text').value,
                image_url: originalAct ? originalAct.image_url : ''
            };
        });

        const html = generateNewsletterHTML(liveActivities);
        
        // Modal Preview
        const modal = document.createElement('div');
        modal.className = 'login-overlay'; // Reusing style for backdrop
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
    };

    if (window.lucide) window.lucide.createIcons();
}
