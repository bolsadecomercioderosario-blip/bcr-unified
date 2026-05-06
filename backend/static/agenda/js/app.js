import { state, subscribe, setView, setCurrentActivity, setSearchQuery, toggleShowPast, loadActivities, loadEfemerides } from './state.js';
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

// Auth Logic
const loginOverlay = document.getElementById('login-overlay');
const loginPassword = document.getElementById('login-password');
const btnLogin = document.getElementById('btn-login');
const loginError = document.getElementById('login-error');

function checkAuth() {
    if (localStorage.getItem('agenda_auth') === 'true') {
        loginOverlay.classList.add('hidden');
        return true;
    }
    return false;
}

async function tryLogin() {
    const password = loginPassword.value;
    try {
        const res = await fetch('/api/agenda/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });

        if (res.ok) {
            localStorage.setItem('agenda_auth', 'true');
            loginOverlay.classList.add('hidden');
            Promise.all([loadActivities(), loadEfemerides()]).then(updateUI);
        } else {
            loginError.style.display = 'block';
            loginPassword.value = '';
        }
    } catch (e) {
        console.error(e);
        alert('Error al conectar con el servidor');
    }
}

if (btnLogin) {
    btnLogin.onclick = tryLogin;
    loginPassword.onkeydown = (e) => { if (e.key === 'Enter') tryLogin(); };
}

// Initial Cleanup
state.activities = state.activities.map(a => {
    return {
        ...a,
        location: (a.location === 'undefined' || !a.location) ? '' : a.location,
        observations: (a.observations === 'undefined' || !a.observations) ? '' : a.observations
    };
});

// Initial Render
if (checkAuth()) {
    subscribe(updateUI);
    Promise.all([loadActivities(), loadEfemerides()]).then(() => {
        updateUI();
        startPolling();
    });
} else {
    // Si no está autenticado, esperamos a que el usuario se loguee
    subscribe(updateUI);
}

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

// Si el usuario se loguea después del initial render, arrancar polling al ocultarse
// el overlay de login (se oculta sólo cuando la auth fue exitosa).
new MutationObserver(() => {
    if (loginOverlay.classList.contains('hidden')) startPolling();
}).observe(loginOverlay, { attributes: true, attributeFilter: ['class'] });

