import { state, addActivity, updateActivity, deleteActivity } from '../state.js';
import { getRole, getAreaSlug } from '../role.js';
import { SEC_RESPONSABLES } from '../constants.js';
// Nota: los botones de "Generar con IA" en este modal se sacaron por seguridad
// (no exponer la API key de OpenAI desde un endpoint público). La generación
// IA queda sólo en el botón del bloque de Conectados.

// Escapa un valor para meterlo en un atributo HTML (value="..."). Sin esto, un
// título con comillas dobles (ej: Cena "El poder...") corta el atributo y el
// campo aparece truncado en el formulario.
function escAttr(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

export function renderActivityForm(container, preData = null) {
    const sourceAct = preData || state.currentActivity || {};
    const act = {
        id: sourceAct.id || '',
        date: sourceAct.date || new Date().toISOString().split('T')[0],
        time: sourceAct.time || '09:00',
        end_date: sourceAct.end_date || '',
        end_time: sourceAct.end_time || '',
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
        participants_me: sourceAct.participants_me || '',
        story_type: sourceAct.story_type || 'Video',
        comunicacion_notes: sourceAct.comunicacion_notes || '',
        sec_notes: sourceAct.sec_notes || '',
        estado: sourceAct.estado || 'Pendiente',
        sec_responsible: sourceAct.sec_responsible || '',
        sec_responsible_other: sourceAct.sec_responsible_other || '',
        attachment_url: sourceAct.attachment_url || '',
        attachment_name: sourceAct.attachment_name || '',
        me_estado: sourceAct.me_estado || ''
    };

    const isNew = !state.currentActivity;

    // --- Rol / origen: deciden qué secciones se muestran y qué se guarda ---
    const role = getRole();
    const isSec = role === 'secretaria';
    const isArea = role === 'area';
    const areaSlug = getAreaSlug();

    // --- Rol Audiovisual (Santiago): vista mínima de solo lectura + único
    // campo editable = el link de video (drive_santiago). El backend además
    // sólo acepta ese campo para este rol, así que es doblemente seguro. ---
    if (role === 'audiovisual') {
        renderAudiovisualForm(container, act);
        return;
    }
    // Origen de la actividad. Para nuevas, lo define el rol que la crea.
    const actOrigen = sourceAct.origen || (isNew ? (isSec ? 'secretaria' : isArea ? 'area' : 'comunicacion') : 'comunicacion');
    // Secretaría viendo una actividad de un ÁREA: solo lectura (el contenido lo
    // maneja el área; Secretaría sólo aprueba/rechaza desde la bandeja).
    const areaForeignForSec = isSec && actOrigen === 'area';
    // ¿Es una actividad de área? (para etiquetas y campos propios del circuito área)
    const esArea = isArea || actOrigen === 'area';
    // Datos Generales: los edita el dueño (Secretaría en las de Mesa; Área en
    // las suyas; Comunicación sólo en sus propias). En las de Secretaría,
    // Comunicación los ve en solo-lectura; en las de área, Secretaría también.
    const generalsEditable = (isSec && !areaForeignForSec) || isArea || actOrigen === 'comunicacion';
    const generalsReadOnly = !generalsEditable;
    // Operativo (responsable, canales, links, copies) + notas internas: sólo
    // Comunicación. Secretaría y Área no ven nada de esto.
    const showOperative = !isSec && !isArea;
    // Borrar la actividad entera es acción del dueño de los Datos Generales.
    const showDelete = !isNew && generalsEditable;

    // Multi-día / rango horario (excepcional): estado inicial según los datos.
    const isMultiday = !!(act.end_date && act.end_date > act.date);
    const hasEndTime = !!act.end_time;
    // Estados de hora: "A definir" (hay hora pero sin definir) y "Sin horario"
    // (todo el día, no tiene hora). Son excluyentes entre sí.
    const timeIsTbd = act.time === 'A definir';
    const timeIsNone = act.time === 'Sin horario';
    const timeDisabled = timeIsTbd || timeIsNone;
    // En actividades de Secretaría vistas por Comunicación (solo lectura),
    // ocultamos los campos de Datos Generales que estén vacíos.
    const hasContent = (v) => v != null && String(v).trim() !== '';
    const showGen = (v) => !generalsReadOnly || hasContent(v);
    // Notas internas de Comunicación: en las actividades ajenas que Comunicación
    // gestiona (de Secretaría o de área ya en la Mesa), no en las nativas suyas.
    const showNotes = showOperative && (actOrigen === 'secretaria' || actOrigen === 'area');

    // --- Bloque de adjunto (al final de Datos Generales) ---
    // Secretaría puede subir/cambiar/quitar; Comunicación sólo ve/descarga (en
    // actividades de Secretaría que ya tengan adjunto).
    let attachmentHTML = '';
    if ((isSec && !areaForeignForSec) || isArea) {
        attachmentHTML = `
            <div class="form-group" style="margin-top: 1rem;">
                <label>Archivo adjunto <span style="font-weight: 400; color: var(--text-muted); font-size: 0.78rem;">(DOC, DOCX, PDF, JPG o PNG)</span></label>
                <input type="file" id="attach-input" accept=".doc,.docx,.pdf,.jpg,.jpeg,.png" style="display: none;">
                <div id="attach-area"></div>
            </div>`;
    } else if (act.attachment_url) {
        attachmentHTML = `
            <div class="form-group" style="margin-top: 1rem;">
                <label>Archivo adjunto</label>
                <a href="${act.attachment_url}" target="_blank" rel="noopener" style="display: inline-flex; align-items: center; gap: 0.4rem; color: var(--primary); font-size: 0.9rem; font-weight: 500; text-decoration: none; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 0.5rem; width: fit-content;">
                    <i data-lucide="paperclip" style="width: 15px; height: 15px;"></i> ${(act.attachment_name || 'archivo adjunto').replace(/</g, '&lt;')} · Descargar
                </a>
            </div>`;
    }

    // --- Sección de Secretaría ---
    const ESTADOS = ['Pendiente', 'En Proceso', 'Avanzado', 'Finalizado'];
    const secRespIsOther = act.sec_responsible === 'Otro';
    // Selector de Responsable de Secretaría (reutilizado).
    const _respSelect = `
        <div class="form-group">
            <label>Responsable de Secretaría</label>
            <select name="sec_responsible" id="sec-resp-select">
                <option value="" ${!act.sec_responsible ? 'selected' : ''}>-- Seleccionar --</option>
                ${SEC_RESPONSABLES.map(r => `<option value="${r}" ${act.sec_responsible === r ? 'selected' : ''}>${r}</option>`).join('')}
                <option value="Otro" ${secRespIsOther ? 'selected' : ''}>Otro</option>
            </select>
        </div>
        <div class="form-group" id="sec-resp-other-group" style="margin-top: 1rem; display: ${secRespIsOther ? 'block' : 'none'};">
            <label>Nombre del responsable</label>
            <input type="text" name="sec_responsible_other" value="${escAttr(act.sec_responsible_other)}" placeholder="Nombre y apellido">
        </div>`;
    const _secNotes = `
        <div class="form-group" style="margin-top: 1rem;">
            <label>Notas internas · Secretaría</label>
            <p style="font-size: 0.78rem; color: var(--text-muted); margin: -0.35rem 0 0.5rem;">Sólo las ve Secretaría.</p>
            <textarea name="sec_notes" rows="4" style="width: 100%; padding: 0.65rem 0.8rem; border: 1px solid var(--border); border-radius: 0.5rem; font-size: 0.95rem; line-height: 1.5; font-family: inherit; resize: vertical;">${escAttr(act.sec_notes)}</textarea>
        </div>`;
    let estadoHTML = '';
    if (isSec && !areaForeignForSec) {
        // Actividad propia de Secretaría: Estado de avance (semáforo) + Responsable.
        estadoHTML = `
            <section>
                <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Estado</h3>
                <div class="form-grid-2">
                    <div class="form-group">
                        <label>Estado de avance</label>
                        <select name="estado">
                            ${ESTADOS.map(s => `<option value="${s}" ${act.estado === s ? 'selected' : ''}>${s}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div style="margin-top: 1rem;">${_respSelect}</div>
            </section>`;
    } else if (areaForeignForSec) {
        // Actividad de área: INTERNO · Secretaría (Responsable + Notas), sin Estado de avance.
        estadoHTML = `
            <section>
                <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">INTERNO · Secretaría</h3>
                ${_respSelect}
                ${_secNotes}
            </section>`;
    }

    // --- "Participa (por Mesa Ejecutiva)": lo carga Secretaría en las de área,
    // va debajo de "Participa (por el área)". Área/Comunicación lo ven read-only. ---
    let participaMeHTML = '';
    if (actOrigen === 'area' && (areaForeignForSec || act.participants_me)) {
        const dis = areaForeignForSec ? '' : 'disabled';
        participaMeHTML = `
            <div class="form-group" style="margin-top: 1rem;">
                <label>Participa (por Mesa Ejecutiva)</label>
                <input type="text" name="participants_me" value="${escAttr(act.participants_me)}" ${dis} placeholder="Autoridades de la Mesa que participan...">
            </div>`;
    }

    // --- Sección "Agenda de la Mesa" (sólo Área): sugerir a Compromisos ---
    let sugerirHTML = '';
    if (isArea) {
        const st = act.me_estado || '';
        const checked = (st === 'pendiente' || st === 'aprobada') ? 'checked' : '';
        const disabled = st === 'aprobada' ? 'disabled' : '';
        let hint = 'Se envía como sugerencia; Secretaría la aprueba para que aparezca en la Agenda de la Mesa.';
        if (st === 'pendiente') hint = 'Sugerida — pendiente de aprobación de Secretaría.';
        else if (st === 'aprobada') hint = 'Aprobada — ya aparece en la Agenda de la Mesa. La seguís editando normalmente.';
        else if (st === 'rechazada') hint = 'Secretaría no la sumó a la Mesa. Podés volver a sugerirla marcando la casilla.';
        sugerirHTML = `
            <section>
                <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Agenda de la Mesa</h3>
                <label style="display: flex; align-items: center; gap: 0.6rem; cursor: ${disabled ? 'default' : 'pointer'}; font-weight: 600;">
                    <input type="checkbox" id="area-sugerir" ${checked} ${disabled} style="width: 18px; height: 18px;">
                    Sugerir esta actividad para la Agenda de Compromisos (Mesa)
                </label>
                <p style="font-size: 0.78rem; color: var(--text-muted); margin: 0.5rem 0 0;">${hint}</p>
            </section>`;
    }

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
                    <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                        Datos Generales
                        ${generalsReadOnly ? `<span style="text-transform: none; letter-spacing: 0; font-weight: 600; font-size: 0.7rem; color: #92400e; background: #fef3c7; border: 1px solid #fde68a; padding: 0.1rem 0.5rem; border-radius: 999px; display: inline-flex; align-items: center; gap: 0.3rem;"><i data-lucide="lock" style="width: 12px; height: 12px;"></i> ${actOrigen === 'area' ? 'La carga el área · solo lectura' : 'Los carga Secretaría · solo lectura'}</span>` : ''}
                    </h3>
                    <fieldset ${generalsReadOnly ? 'disabled' : ''} style="border: none; padding: 0; margin: 0; min-inline-size: auto;">
                    <label style="display: inline-flex; align-items: center; gap: 0.45rem; font-size: 0.85rem; cursor: pointer; margin-bottom: 0.85rem; user-select: none;">
                        <input type="checkbox" id="multiday-check" ${isMultiday ? 'checked' : ''} style="margin: 0; cursor: pointer;">
                        Dura varios días
                    </label>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label id="label-date">${isMultiday ? 'Desde' : 'Fecha'}</label>
                            <input type="date" name="date" value="${act.date}" required>
                        </div>
                        <div class="form-group" id="grp-end-date" style="display: ${isMultiday ? 'block' : 'none'};">
                            <label>Hasta</label>
                            <input type="date" name="end_date" value="${act.end_date}">
                        </div>
                    </div>
                    <div class="form-grid-2" style="margin-top: 1rem;">
                        <div class="form-group">
                            <label style="display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                                <span>Hora</span>
                                <span style="display: inline-flex; gap: 0.7rem; flex-wrap: wrap;">
                                    <label style="font-size: 0.75rem; font-weight: 400; color: var(--text-muted); cursor: pointer; display: inline-flex; align-items: center; gap: 0.3rem; user-select: none;">
                                        <input type="checkbox" id="time-tbd" ${timeIsTbd ? 'checked' : ''} style="margin: 0; cursor: pointer;">
                                        A definir
                                    </label>
                                    <label style="font-size: 0.75rem; font-weight: 400; color: var(--text-muted); cursor: pointer; display: inline-flex; align-items: center; gap: 0.3rem; user-select: none;">
                                        <input type="checkbox" id="time-none" ${timeIsNone ? 'checked' : ''} style="margin: 0; cursor: pointer;">
                                        Sin horario
                                    </label>
                                    <label style="font-size: 0.75rem; font-weight: 400; color: var(--text-muted); cursor: pointer; display: inline-flex; align-items: center; gap: 0.3rem; user-select: none;">
                                        <input type="checkbox" id="endtime-check" ${hasEndTime ? 'checked' : ''} style="margin: 0; cursor: pointer;">
                                        Hora de fin
                                    </label>
                                </span>
                            </label>
                            <input type="time" name="time" value="${timeDisabled ? '09:00' : act.time}" ${timeDisabled ? 'disabled style="opacity: 0.4;"' : ''}>
                        </div>
                        <div class="form-group" id="grp-end-time" style="display: ${hasEndTime ? 'block' : 'none'};">
                            <label>Hora de fin</label>
                            <input type="time" name="end_time" value="${act.end_time || '17:00'}">
                        </div>
                    </div>
                    <div class="form-group" style="margin-top: 1rem;">
                        <label>Título</label>
                        <input type="text" name="title" value="${escAttr(act.title)}" placeholder="Ej: Lanzamiento de..." required>
                    </div>
                    ${showGen(act.description) ? `
                    <div class="form-group" style="margin-top: 1rem;">
                        <label>Descripción</label>
                        <textarea name="description" rows="3">${escAttr(act.description)}</textarea>
                    </div>` : ''}
                    ${esArea ? (showGen(act.location) ? `
                    <div class="form-group" style="margin-top: 1rem;">
                        <label>Lugar</label>
                        <input type="text" name="location" value="${escAttr(act.location)}">
                    </div>` : '') : ((showGen(act.location) || showGen(act.observations)) ? `
                    <div class="form-grid-2" style="margin-top: 1rem;">
                        ${showGen(act.location) ? `<div class="form-group">
                            <label>Lugar</label>
                            <input type="text" name="location" value="${escAttr(act.location)}">
                        </div>` : ''}
                        ${showGen(act.observations) ? `<div class="form-group">
                            <label>Observaciones</label>
                            <input type="text" name="observations" value="${escAttr(act.observations)}">
                        </div>` : ''}
                    </div>` : '')}
                    ${showGen(act.participants) ? `
                    <div class="form-group" style="margin-top: 1rem;">
                        <label>${actOrigen === 'area' ? 'Participa (por el área)' : 'Participa'}</label>
                        <input type="text" name="participants" value="${escAttr(act.participants)}" placeholder="Ej: Juan Pérez, María García, Autoridades locales...">
                    </div>` : ''}
                    </fieldset>
                    ${participaMeHTML}
                    ${attachmentHTML}
                </section>

                ${estadoHTML}

                ${sugerirHTML}

                ${showOperative ? `
                ${showNotes ? `
                <section>
                    <h3 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Notas internas · Comunicación</h3>
                    <p style="font-size: 0.78rem; color: var(--text-muted); margin: -0.5rem 0 0.6rem;">Sólo las ve Comunicación. No aparecen en la landing ni para Secretaría.</p>
                    <textarea name="comunicacion_notes" rows="5" style="width: 100%; padding: 0.65rem 0.8rem; border: 1px solid var(--border); border-radius: 0.5rem; font-size: 0.95rem; line-height: 1.5; font-family: inherit; resize: vertical;">${escAttr(act.comunicacion_notes)}</textarea>
                </section>
                ` : ''}

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
                                <option value="Ana" ${act.responsible === 'Ana' ? 'selected' : ''}>Ana</option>
                                <option value="Nico" ${act.responsible === 'Nico' ? 'selected' : ''}>Nico</option>
                                <option value="Externo" ${act.responsible === 'Externo' ? 'selected' : ''}>Externo</option>
                            </select>
                        </div>
                        <div class="form-group" id="group-external" style="display: ${act.responsible === 'Externo' ? 'block' : 'none'};">
                            <label>Nombre Externo</label>
                            <input type="text" name="external_name" value="${escAttr(act.external_name)}">
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
                        <div style="display: flex; gap: 0.5rem;">
                            <input type="url" name="drive_bcr" id="input-drive-bcr" value="${escAttr(act.drive_bcr)}" placeholder="https://..." style="flex-grow: 1;">
                            <button type="button" id="btn-create-folder-bcr" class="btn-primary" style="background: #4285F4; border: none; padding: 0 0.75rem; border-radius: 6px; display: flex; align-items: center; justify-content: center;" title="Crear carpeta en Drive">
                                <i data-lucide="folder-plus" style="width: 18px; height: 18px;"></i>
                            </button>
                        </div>
                    </div>
                    <div class="form-group" id="group-santiago" style="margin-top: 1rem; display: none;">
                        <label>Link Drive Santiago</label>
                        <div style="display: flex; gap: 0.5rem;">
                            <input type="url" name="drive_santiago" id="input-drive-santiago" value="${escAttr(act.drive_santiago)}" placeholder="https://..." style="flex-grow: 1;">
                            <button type="button" id="btn-whatsapp-santiago" class="btn-primary" style="background: #25D366; border: none; padding: 0 0.75rem; border-radius: 6px; display: flex; align-items: center; justify-content: center;" title="Compartir por WhatsApp">
                                <i data-lucide="message-circle" style="width: 18px; height: 18px;"></i>
                            </button>
                        </div>
                    </div>

                    <div style="margin-top: 1.5rem; background: #f8fafc; padding: 1.5rem; border-radius: 0.5rem; border: 1px dashed var(--border);">
                        <div style="font-weight: 700; font-size: 0.9rem; margin-bottom: 1.25rem; color: var(--primary); text-transform: uppercase; letter-spacing: 0.05em;">COPYS DE DIFUSIÓN</div>

                        <div class="form-group">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                <label style="margin: 0;">Copy Instagram</label>
                                <button type="button" id="btn-copy-ig" class="btn-primary" style="width: auto; padding: 0.35rem 0.6rem; font-size: 0.75rem; background: #64748b; border-radius: 4px; display: flex; align-items: center; gap: 0.4rem;" title="Copiar al portapapeles">
                                    <i data-lucide="copy" style="width: 14px; height: 14px;"></i> Copiar
                                </button>
                            </div>
                            <textarea name="copy_instagram" id="copy-ig" rows="4" style="font-size: 0.85rem; border-radius: 6px;">${escAttr(act.copy_instagram)}</textarea>
                        </div>

                        <div class="form-group" style="margin-top: 1.5rem;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                <label style="margin: 0;">Copy LinkedIn / Conectados</label>
                                <button type="button" id="btn-copy-li" class="btn-primary" style="width: auto; padding: 0.35rem 0.6rem; font-size: 0.75rem; background: #64748b; border-radius: 4px; display: flex; align-items: center; gap: 0.4rem;" title="Copiar al portapapeles">
                                    <i data-lucide="copy" style="width: 14px; height: 14px;"></i> Copiar
                                </button>
                            </div>
                            <textarea name="copy_linkedin" id="copy-li" rows="6" style="font-size: 0.85rem; border-radius: 6px;">${escAttr(act.copy_linkedin)}</textarea>
                        </div>
                    </div>
                </section>
                ` : ''}
            </form>
        </div>

        <div class="sheet-footer" style="padding: 1.5rem; border-top: 1px solid var(--border); display: flex; gap: 1rem;">
            <button id="btn-save-activity" class="btn-primary">Guardar Cambios</button>
            ${(areaForeignForSec && act.me_estado === 'aprobada') ? '<button id="btn-revert-me" class="btn-primary" style="background:#b45309;">Quitar de la Mesa</button>' : ''}
            <button onclick="window.closeActivitySheet()" style="flex-grow: 1; background: white; border: 1px solid var(--border); border-radius: 0.5rem; font-weight: 600; cursor: pointer;">Cancelar</button>
            ${showDelete ? `<button id="btn-delete-activity-form" style="background: none; border: 1px solid #fca5a5; color: #ef4444; border-radius: 0.5rem; padding: 0 1rem; cursor: pointer; display: flex; align-items: center; justify-content: center;" title="Eliminar"><i data-lucide="trash-2"></i></button>` : ''}
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

    // --- Controles de hora: "A definir" | "Sin horario" | "Hora de fin" ---
    // "A definir" y "Sin horario" son excluyentes; cualquiera de las dos
    // deshabilita el input de hora y el rango horario.
    const timeTbd = container.querySelector('#time-tbd');
    const timeNone = container.querySelector('#time-none');
    const timeInput = container.querySelector('input[name="time"]');
    const endtimeCheck = container.querySelector('#endtime-check');
    const grpEndTime = container.querySelector('#grp-end-time');

    const syncTimeControls = () => {
        const noTime = (timeTbd && timeTbd.checked) || (timeNone && timeNone.checked);
        if (timeInput) {
            timeInput.disabled = noTime;
            timeInput.style.opacity = noTime ? '0.4' : '1';
        }
        if (endtimeCheck) {
            endtimeCheck.disabled = noTime;
            if (noTime && endtimeCheck.checked) {
                endtimeCheck.checked = false;
                if (grpEndTime) grpEndTime.style.display = 'none';
            }
        }
    };

    if (timeTbd) timeTbd.addEventListener('change', () => {
        if (timeTbd.checked && timeNone) timeNone.checked = false;
        syncTimeControls();
    });
    if (timeNone) timeNone.addEventListener('change', () => {
        if (timeNone.checked && timeTbd) timeTbd.checked = false;
        syncTimeControls();
    });
    if (endtimeCheck) endtimeCheck.addEventListener('change', () => {
        if (grpEndTime) grpEndTime.style.display = endtimeCheck.checked ? 'block' : 'none';
    });

    // Multi-día: el check alterna Fecha ↔ Desde/Hasta.
    const multidayCheck = container.querySelector('#multiday-check');
    if (multidayCheck) {
        const labelDate = container.querySelector('#label-date');
        const grpEndDate = container.querySelector('#grp-end-date');
        const endDateInput = container.querySelector('input[name="end_date"]');
        const startDateInput = container.querySelector('input[name="date"]');
        multidayCheck.addEventListener('change', () => {
            const on = multidayCheck.checked;
            labelDate.textContent = on ? 'Desde' : 'Fecha';
            grpEndDate.style.display = on ? 'block' : 'none';
            // Al activar, si no hay "Hasta", lo prellenamos con la fecha de inicio.
            if (on && endDateInput && !endDateInput.value && startDateInput) {
                endDateInput.value = startDateInput.value;
            }
        });
    }

    // Todo el wiring operativo sólo aplica a Comunicación (en modo Secretaría
    // estos elementos no existen en el DOM).
    if (showOperative) {
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

        const txtIg = container.querySelector('#copy-ig');
        const txtLi = container.querySelector('#copy-li');

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
    }

    // --- Estado: mostrar el campo "Otro" cuando corresponde (sólo Secretaría) ---
    const secRespSelect = container.querySelector('#sec-resp-select');
    if (secRespSelect) {
        const otherGroup = container.querySelector('#sec-resp-other-group');
        secRespSelect.onchange = () => {
            otherGroup.style.display = secRespSelect.value === 'Otro' ? 'block' : 'none';
        };
    }

    // --- Adjunto: subir/cambiar/quitar (sólo Secretaría) ---
    // getAttachment devuelve el adjunto vigente al guardar. Default: el que ya
    // tenía la actividad (para no perderlo cuando el form no lo edita).
    let getAttachment = () => ({ attachment_url: act.attachment_url || '', attachment_name: act.attachment_name || '' });
    if ((isSec && !areaForeignForSec) || isArea) {
        const attachInput = container.querySelector('#attach-input');
        const attachArea = container.querySelector('#attach-area');
        let attachUrl = act.attachment_url || '';
        let attachNm = act.attachment_name || '';

        const renderAttachArea = () => {
            if (attachUrl) {
                attachArea.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
                        <a href="${attachUrl}" target="_blank" rel="noopener" style="display: inline-flex; align-items: center; gap: 0.4rem; color: var(--primary); font-size: 0.9rem; font-weight: 500; text-decoration: none;">
                            <i data-lucide="paperclip" style="width: 15px; height: 15px;"></i> ${(attachNm || 'archivo adjunto').replace(/</g, '&lt;')}
                        </a>
                        <button type="button" id="attach-replace" style="background: white; border: 1px solid var(--border); padding: 0.35rem 0.6rem; border-radius: 0.4rem; font-size: 0.8rem; cursor: pointer;">Cambiar</button>
                        <button type="button" id="attach-remove" style="background: none; border: none; color: #ef4444; font-size: 0.8rem; cursor: pointer;">Quitar</button>
                    </div>`;
            } else {
                attachArea.innerHTML = `
                    <button type="button" id="attach-add" style="background: white; border: 1px dashed var(--border); color: var(--text-muted); padding: 0.55rem 0.85rem; border-radius: 0.5rem; font-size: 0.85rem; cursor: pointer; display: inline-flex; align-items: center; gap: 0.4rem;">
                        <i data-lucide="paperclip" style="width: 15px; height: 15px;"></i> Adjuntar archivo
                    </button>`;
            }
            const add = attachArea.querySelector('#attach-add');
            const rep = attachArea.querySelector('#attach-replace');
            const rem = attachArea.querySelector('#attach-remove');
            if (add) add.onclick = () => attachInput.click();
            if (rep) rep.onclick = () => attachInput.click();
            if (rem) rem.onclick = () => { attachUrl = ''; attachNm = ''; renderAttachArea(); };
            if (window.lucide) window.lucide.createIcons();
        };

        attachInput.onchange = async () => {
            if (!attachInput.files.length) return;
            const f = attachInput.files[0];
            const fd = new FormData();
            fd.append('file', f);
            attachArea.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">Subiendo…</span>';
            try {
                const res = await fetch('/api/agenda/upload-file', { method: 'POST', body: fd });
                const data = await res.json();
                if (res.ok && data.url) {
                    attachUrl = data.url;
                    attachNm = data.name || f.name;
                } else {
                    alert(data.detail || 'No se pudo subir el archivo.');
                }
            } catch (e) {
                console.error(e);
                alert('Error al subir el archivo.');
            } finally {
                attachInput.value = '';
                renderAttachArea();
            }
        };

        renderAttachArea();
        getAttachment = () => ({ attachment_url: attachUrl, attachment_name: attachNm });
    }

    // Drive Folder Creation logic
    const btnCreateFolder = container.querySelector('#btn-create-folder-bcr');
    if (btnCreateFolder) {
        btnCreateFolder.onclick = async () => {
            if (!act.id) {
                alert('Primero guardá la actividad para poder crear la carpeta.');
                return;
            }
            
            btnCreateFolder.disabled = true;
            btnCreateFolder.innerHTML = '<span style="font-size: 0.7rem;">...</span>';
            
            try {
                const response = await fetch(`/api/agenda/actividades/${act.id}/create-folder`, { method: 'POST' });
                const result = await response.json();
                
                if (response.ok) {
                    container.querySelector('#input-drive-bcr').value = result.link;
                    // Actualizamos el objeto local por si guardan de nuevo
                    act.drive_bcr = result.link;
                    alert('✅ Carpeta creada exitosamente en Google Drive.');
                } else {
                    alert('Error: ' + (result.detail || 'No se pudo crear la carpeta.'));
                }
            } catch (e) {
                console.error(e);
                alert('Hubo un problema al conectar con el servidor.');
            } finally {
                btnCreateFolder.disabled = false;
                btnCreateFolder.innerHTML = '<i data-lucide="folder-plus" style="width: 18px; height: 18px;"></i>';
                if (window.lucide) window.lucide.createIcons();
            }
        };
    }

    // WhatsApp logic
    const btnWpp = container.querySelector('#btn-whatsapp-santiago');
    if (btnWpp) {
        btnWpp.onclick = async () => {
            const link = form.drive_santiago.value;
            if (!link) {
                alert('Primero ingresa el link de Santiago.');
                return;
            }
            
            // Si la actividad ya tiene ID (ya fue guardada antes), disparamos el circuito automático
            if (act.id) {
                btnWpp.disabled = true;
                const originalContent = btnWpp.innerHTML;
                btnWpp.innerHTML = '<span style="font-size: 0.7rem;">...</span>';
                
                try {
                    const response = await fetch(`/api/agenda/actividades/${act.id}/notify-santiago`, { 
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ drive_santiago: link })
                    });
                    if (response.ok) {
                        alert('✅ ¡Aviso enviado al grupo de WhatsApp!');
                    } else {
                        const err = await response.json();
                        alert('Error: ' + (err.detail || 'No se pudo enviar el aviso.'));
                    }
                } catch (e) {
                    console.error(e);
                    alert('Hubo un problema al conectar con el servidor.');
                } finally {
                    btnWpp.disabled = false;
                    btnWpp.innerHTML = originalContent;
                }
            } else {
                alert('Primero guardá la actividad para que el sistema pueda generar el aviso automático.');
            }
        };
    }

    // Save logic (no existe en modo solo-lectura de Secretaría sobre área)
    const saveBtnEl = container.querySelector('#btn-save-activity');
    if (saveBtnEl) saveBtnEl.onclick = async () => {
        const formData = new FormData(form);

        // Datos Generales (sólo se incluyen si el rol puede editarlos).
        const isMulti = !!(multidayCheck && multidayCheck.checked);
        const hasEnd = !!(endtimeCheck && endtimeCheck.checked);
        const timeVal = (timeNone && timeNone.checked) ? 'Sin horario'
            : (timeTbd && timeTbd.checked) ? 'A definir'
            : formData.get('time');
        const noClock = (timeVal === 'A definir' || timeVal === 'Sin horario');
        const generalsData = {
            date: formData.get('date'),
            time: timeVal,
            // end_date sólo si es multi-día; end_time sólo si hay rango horario y
            // hay una hora real (no aplica con "A definir" ni "Sin horario").
            end_date: isMulti ? (formData.get('end_date') || '') : '',
            end_time: (hasEnd && !noClock) ? (formData.get('end_time') || '') : '',
            title: formData.get('title'),
            description: formData.get('description'),
            location: formData.get('location'),
            observations: formData.get('observations'),
            participants: formData.get('participants'),
        };

        if (generalsData.end_date && generalsData.end_date < generalsData.date) {
            alert('La fecha "Hasta" no puede ser anterior a "Desde".');
            return;
        }

        let data;
        if (areaForeignForSec) {
            // Secretaría sobre una actividad de área: "Participa (por Mesa
            // Ejecutiva)" + INTERNO (Responsable + Notas). NO toca el contenido
            // del área ni el estado de avance; el backend ignora lo demás.
            data = {
                participants_me: formData.get('participants_me') || '',
                sec_responsible: formData.get('sec_responsible') || '',
                sec_responsible_other: formData.get('sec_responsible') === 'Otro' ? (formData.get('sec_responsible_other') || '') : '',
                sec_notes: formData.get('sec_notes') || '',
            };
        } else if (isSec) {
            // Secretaría: Datos Generales + sección Estado + adjunto. La
            // actividad es suya.
            const att = getAttachment();
            data = {
                ...generalsData,
                origen: 'secretaria',
                estado: formData.get('estado') || 'Pendiente',
                sec_responsible: formData.get('sec_responsible') || '',
                sec_responsible_other: formData.get('sec_responsible') === 'Otro' ? (formData.get('sec_responsible_other') || '') : '',
                attachment_url: att.attachment_url,
                attachment_name: att.attachment_name,
            };
        } else if (isArea) {
            // Área: Datos Generales + adjunto + estado de sugerencia a la Mesa.
            const att = getAttachment();
            const sug = container.querySelector('#area-sugerir');
            // No se puede "des-aprobar" desde el área: si ya está aprobada, queda.
            let me_estado = act.me_estado || '';
            if (me_estado !== 'aprobada') {
                me_estado = (sug && sug.checked) ? 'pendiente' : '';
            }
            data = {
                ...generalsData,
                origen: 'area',
                area: areaSlug,
                attachment_url: att.attachment_url,
                attachment_name: att.attachment_name,
                me_estado,
            };
        } else {
            // Comunicación: siempre lo operativo + notas internas.
            const selectedChannels = Array.from(form.querySelectorAll('input[name="channels"]:checked'))
                .map(cb => cb.value);
            data = {
                responsible: formData.get('responsible'),
                external_name: formData.get('external_name'),
                channels: selectedChannels,
                done: formData.get('done') === 'on',
                drive_bcr: formData.get('drive_bcr'),
                drive_santiago: formData.get('drive_santiago'),
                copy_instagram: formData.get('copy_instagram'),
                copy_linkedin: formData.get('copy_linkedin'),
                story_type: formData.get('story_type'),
            };
            // Notas internas: sólo se manda si el campo existe (actividad de
            // Secretaría). En las nativas no se muestra, así que no lo pisamos.
            const notesField = form.querySelector('[name="comunicacion_notes"]');
            if (notesField) data.comunicacion_notes = notesField.value;
            // Los Datos Generales sólo se mandan si Comunicación es dueña de
            // ellos (actividad propia o nueva). En las de Secretaría quedan
            // intactos: no se incluyen, así el backend no los pisa.
            if (generalsEditable) {
                Object.assign(data, generalsData, { origen: 'comunicacion' });
            }
        }

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

    // Secretaría: revertir una actividad de área ya aprobada (sacarla de la Mesa).
    const revertBtn = container.querySelector('#btn-revert-me');
    if (revertBtn) revertBtn.onclick = async () => {
        if (!confirm('¿Quitar esta actividad de la Agenda de la Mesa? Vuelve a "pendiente" para que la revises en la bandeja.')) return;
        revertBtn.disabled = true;
        await updateActivity(act.id, { me_estado: 'pendiente' });
        window.closeActivitySheet();
    };

    if (showDelete) {
        container.querySelector('#btn-delete-activity-form').onclick = () => {
            if (confirm('¿Estás seguro de que querés eliminar esta actividad? Esta acción no se puede deshacer.')) {
                deleteActivity(act.id);
                window.closeActivitySheet();
            }
        };
    }
}

// --- Formulario mínimo para el rol Audiovisual (Santiago) -------------------
// Ve la actividad en solo lectura y sólo puede editar el link de video
// (drive_santiago). Se usa desde la pestaña "Santi".
function renderAudiovisualForm(container, act) {
    const row = (label, value) => value && String(value).trim() !== '' ? `
        <div class="form-group" style="margin-top: 1rem;">
            <label style="font-size: 0.8rem; color: var(--text-muted);">${label}</label>
            <div style="font-size: 0.95rem; color: var(--text);">${escAttr(value)}</div>
        </div>` : '';

    const fecha = act.end_date && act.end_date > act.date
        ? `${act.date} → ${act.end_date}` : act.date;
    const hora = act.time;

    // ¿Esta actividad requiere una tarea de video? (misma lógica que la pestaña
    // Santi: IG Story en Video —no Layout— o YouTube). Sólo en ese caso Santi
    // edita el link; si no, la ve en solo lectura.
    const channels = act.channels || [];
    const needsVideo = (channels.includes('Instagram Story') && act.story_type !== 'Layout')
        || channels.includes('YouTube');

    // Link Drive Cobertura BCR (material de cobertura): solo lectura para Santi.
    const driveBcrBlock = act.drive_bcr ? `
                <div class="form-group" style="margin-top: 1rem;">
                    <label style="font-size: 0.8rem; color: var(--text-muted);">Link Drive Cobertura BCR</label>
                    <div><a href="${escAttr(act.drive_bcr)}" target="_blank" rel="noopener" style="color: var(--primary); font-size: 0.9rem; font-weight: 600; display: inline-flex; align-items: center; gap: 0.35rem;"><i data-lucide="folder" style="width: 15px; height: 15px;"></i> Abrir carpeta de cobertura</a></div>
                </div>` : '';

    // Copy Instagram: solo lectura, con botón para copiarlo.
    const copyIgBlock = act.copy_instagram ? `
                <div class="form-group" style="margin-top: 1.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <label style="font-size: 0.8rem; color: var(--text-muted); margin: 0;">Copy Instagram</label>
                        <button type="button" id="btn-copy-ig-av" style="width: auto; padding: 0.3rem 0.6rem; font-size: 0.75rem; background: #64748b; color: white; border: none; border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 0.35rem;"><i data-lucide="copy" style="width: 13px; height: 13px;"></i> Copiar</button>
                    </div>
                    <textarea readonly rows="5" style="width: 100%; padding: 0.65rem 0.8rem; border: 1px solid var(--border); border-radius: 0.5rem; font-size: 0.85rem; line-height: 1.5; font-family: inherit; resize: vertical; background: #f8fafc;">${escAttr(act.copy_instagram)}</textarea>
                </div>` : '';

    // Bloque del link de video: editable si requiere video; si no, sólo se
    // muestra el link cargado (si hay) y una aclaración.
    const videoBlock = needsVideo ? `
                <div class="form-group" style="margin-top: 1.5rem; background: #eef2ff; padding: 1.25rem; border-radius: 0.5rem; border: 1px solid #c7d2fe;">
                    <label style="font-weight: 700; color: var(--primary);">Link del video (Drive)</label>
                    <p style="font-size: 0.78rem; color: var(--text-muted); margin: 0.25rem 0 0.6rem;">Esta actividad requiere video. Cargá el link acá; es lo único que podés editar.</p>
                    <input type="url" name="drive_santiago" value="${escAttr(act.drive_santiago)}" placeholder="https://drive.google.com/..." style="width: 100%;">
                </div>` : `
                <div class="form-group" style="margin-top: 1.5rem; background: #f8fafc; padding: 1rem 1.25rem; border-radius: 0.5rem; border: 1px dashed var(--border);">
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">Esta actividad no requiere video.</p>
                    ${act.drive_santiago ? `<div style="margin-top: 0.5rem;"><a href="${escAttr(act.drive_santiago)}" target="_blank" rel="noopener" style="color: var(--primary); font-size: 0.9rem;">Ver video cargado</a></div>` : ''}
                </div>`;

    container.innerHTML = `
        <div class="sheet-header" style="padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
            <h2 style="font-weight: 700;">${needsVideo ? 'Tarea de video' : 'Actividad'}</h2>
            <button onclick="window.closeActivitySheet()" style="background: none; border: none; cursor: pointer; color: var(--text-muted);">
                <i data-lucide="x"></i>
            </button>
        </div>

        <div class="sheet-body" style="flex-grow: 1; overflow-y: auto; padding: 1.5rem;">
            <form id="form-av" style="display: flex; flex-direction: column; gap: 0.25rem;">
                <div class="form-group">
                    <label style="font-size: 0.8rem; color: var(--text-muted);">Título</label>
                    <div style="font-size: 1.05rem; font-weight: 700; color: var(--text);">${escAttr(act.title) || '(sin título)'}</div>
                </div>
                ${row('Fecha', fecha)}
                ${row('Hora', hora)}
                ${row('Lugar', act.location)}
                ${row('Descripción', act.description)}
                ${driveBcrBlock}
                ${videoBlock}
                ${copyIgBlock}
            </form>
        </div>

        <div class="sheet-footer" style="padding: 1.5rem; border-top: 1px solid var(--border); display: flex; gap: 1rem;">
            ${needsVideo ? '<button id="btn-save-av" class="btn-primary">Guardar link</button>' : ''}
            <button onclick="window.closeActivitySheet()" style="flex-grow: 1; background: white; border: 1px solid var(--border); border-radius: 0.5rem; font-weight: 600; cursor: pointer;">Cerrar</button>
        </div>
    `;

    if (window.lucide) window.lucide.createIcons();

    // Copiar el Copy de Instagram al portapapeles.
    const btnCopyIg = container.querySelector('#btn-copy-ig-av');
    if (btnCopyIg) btnCopyIg.onclick = () => {
        navigator.clipboard.writeText(act.copy_instagram || '');
        const orig = btnCopyIg.innerHTML;
        btnCopyIg.innerHTML = 'Copiado ✓';
        setTimeout(() => { btnCopyIg.innerHTML = orig; if (window.lucide) window.lucide.createIcons(); }, 1500);
    };

    const form = container.querySelector('#form-av');
    const btnSave = container.querySelector('#btn-save-av');
    if (btnSave) btnSave.onclick = async () => {
        if (!act.id) { window.closeActivitySheet(); return; }
        const originalText = btnSave.innerText;
        btnSave.disabled = true;
        btnSave.innerText = 'Guardando...';
        try {
            await updateActivity(act.id, { drive_santiago: form.drive_santiago.value });
            window.closeActivitySheet();
        } catch (error) {
            alert('Error al guardar: ' + error.message);
            btnSave.disabled = false;
            btnSave.innerText = originalText;
        }
    };
}
