export const state = {
    view: 'list',
    showPast: false,
    activities: [],
    currentActivity: null,
    searchQuery: ''
};

// Cargar actividades desde el servidor
export async function loadActivities() {
    try {
        const response = await fetch('/api/agenda/actividades');
        if (response.ok) {
            state.activities = await response.json();
            notify();
        } else {
            console.error('Error fetching activities');
        }
    } catch (error) {
        console.error('Network error loading activities:', error);
    }
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
        channels: Array.isArray(activity.channels) ? activity.channels : []
    };
}

export async function addActivity(activity) {
    const newActivity = {
        ...sanitizeActivity(activity),
        id: Date.now().toString(),
        done: false
    };
    
    // Optimistic update
    state.activities.push(newActivity);
    notify();

    // Persist
    try {
        await fetch('/api/agenda/actividades', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newActivity)
        });
    } catch (e) {
        console.error("Failed to add activity to server", e);
    }
    
    return newActivity;
}

export async function updateActivity(id, updates, shouldNotify = true) {
    const index = state.activities.findIndex(a => a.id === id);
    if (index !== -1) {
        // Optimistic update
        const updatedActivity = { ...state.activities[index], ...sanitizeActivity(updates) };
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
