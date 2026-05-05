import { state, subscribe, setView, setCurrentActivity, setSearchQuery, toggleShowPast, loadActivities } from './state.js';
import { renderList } from './components/List.js';
import { renderConectados } from './components/Conectados.js';
import { renderSanti } from './components/Santi.js';
import { renderActivityForm } from './components/ActivityForm.js';

const viewContainer = document.getElementById('view-container');
const btnNewActivity = document.getElementById('btn-new-activity');
const btnTogglePast = document.getElementById('btn-toggle-past');
const activitySheet = document.getElementById('activity-sheet');
const globalSearch = document.getElementById('global-search');

// Router/View Switcher
function updateUI() {
    const navItems = document.querySelectorAll('.nav-item');
    
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
    
    // Show/Hide search and history toggle only in 'list' view
    const searchBox = document.querySelector('.search-box');
    if (searchBox) {
        searchBox.style.display = state.view === 'list' ? 'flex' : 'none';
    }
    if (btnTogglePast) {
        btnTogglePast.style.display = state.view === 'list' ? 'flex' : 'none';
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

// Initial Cleanup
state.activities = state.activities.map(a => {
    return {
        ...a,
        location: (a.location === 'undefined' || !a.location) ? '' : a.location,
        observations: (a.observations === 'undefined' || !a.observations) ? '' : a.observations
    };
});

// Initial Render
subscribe(updateUI);
loadActivities().then(() => {
    updateUI();
});
