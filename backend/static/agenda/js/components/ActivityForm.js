import { state, addActivity, updateActivity, deleteActivity } from '../state.js';
import { generateIGCopy, generateLICopy } from '../utils/ai-engine.js';

export function renderActivityForm(container, preData = null) {
    const sourceAct = preData || state.currentActivity || {};
    const act = {
        id: sourceAct.id || '',
        date: sourceAct.date || new Date().toISOString().split('T')[0],
        time: sourceAct.time || '09:00',
        title: sourceAct.title || '',
        description: sourceAct.description || '',
        location: (sourceAct.location === 'undefined' || !sourceAct.location) ? '' : sourceAct.location,
        observations: (sourceAct.observations === 'undefined' || !sourceAct.observations) ? '' : sourceAct.observations,
        responsible: sourceAct.responsible || '', 
        external_name: sourceAct.external_name || '',
        channels: sourceAct.channels || [],
        done: sourceAct.done || false,
        drive_bcr: (sourceAct.drive_bcr === 'undefined' || !sourceAct.drive_bcr) ? '' : sourceAct.drive_bcr,
        drive_santiago: (sourceAct.drive_santiago === 'undefined' || !sourceAct.drive_santiago) ? '' : sourceAct.drive_santiago,
        copy_instagram: (sourceAct.copy_instagram === 'undefined' || !sourceAct.copy_instagram) ? '' : sourceAct.copy_instagram,
        copy_linkedin: (sourceAct.copy_linkedin === 'undefined' || !sourceAct.copy_linkedin) ? '' : sourceAct.copy_linkedin,
        participants: sourceAct.participants || '',
        story_type: sourceAct.story_type || 'Video'
    };

    const isNew = !state.currentActivity;
    
    container.innerHTML = `
        <div class="sheet-header" style="padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
            <h2 style="font-weight: 700;">${isNew ? 'Nueva Actividad' : 'Editar Actividad'}</h2>
            <button onclick="window.closeActivitySheet()" style="background: none; border: none; cursor: pointer; color: var(--text-muted);">
                <i data-lucide="x"></i>
            </button>
        </div>
        
        <div class="sheet-body" style="flex-grow: 1; overflow-y: auto; padding: 1.5rem;">
            <form id="form-activity" style="display: flex; flex-direction: column; gap: 1.5rem;">
                
                <section>
                    <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Datos Generales</h3>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label>Fecha</label>
                            <input type="date" name="date" value="${act.date}" required>
                        </div>
                        <div class="form-group">
                            <label>Hora</label>
                            <input type="time" name="time" value="${act.time}" required>
                        </div>
                    </div>
                    <div class="form-group" style="margin-top: 1rem;">
                        <label>Título</label>
                        <input type="text" name="title" value="${act.title}" placeholder="Ej: Lanzamiento de..." required>
                    </div>
                    <div class="form-group" style="margin-top: 1rem;">
                        <label>Descripción</label>
                        <textarea name="description" rows="3">${act.description}</textarea>
                    </div>
                    <div class="form-grid-2" style="margin-top: 1rem;">
                        <div class="form-group">
                            <label>Lugar</label>
                            <input type="text" name="location" value="${act.location}">
                        </div>
                        <div class="form-group">
                            <label>Observaciones</label>
                            <input type="text" name="observations" value="${act.observations}">
                        </div>
                    </div>
                    <div class="form-group" style="margin-top: 1rem;">
                        <label>Autoridades Presentes</label>
                        <input type="text" name="participants" value="${act.participants}" placeholder="Ej: Juan Pérez, María García, Autoridades locales...">
                    </div>
                </section>

                <section>
                    <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Operativo</h3>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label>Responsable</label>
                            <select name="responsible" id="select-responsible">
                                <option value="" ${!act.responsible ? 'selected' : ''}>-- Seleccionar --</option>
                                <option value="Juan" ${act.responsible === 'Juan' ? 'selected' : ''}>Juan</option>
                                <option value="Paku" ${act.responsible === 'Paku' ? 'selected' : ''}>Paku</option>
                                <option value="Guillermina" ${act.responsible === 'Guillermina' ? 'selected' : ''}>Guillermina</option>
                                <option value="Externo" ${act.responsible === 'Externo' ? 'selected' : ''}>Externo</option>
                            </select>
                        </div>
                        <div class="form-group" id="group-external" style="display: ${act.responsible === 'Externo' ? 'block' : 'none'};">
                            <label>Nombre Externo</label>
                            <input type="text" name="external_name" value="${act.external_name || ''}">
                        </div>
                    </div>
                    
                    <div style="margin-top: 1rem;">
                        <label style="display: block; margin-bottom: 0.5rem; font-weight: 500; font-size: 0.9rem;">Canales de Difusión</label>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                            ${['Instagram Story', 'Instagram Feed', 'LinkedIn', 'X', 'YouTube', 'Facebook', 'Más BCR', 'Envíalo Simple', 'Mail a asociados', 'Conectados'].map(ch => `
                                <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; cursor: pointer;">
                                    <input type="checkbox" name="channels" value="${ch}" ${act.channels.includes(ch) ? 'checked' : ''}>
                                    ${ch}
                                </label>
                            `).join('')}
                        </div>
                    </div>

                    <div id="group-story-type" style="margin-top: 1rem; display: none; padding: 0.75rem; background: #fffbeb; border: 1px solid #fde68a; border-radius: 0.5rem;">
                        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; font-size: 0.85rem; color: #92400e;">Formato de IG Story</label>
                        <select name="story_type" style="width: 100%; padding: 0.4rem; border-radius: 0.25rem; border: 1px solid #fde68a;">
                            <option value="Video" ${act.story_type === 'Video' ? 'selected' : ''}>Video (Realización AV)</option>
                            <option value="Layout" ${act.story_type === 'Layout' ? 'selected' : ''}>Layout (Collage de fotos)</option>
                        </select>
                    </div>

                    <div style="margin-top: 1.5rem;">
                        <label style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer; font-weight: 600;">
                            <input type="checkbox" name="done" ${act.done ? 'checked' : ''} style="width: 18px; height: 18px;">
                            Realizado
                        </label>
                    </div>
                </section>

                <section>
                    <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Links y Contenido</h3>
                    <div class="form-group">
                        <label>Link Drive Cobertura BCR</label>
                        <input type="url" name="drive_bcr" value="${act.drive_bcr}" placeholder="https://...">
                    </div>
                    <div class="form-group" id="group-santiago" style="margin-top: 1rem; display: none;">
                        <label>Link Drive Santiago</label>
                        <input type="url" name="drive_santiago" value="${act.drive_santiago}" placeholder="https://...">
                    </div>

                    <div style="margin-top: 1.5rem; background: #f8fafc; padding: 1.5rem; border-radius: 0.5rem; border: 1px dashed var(--border);">
                        <div style="font-weight: 700; font-size: 0.9rem; margin-bottom: 1.25rem; color: var(--primary); text-transform: uppercase; letter-spacing: 0.05em;">GENERACIÓN DE TEXTOS (IA)</div>
                        
                        <div class="form-group">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                <label style="margin: 0;">Copy Instagram</label>
                                <div style="display: flex; gap: 0.5rem;">
                                    <button type="button" id="btn-copy-ig" class="btn-primary" style="width: auto; padding: 0.35rem 0.6rem; font-size: 0.75rem; background: #64748b; border-radius: 4px; display: flex; align-items: center; gap: 0.4rem;" title="Copiar al portapapeles">
                                        <i data-lucide="copy" style="width: 14px; height: 14px;"></i> Copiar
                                    </button>
                                    <button type="button" id="btn-gen-ig" class="btn-primary" style="width: auto; padding: 0.35rem 0.8rem; font-size: 0.75rem; background: var(--primary); border-radius: 4px; display: flex; align-items: center; gap: 0.4rem;">
                                        <i data-lucide="sparkles" style="width: 14px; height: 14px;"></i> Generar
                                    </button>
                                </div>
                            </div>
                            <textarea name="copy_instagram" id="copy-ig" rows="4" style="font-size: 0.85rem; border-radius: 6px;">${act.copy_instagram}</textarea>
                        </div>

                        <div class="form-group" style="margin-top: 1.5rem;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                <label style="margin: 0;">Copy LinkedIn / Conectados</label>
                                <div style="display: flex; gap: 0.5rem;">
                                    <button type="button" id="btn-copy-li" class="btn-primary" style="width: auto; padding: 0.35rem 0.6rem; font-size: 0.75rem; background: #64748b; border-radius: 4px; display: flex; align-items: center; gap: 0.4rem;" title="Copiar al portapapeles">
                                        <i data-lucide="copy" style="width: 14px; height: 14px;"></i> Copiar
                                    </button>
                                    <button type="button" id="btn-gen-li" class="btn-primary" style="width: auto; padding: 0.35rem 0.8rem; font-size: 0.75rem; background: var(--primary); border-radius: 4px; display: flex; align-items: center; gap: 0.4rem;">
                                        <i data-lucide="sparkles" style="width: 14px; height: 14px;"></i> Generar
                                    </button>
                                </div>
                            </div>
                            <textarea name="copy_linkedin" id="copy-li" rows="6" style="font-size: 0.85rem; border-radius: 6px;">${act.copy_linkedin}</textarea>
                        </div>
                    </div>
                </section>
            </form>
        </div>
        
        <div class="sheet-footer" style="padding: 1.5rem; border-top: 1px solid var(--border); display: flex; gap: 1rem;">
            <button id="btn-save-activity" class="btn-primary">Guardar Cambios</button>
            <button onclick="window.closeActivitySheet()" style="flex-grow: 1; background: white; border: 1px solid var(--border); border-radius: 0.5rem; font-weight: 600; cursor: pointer;">Cancelar</button>
            ${!isNew ? `<button id="btn-delete-activity-form" style="background: none; border: 1px solid #fca5a5; color: #ef4444; border-radius: 0.5rem; padding: 0 1rem; cursor: pointer; display: flex; align-items: center; justify-content: center;" title="Eliminar"><i data-lucide="trash-2"></i></button>` : ''}
        </div>
    `;

    // Initialize Lucide
    if (window.lucide) window.lucide.createIcons();

    // Logic for conditional fields
    const form = container.querySelector('#form-activity');
    const selectResp = container.querySelector('#select-responsible');
    const groupExt = container.querySelector('#group-external');
    const groupSant = container.querySelector('#group-santiago');
    const channelChecks = container.querySelectorAll('input[name="channels"]');

    const updateVisibility = () => {
        // Responsible Externo
        groupExt.style.display = selectResp.value === 'Externo' ? 'block' : 'none';
        
        // Drive Santiago (Audiovisual channels)
        const selectedChannels = Array.from(channelChecks).filter(i => i.checked).map(i => i.value);
        const isAV = selectedChannels.some(ch => ['Instagram Story', 'YouTube'].includes(ch));
        groupSant.style.display = isAV ? 'block' : 'none';

        // Story Type visibility
        const isStory = selectedChannels.includes('Instagram Story');
        container.querySelector('#group-story-type').style.display = isStory ? 'block' : 'none';
    };

    selectResp.onchange = updateVisibility;
    channelChecks.forEach(c => c.onchange = updateVisibility);
    updateVisibility();

    // AI Generation logic (Updated sequential flow)
    const btnGenIg = container.querySelector('#btn-gen-ig');
    const btnGenLi = container.querySelector('#btn-gen-li');
    const txtIg = container.querySelector('#copy-ig');
    const txtLi = container.querySelector('#copy-li');

    btnGenIg.onclick = async () => {
        const title = form.title.value;
        const desc = form.description.value;
        const obs = form.observations.value;
        
        if (!title) return alert('Ingresa un título.');
        
        btnGenIg.disabled = true;
        const originalTextIg = btnGenIg.innerHTML;
        btnGenIg.innerHTML = '<i data-lucide="loader" class="spin"></i> ...';
        if (window.lucide) window.lucide.createIcons();

        txtIg.value = await generateIGCopy(title, desc, obs);
        
        btnGenIg.innerHTML = originalTextIg;
        btnGenIg.disabled = false;
        if (window.lucide) window.lucide.createIcons();
    };

    btnGenLi.onclick = async () => {
        const title = form.title.value;
        const desc = form.description.value;
        const obs = form.observations.value;
        const participants = form.participants.value;
        
        btnGenLi.disabled = true;
        const originalTextLi = btnGenLi.innerHTML;
        btnGenLi.innerHTML = '<i data-lucide="loader" class="spin"></i> ...';
        if (window.lucide) window.lucide.createIcons();

        txtLi.value = await generateLICopy(title, desc, obs, participants);
        
        btnGenLi.innerHTML = originalTextLi;
        btnGenLi.disabled = false;
        if (window.lucide) window.lucide.createIcons();
    };

    const copyToClipboard = (btnId, inputEl) => {
        const btn = container.querySelector('#' + btnId);
        btn.onclick = () => {
            if (!inputEl.value) return;
            navigator.clipboard.writeText(inputEl.value);
            const orig = btn.innerHTML;
            btn.innerHTML = '<i data-lucide="check" style="width: 14px; height: 14px;"></i> Copiado';
            if (window.lucide) window.lucide.createIcons();
            setTimeout(() => { btn.innerHTML = orig; if (window.lucide) window.lucide.createIcons(); }, 2000);
        };
    };

    copyToClipboard('btn-copy-ig', txtIg);
    copyToClipboard('btn-copy-li', txtLi);

    // Save logic
    container.querySelector('#btn-save-activity').onclick = async () => {
        const formData = new FormData(form);
        
        // Use a more robust way to get all checked channels
        const selectedChannels = Array.from(form.querySelectorAll('input[name="channels"]:checked'))
            .map(cb => cb.value);

        const data = {
            date: formData.get('date'),
            time: formData.get('time'),
            title: formData.get('title'),
            description: formData.get('description'),
            location: formData.get('location'),
            observations: formData.get('observations'),
            responsible: formData.get('responsible'),
            external_name: formData.get('external_name'),
            channels: selectedChannels,
            done: formData.get('done') === 'on',
            drive_bcr: formData.get('drive_bcr'),
            drive_santiago: formData.get('drive_santiago'),
            copy_instagram: formData.get('copy_instagram'),
            copy_linkedin: formData.get('copy_linkedin'),
            participants: formData.get('participants'),
            story_type: formData.get('story_type')
        };

        const btnSave = container.querySelector('#btn-save-activity');
        const originalText = btnSave.innerText;
        btnSave.disabled = true;
        btnSave.innerText = 'Guardando...';

        try {
            if (isNew) {
                await addActivity(data);
            } else {
                await updateActivity(act.id, data);
            }
            window.closeActivitySheet();
        } catch (error) {
            alert('Error al guardar: ' + error.message);
            btnSave.disabled = false;
            btnSave.innerText = originalText;
        }
    };

    if (!isNew) {
        container.querySelector('#btn-delete-activity-form').onclick = () => {
            if (confirm('¿Estás seguro de que querés eliminar esta actividad? Esta acción no se puede deshacer.')) {
                deleteActivity(act.id);
                window.closeActivitySheet();
            }
        };
    }
}
