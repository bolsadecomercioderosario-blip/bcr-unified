export const state = {
    view: 'list',
    showPast: false,
    pastMonthsVisible: 1,
    activities: [],
    efemerides: [],
    currentActivity: null,
    searchQuery: ''
};

// Cargar actividades desde el servidor.
// Si `silent` es true, sólo notifica si hay cambios reales — útil para polling
// para no re-renderizar la UI (y romper foco / drag) cuando nada cambió.
export async function loadActivities({ silent = false } = {}) {
    try {
        const response = await fetch('/api/agenda/actividades');
        if (response.ok) {
            const incoming = await response.json();
            const changed = JSON.stringify(state.activities) !== JSON.stringify(incoming);
            state.activities = incoming;
            if (!silent || changed) notify();
        } else {
            console.error('Error fetching activities');
        }
    } catch (error) {
        console.error('Network error loading activities:', error);
    }
}

// Cargar efemérides desde el servidor (misma lógica de silent / diff)
export async function loadEfemerides({ silent = false } = {}) {
    try {
        const response = await fetch('/api/agenda/efemerides');
        if (response.ok) {
            const incoming = await response.json();
            const changed = JSON.stringify(state.efemerides) !== JSON.stringify(incoming);
            state.efemerides = incoming;
            if (!silent || changed) notify();
        } else {
            console.error('Error fetching efemérides');
        }
    } catch (error) {
        console.error('Network error loading efemérides:', error);
    }
}

export async function addEfemeride(payload) {
    try {
        const res = await fetch('/api/agenda/efemerides', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const created = await res.json();
            state.efemerides.push(created);
            state.efemerides.sort((a, b) => a.mes - b.mes || a.dia - b.dia);
            notify();
            return created;
        }
    } catch (e) { console.error("addEfemeride", e); }
}

export async function updateEfemeride(id, updates) {
    try {
        const res = await fetch(`/api/agenda/efemerides/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        if (res.ok) {
            const updated = await res.json();
            const idx = state.efemerides.findIndex(e => e.id === id);
            if (idx !== -1) state.efemerides[idx] = updated;
            state.efemerides.sort((a, b) => a.mes - b.mes || a.dia - b.dia);
            notify();
        }
    } catch (e) { console.error("updateEfemeride", e); }
}

export async function deleteEfemeride(id) {
    try {
        const res = await fetch(`/api/agenda/efemerides/${id}`, { method: 'DELETE' });
        if (res.ok) {
            state.efemerides = state.efemerides.filter(e => e.id !== id);
            notify();
        }
    } catch (e) { console.error("deleteEfemeride", e); }
}

export const listeners = [];

export function subscribe(callback) {
    listeners.push(callback);
}

export function notify() {
    listeners.forEach(cb => cb(state));
}

export function setView(viewName) {
    state.view = viewName;
    notify();
}

function sanitizeActivity(activity) {
    return {
        ...activity,
        location: (activity.location === 'undefined' || !activity.location) ? '' : activity.location,
        observations: (activity.observations === 'undefined' || !activity.observations) ? '' : activity.observations,
        participants: activity.participants || '',
        story_type: activity.story_type || 'Video',
        is_custom: activity.is_custom || false,
        image_url: activity.image_url || '',
        channels: Array.isArray(activity.channels) ? activity.channels : []
    };
}

export async function addActivity(activity) {
    const newActivity = {
        ...sanitizeActivity(activity),
        id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
        done: false
    };
    
    // Optimistic update
    state.activities.push(newActivity);
    notify();

    // Persist
    try {
        const response = await fetch('/api/agenda/actividades', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newActivity)
        });
        if (response.ok) {
            const savedActivity = await response.json();
            // Update the optimistic entry with data from the server (like the generated Drive link)
            const index = state.activities.findIndex(a => a.id === newActivity.id);
            if (index !== -1) {
                state.activities[index] = { ...state.activities[index], ...savedActivity };
                notify();
            }
        }
    } catch (e) {
        console.error("Failed to add activity to server", e);
    }
    
    return newActivity;
}

export async function updateActivity(id, updates, shouldNotify = true) {
    const index = state.activities.findIndex(a => a.id === id);
    if (index !== -1) {
        // Optimistic update
        const updatedActivity = sanitizeActivity({ ...state.activities[index], ...updates });
        state.activities[index] = updatedActivity;
        if (shouldNotify) notify();

        // Persist
        try {
            await fetch(`/api/agenda/actividades/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
        } catch (e) {
            console.error("Failed to update activity on server", e);
        }
    }
}

export async function deleteActivity(id) {
    // Optimistic update
    state.activities = state.activities.filter(a => a.id !== id);
    notify();

    // Persist
    try {
        await fetch(`/api/agenda/actividades/${id}`, {
            method: 'DELETE'
        });
    } catch (e) {
        console.error("Failed to delete activity on server", e);
    }
}

export function setCurrentActivity(activity) {
    state.currentActivity = activity;
    notify();
}

export function setSearchQuery(query) {
    state.searchQuery = query;
    notify();
}

export function toggleShowPast() {
    state.showPast = !state.showPast;
    if (!state.showPast) {
        // Reset al cerrar para que la próxima vez arranque mostrando solo 1 mes
        state.pastMonthsVisible = 1;
    }
    notify();
}

export function expandPastMonths() {
    state.pastMonthsVisible += 1;
    notify();
}

export function suggestJournalisticTitle(activity) {
    const text = (activity.title + ' ' + activity.description).toLowerCase();
    
    if (text.includes('web') || text.includes('it') || text.includes('digital')) 
        return `Transformación Digital: La BCR renueva su plataforma institucional`;
    if (text.includes('estudiantes') || text.includes('visita') || text.includes('puertas'))
        return `Vinculación con el Futuro: Estudiantes de la región conocieron el corazón de la Bolsa`;
    if (text.includes('reunión') || text.includes('agenda') || text.includes('coordinación'))
        return `Estrategia y Gestión: Definimos los ejes comunicacionales de la semana`;
    if (text.includes('podcast') || text.includes('grabación'))
        return `Contenidos BCR: Nuevo episodio sobre actualidad y tecnología agropecuaria`;
    if (text.includes('clima') || text.includes('lluvia') || text.includes('reporte') || text.includes('conferencia'))
        return `Información de Calidad: Presentación de nuevo reporte agrometeorológico para el sector`;
    
    // Default journalistic templates
    const templates = [
        `Hito Institucional: BCR lidera nueva iniciativa de impacto local`,
        `Comunicación Estratégica: Avances en la gestión de contenidos BCR`,
        `Presencia en el Sector: BCR participa en eventos clave de la semana`,
        `Compromiso Institucional: Fortalecemos los lazos con la comunidad agro`
    ];
    
    return templates[Math.floor(Math.random() * templates.length)];
}
