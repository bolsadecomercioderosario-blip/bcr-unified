import { state, subscribe, setView, setCurrentActivity, setSearchQuery, toggleShowPast, loadActivities, loadEfemerides, loadNewsletterSettings } from './state.js';
import { renderList } from './components/List.js';
import { renderConectados } from './components/Conectados.js';
import { renderSanti } from './components/Santi.js';
import { renderActivityForm } from './components/ActivityForm.js';
import { renderEfemeridesModal } from './components/EfemeridesModal.js';

const viewContainer = document.getElementById('view-container');
const btnNewActivity = document.getElementById('btn-new-activity');
const btnTogglePast = document.getElementById('btn-toggle-past');
const btnEfemerides = document.getElementById('btn-efemerides');
const activitySheet = document.getElementById('activity-sheet');
const efemeridesSheet = document.getElementById('efemerides-sheet');
const globalSearch = document.getElementById('global-search');

// Router/View Switcher
function updateUI() {
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
    }

    // Update Lucide Icons
    if (window.lucide) {
        window.lucide.createIcons();
    }
}

// Event Listeners
document.addEventListener('click', (e) => {
    const navItem = e.target.closest('.nav-item');
    if (navItem) {
        setView(navItem.dataset.view);
    }
});

btnNewActivity.addEventListener('click', () => {
    setCurrentActivity(null); 
    openActivitySheet();
});

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

