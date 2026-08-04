import { state, subscribe, setView, setCurrentActivity, setSearchQuery, toggleShowPast, loadActivities, loadEfemerides, loadNewsletterSettings } from './state.js';
import { renderList } from './components/List.js';
import { renderConectados } from './components/Conectados.js';
import { renderSanti } from './components/Santi.js';
import { renderActivityForm } from './components/ActivityForm.js';
import { renderAgendaCompromisos } from './components/AgendaCompromisos.js';
import { renderEfemeridesModal } from './components/EfemeridesModal.js';
import { renderArchivedModal } from './components/ArchivedModal.js';
import { getRole, isSecretaria } from './role.js';

// Rol del usuario (secretaria | comunicacion). Lo exponemos en el <body> para
// que el CSS muestre/oculte la nav que corresponde a cada rol.
const ROLE = getRole();
document.body.dataset.role = ROLE;

// Vistas permitidas por rol. Secretaría sólo ve la Agenda de Compromisos.
const ALLOWED_VIEWS = ROLE === 'secretaria'
    ? ['compromisos']
    : ['list', 'conectados', 'santi'];

// La vista inicial depende del rol.
state.view = ROLE === 'secretaria' ? 'compromisos' : 'list';

const viewContainer = document.getElementById('view-container');
const btnNewActivity = document.getElementById('btn-new-activity');
const btnTogglePast = document.getElementById('btn-toggle-past');
const btnEfemerides = document.getElementById('btn-efemerides');
const btnArchived = document.getElementById('btn-archived');
const activitySheet = document.getElementById('activity-sheet');
const efemeridesSheet = document.getElementById('efemerides-sheet');
const archivedSheet = document.getElementById('archived-sheet');
const globalSearch = document.getElementById('global-search');

// Recordamos qué vista se renderizó por última vez para saber si un re-render
// es "en el lugar" (misma vista → preservar scroll) o un cambio de vista (ir arriba).
let lastRenderedView = null;

// Router/View Switcher
function updateUI() {
    // Guardamos la posición de scroll ANTES de reconstruir la lista. Abrir/guardar
    // una actividad dispara un re-render; sin esto, la lista vuelve al inicio y se
    // pierde el lugar donde estabas.
    const sameView = (state.view === lastRenderedView);
    const prevScroll = viewContainer ? viewContainer.scrollTop : 0;

    const navItems = document.querySelectorAll('.nav-item');

    // Expose current view on <body> for view-conditional styles (e.g. mobile)
    document.body.dataset.view = state.view;

    // Update Navigation Active State
    navItems.forEach(item => {
        if (item.dataset.view === state.view) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Update Toggle Icon
    if (btnTogglePast) {
        btnTogglePast.innerHTML = state.showPast ? 
            '<i data-lucide="history"></i>' : 
            '<i data-lucide="calendar-x"></i>';
        btnTogglePast.title = state.showPast ? "Ocultar Pasadas" : "Ver Pasadas (Historial)";
        btnTogglePast.style.color = state.showPast ? "var(--primary)" : "var(--text-muted)";
        btnTogglePast.style.backgroundColor = state.showPast ? "#eef2ff" : "transparent";
    }

    // Render current view
    viewContainer.innerHTML = '';
    
    // Show/Hide search and history/efemerides controls only in 'list' view
    const searchBox = document.querySelector('.search-box');
    if (searchBox) {
        searchBox.style.display = state.view === 'list' ? 'flex' : 'none';
    }
    if (btnTogglePast) {
        btnTogglePast.style.display = state.view === 'list' ? 'flex' : 'none';
    }
    if (btnEfemerides) {
        btnEfemerides.style.display = state.view === 'list' ? 'flex' : 'none';
    }

    switch (state.view) {
        case 'list':
            renderList(viewContainer);
            break;
        case 'conectados':
            renderConectados(viewContainer);
            break;
        case 'santi':
            renderSanti(viewContainer);
            break;
        case 'compromisos':
            renderAgendaCompromisos(viewContainer);
            break;
    }

    // Update Lucide Icons
    if (window.lucide) {
        window.lucide.createIcons();
    }

    // Restaurar el scroll: si seguimos en la misma vista (re-render por editar,
    // guardar o polling), volvemos a donde estabas; si cambiaste de vista, arriba.
    if (viewContainer) {
        viewContainer.scrollTop = sameView ? prevScroll : 0;
    }
    lastRenderedView = state.view;
}

// Event Listeners
document.addEventListener('click', (e) => {
    const navItem = e.target.closest('.nav-item');
    if (navItem) {
        // Guard: Secretaría sólo puede ir a sus vistas permitidas.
        if (!ALLOWED_VIEWS.includes(navItem.dataset.view)) return;
        setView(navItem.dataset.view);
    }
});

btnNewActivity.addEventListener('click', () => {
    setCurrentActivity(null);
    openActivitySheet();
});

// Abrir el form de "Nueva actividad" desde cualquier vista (lo usa el botón
// de la Agenda de Compromisos del rol Secretaría).
window.openNewActivity = () => {
    setCurrentActivity(null);
    openActivitySheet();
};

if (btnTogglePast) {
    btnTogglePast.addEventListener('click', () => {
        toggleShowPast();
    });
}

if (btnEfemerides) {
    btnEfemerides.addEventListener('click', () => {
        openEfemeridesSheet();
    });
}

function openEfemeridesSheet() {
    efemeridesSheet.classList.remove('hidden');
    renderEfemeridesModal(efemeridesSheet.querySelector('.sheet-content'));
}

export function closeEfemeridesSheet() {
    efemeridesSheet.classList.add('hidden');
}

// --- Archivados (soft-deleted) ---
// Expuesto global para poder abrirlo también desde la vista de Secretaría
// (Agenda de Compromisos), que tiene su propio header y oculta el top-bar.
function openArchivedSheet() {
    archivedSheet.classList.remove('hidden');
    renderArchivedModal(archivedSheet.querySelector('.sheet-content'));
}
window.openArchivedSheet = openArchivedSheet;

if (btnArchived) {
    btnArchived.addEventListener('click', openArchivedSheet);
}

export function closeArchivedSheet() {
    archivedSheet.classList.add('hidden');
}
window.closeArchivedSheet = closeArchivedSheet;

let isMouseDownOnArchivedOverlay = false;
archivedSheet.addEventListener('mousedown', (e) => {
    isMouseDownOnArchivedOverlay = (e.target === archivedSheet);
});
archivedSheet.addEventListener('mouseup', (e) => {
    if (isMouseDownOnArchivedOverlay && e.target === archivedSheet) {
        closeArchivedSheet();
    }
    isMouseDownOnArchivedOverlay = false;
});

let isMouseDownOnEfOverlay = false;
efemeridesSheet.addEventListener('mousedown', (e) => {
    isMouseDownOnEfOverlay = (e.target === efemeridesSheet);
});
efemeridesSheet.addEventListener('mouseup', (e) => {
    if (isMouseDownOnEfOverlay && e.target === efemeridesSheet) {
        closeEfemeridesSheet();
    }
    isMouseDownOnEfOverlay = false;
});

window.closeEfemeridesSheet = closeEfemeridesSheet;

globalSearch.addEventListener('input', (e) => {
    setSearchQuery(e.target.value);
});

// Sheet Logic
let isMouseDownOnOverlay = false;

activitySheet.addEventListener('mousedown', (e) => {
    isMouseDownOnOverlay = (e.target === activitySheet);
});

activitySheet.addEventListener('mouseup', (e) => {
    if (isMouseDownOnOverlay && e.target === activitySheet) {
        closeActivitySheet();
    }
    isMouseDownOnOverlay = false;
});

function openActivitySheet() {
    activitySheet.classList.remove('hidden');
    renderActivityForm(activitySheet.querySelector('.sheet-content'));
}

window.openActivitySheetWithData = (data) => {
    activitySheet.classList.remove('hidden');
    renderActivityForm(activitySheet.querySelector('.sheet-content'), data);
};

export function closeActivitySheet() {
    activitySheet.classList.add('hidden');
}

// Global exposure
window.openActivityDetail = (id) => {
    const activity = state.activities.find(a => a.id === id);
    if (activity) {
        setCurrentActivity(activity);
        openActivitySheet();
    }
};

window.closeActivitySheet = closeActivitySheet;
window.setCurrentActivity = setCurrentActivity;

// Version Marker v1.2
const logo = document.querySelector('.logo');
if (logo) {
    const badge = document.createElement('span');
    badge.innerText = 'v1.2';
    badge.style.fontSize = '0.6rem';
    badge.style.background = 'var(--primary)';
    badge.style.color = 'white';
    badge.style.padding = '0.1rem 0.3rem';
    badge.style.borderRadius = '0.3rem';
    badge.style.marginLeft = '0.5rem';
    badge.style.verticalAlign = 'middle';
    logo.appendChild(badge);
}

// Auth: el login lo maneja /static/auth.js de forma centralizada.
// Si no hay token, auth.js muestra su overlay y bloquea la página.
// Cuando se loguea, hace location.reload() y este código corre con token válido.

// Initial Cleanup
state.activities = state.activities.map(a => ({
    ...a,
    location: (a.location === 'undefined' || !a.location) ? '' : a.location,
    observations: (a.observations === 'undefined' || !a.observations) ? '' : a.observations,
}));

// Initial Render
subscribe(updateUI);
Promise.all([loadActivities(), loadEfemerides(), loadNewsletterSettings()]).then(() => {
    updateUI();
    startPolling();
});

// ---------------------------------------------------------
// Polling para sincronización entre múltiples clientes.
// Cada N segundos consultamos el server. Si nada cambió, no re-renderizamos
// (loadActivities con silent: true). Si hay diff, se notifica y la UI se actualiza.
// Salvaguardas:
//  - No recargar si la pestaña está oculta (ahorra requests).
//  - No recargar si el usuario está editando un input/textarea (preserva el cursor
//    y evita pisar lo que está tipeando).
//  - Refresh inmediato cuando la pestaña vuelve a estar visible.
// ---------------------------------------------------------
const POLLING_INTERVAL_MS = 20000;

function isUserEditing() {
    const active = document.activeElement;
    if (!active) return false;
    if (active.matches && active.matches('input, textarea, select')) return true;
    return false;
}

function pollIfSafe() {
    if (document.hidden) return;
    if (isUserEditing()) return;
    loadActivities({ silent: true });
    loadEfemerides({ silent: true });
    loadNewsletterSettings({ silent: true });
}

let pollingStarted = false;
function startPolling() {
    if (pollingStarted) return;
    pollingStarted = true;
    setInterval(pollIfSafe, POLLING_INTERVAL_MS);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) pollIfSafe();
    });
}

// El polling ya arranca en el bloque "Initial Render" de arriba — auth.js
// maneja el login centralizado, así que no hace falta observar el overlay.

