export const state = {
    view: 'list',
    showPast: false,
    activities: [
        {
            id: '1',
            date: '2026-04-20',
            time: '10:00',
            title: 'Reunión de Equipo - Agenda Semanal',
            description: 'Coordinación de temas de prensa y redes.',
            responsible: 'Paku',
            channels: ['LinkedIn', 'Conectados'],
            conectados_title: 'Estrategia y Gestión: El equipo de Comunicación define los ejes de la semana',
            conectados_text: 'En una nueva reunión de coordinación, se establecieron las prioridades de prensa y contenidos digitales para los próximos días.',
            done: false
        },
        {
            id: '2',
            date: '2026-04-20',
            time: '15:00',
            title: 'Grabación Podcast Institucional',
            description: 'Entrevista al Director sobre innovación agropecuaria.',
            responsible: 'Juan',
            channels: ['Spotify', 'YouTube'],
            done: false
        },
        {
            id: '3',
            date: '2026-04-21',
            time: '09:00',
            title: 'Conferencia de Prensa - Reporte Lluvia',
            description: 'Presentación de datos climáticos ante medios locales.',
            responsible: 'Lucía',
            channels: ['X', 'Prensa'],
            done: false
        },
        {
            id: '4',
            date: '2026-04-21',
            time: '14:00',
            title: 'Revisión de Métricas Mensuales',
            description: 'Análisis de impacto en redes sociales del mes pasado.',
            responsible: 'Paula',
            channels: ['Reporte Interno'],
            done: false
        },
        {
            id: '5',
            date: '2026-04-23',
            time: '11:00',
            title: 'Lanzamiento Nueva Web Institucional',
            description: 'Publicación oficial del sitio renovado.',
            responsible: 'Equipo IT / Comms',
            channels: ['Todos los canales'],
            conectados_title: 'Transformación Digital: La BCR estrena una renovada plataforma web institucional',
            conectados_text: 'Ya se encuentra online el sitio oficial rediseñado, con una experiencia de usuario optimizada para el sector.',
            done: false
        },
        {
            id: '6',
            date: '2026-04-25',
            time: '10:00',
            title: 'Evento: Puertas Abiertas BCR',
            description: 'Visita guiada para estudiantes universitarios.',
            responsible: 'Juan',
            channels: ['Instagram', 'Conectados'],
            conectados_title: 'Vinculación Universitaria: Estudiantes recorrieron las instalaciones de la Bolsa',
            conectados_text: 'En el marco del programa de Puertas Abiertas, recibimos a futuros profesionales interesados en los mercados y la tecnología.',
            done: false
        },
        {
            id: '7',
            date: '2026-04-27',
            time: '16:00',
            title: 'Capacitación Vocería en Crisis',
            description: 'Taller práctico para el equipo de directores.',
            responsible: 'Consultora Externa',
            channels: ['Interno'],
            done: false
        },
        {
            id: '8',
            date: '2026-05-02',
            time: '09:00',
            title: 'Planificación Estratégica Trimestral',
            description: 'Definición de objetivos para el segundo trimestre.',
            responsible: 'Directores',
            channels: ['Estrategia'],
            done: false
        },
        {
            id: '9',
            date: '2026-05-15',
            time: '12:00',
            title: 'Aniversario Institucional - Evento Central',
            description: 'Celebración por los 140 años de la institución.',
            responsible: 'Paku',
            channels: ['Streaming', 'Prensa', 'Social'],
            done: false
        },
        {
            id: '10',
            date: '2026-04-20',
            time: '08:30',
            title: 'Chequeo de Mails Matutino',
            description: 'Tarea ya realizada a primera hora.',
            responsible: 'Juan',
            channels: ['Mail a asociados', 'LinkedIn', 'X', 'Conectados'],
            done: true
        }
    ],
    currentActivity: null,
    searchQuery: ''
};

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

export function addActivity(activity) {
    const newActivity = {
        ...sanitizeActivity(activity),
        id: Date.now().toString(),
        done: false
    };
    state.activities.push(newActivity);
    notify();
    return newActivity;
}

export function updateActivity(id, updates, shouldNotify = true) {
    const index = state.activities.findIndex(a => a.id === id);
    if (index !== -1) {
        state.activities[index] = { ...state.activities[index], ...sanitizeActivity(updates) };
        if (shouldNotify) notify();
    }
}

export function deleteActivity(id) {
    state.activities = state.activities.filter(a => a.id !== id);
    notify();
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
