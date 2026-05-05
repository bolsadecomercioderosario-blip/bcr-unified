import { state, updateActivity, addActivity, deleteActivity, suggestJournalisticTitle } from '../state.js';
import { generateLICopy } from '../utils/ai-engine.js';

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
            <div class="drag-handle">
                <i data-lucide="grip-vertical" style="width: 16px;"></i>
            </div>
            <div style="display: flex; justify-content: flex-end; position: absolute; top: 0.5rem; right: 0.5rem; gap: 0.5rem; z-index: 10;">
                <button class="btn-gen-conectados" title="Generar texto con IA" style="background: none; border: none; color: var(--primary); cursor: pointer; padding: 0.2rem; display: flex; align-items: center; justify-content: center; transition: opacity 0.2s;">
                    <i data-lucide="sparkles" style="width: 16px; height: 16px;"></i>
                </button>
                <button class="btn-delete-conectados" title="Eliminar Bloque" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 0.2rem; display: flex; align-items: center; justify-content: center; opacity: 0.6; transition: opacity 0.2s;">
                    <i data-lucide="trash-2" style="width: 14px;"></i>
                </button>
            </div>
            <textarea class="input-conectados-title" rows="1" 
                      placeholder="Título del bloque..." style="padding-right: 4rem;">${act.title || ''}</textarea>
            <textarea class="input-conectados-text" rows="1" 
                      placeholder="Texto del bloque...">${act.copy_linkedin || act.conectados_text || act.description || ''}</textarea>
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

        const autoGrow = (el) => {
            el.style.height = 'auto';
            el.style.height = el.scrollHeight + 'px';
        };

        titleInput.oninput = () => {
            autoGrow(titleInput);
            saveChanges(true);
        };
        textInput.oninput = () => {
            autoGrow(textInput);
            saveChanges(true);
        };

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
            handle: '.drag-handle',
            animation: 150,
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

    if (window.lucide) window.lucide.createIcons();
}
