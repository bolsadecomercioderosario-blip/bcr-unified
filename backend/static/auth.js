/**
 * Auth compartido para todas las páginas del hub.
 *
 * - Si no hay token en localStorage, muestra un overlay de login que bloquea
 *   la app hasta loguearte.
 * - Monkey-patchea `fetch` para que cualquier request a /api/* lleve
 *   `Authorization: Bearer <token>` automáticamente. Cero cambios en el
 *   código de cada módulo.
 * - Si una request devuelve 401, borra el token y vuelve a mostrar el
 *   overlay (sesión vencida o invalidada).
 *
 * Debe cargarse ANTES de cualquier otro script que haga fetch.
 */
(function () {
    const STORAGE_KEY = 'bcr_session_token';

    function getToken() {
        return localStorage.getItem(STORAGE_KEY) || '';
    }

    function setToken(t) {
        localStorage.setItem(STORAGE_KEY, t);
    }

    function clearToken() {
        localStorage.removeItem(STORAGE_KEY);
    }

    // ---- Monkey patch de fetch -------------------------------------------
    const ORIG_FETCH = window.fetch.bind(window);
    window.fetch = function (input, opts) {
        opts = opts || {};
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const isApi = url.startsWith('/api/');
        const isLogin = url.startsWith('/api/auth/login');
        if (isApi && !isLogin) {
            const token = getToken();
            if (token) {
                opts.headers = Object.assign({}, opts.headers || {}, {
                    Authorization: 'Bearer ' + token,
                });
            }
        }
        const promise = ORIG_FETCH(input, opts);
        return promise.then(function (res) {
            if (res.status === 401 && isApi && !isLogin) {
                clearToken();
                showLoginOverlay('La sesión expiró. Volvé a ingresar.');
            }
            return res;
        });
    };

    // ---- Overlay de login -------------------------------------------------
    function buildOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'bcr-auth-overlay';
        overlay.style.cssText =
            'position:fixed;inset:0;background:#0f172a;z-index:100000;' +
            'display:flex;align-items:center;justify-content:center;' +
            'font-family:Inter,-apple-system,system-ui,sans-serif;color:#f1f5f9;';
        overlay.innerHTML = ''
            + '<div style="background:#1e293b;padding:2rem 2.25rem;border-radius:0.75rem;'
            +              'border:1px solid #334155;max-width:380px;width:90%;'
            +              'box-shadow:0 25px 50px -12px rgba(0,0,0,0.5);">'
            + '  <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.5rem;">'
            + '    <span style="font-size:1.2rem;">🔒</span>'
            + '    <span style="font-weight:700;font-size:1.05rem;">Acceso protegido</span>'
            + '  </div>'
            + '  <p style="color:#94a3b8;font-size:0.85rem;margin-bottom:1.25rem;">'
            + '    Ingresá la contraseña para usar las herramientas del equipo.'
            + '  </p>'
            + '  <input id="bcr-auth-password" type="password" placeholder="Contraseña"'
            + '         autocomplete="current-password" style="'
            + '         width:100%;padding:0.7rem 0.85rem;border-radius:0.5rem;'
            + '         border:1px solid #334155;background:#0f172a;color:#f1f5f9;'
            + '         font-size:0.95rem;outline:none;margin-bottom:0.6rem;">'
            + '  <button id="bcr-auth-submit" style="'
            + '         width:100%;padding:0.7rem;border:none;border-radius:0.5rem;'
            + '         background:#4f46e5;color:white;font-weight:600;font-size:0.95rem;'
            + '         cursor:pointer;">Entrar</button>'
            + '  <p id="bcr-auth-error" style="color:#f87171;font-size:0.8rem;'
            + '         margin-top:0.85rem;display:none;text-align:center;"></p>'
            + '</div>';
        return overlay;
    }

    let currentOverlay = null;

    function showLoginOverlay(message) {
        if (currentOverlay) return; // ya está visible
        currentOverlay = buildOverlay();
        document.body.appendChild(currentOverlay);
        const input = currentOverlay.querySelector('#bcr-auth-password');
        const btn = currentOverlay.querySelector('#bcr-auth-submit');
        const err = currentOverlay.querySelector('#bcr-auth-error');
        if (message) {
            err.textContent = message;
            err.style.display = 'block';
        }
        setTimeout(function () { input.focus(); }, 50);

        async function tryLogin() {
            err.style.display = 'none';
            btn.disabled = true;
            btn.textContent = 'Verificando…';
            try {
                const res = await ORIG_FETCH('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: input.value }),
                });
                if (!res.ok) {
                    const data = await res.json().catch(function () { return {}; });
                    throw new Error(data.detail || 'Contraseña incorrecta');
                }
                const data = await res.json();
                setToken(data.token);
                if (currentOverlay && currentOverlay.parentNode) {
                    currentOverlay.parentNode.removeChild(currentOverlay);
                }
                currentOverlay = null;
                // Recargar para que cualquier llamada que falló previamente vuelva a correr
                window.location.reload();
            } catch (e) {
                err.textContent = e.message || 'Error';
                err.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Entrar';
                input.value = '';
                input.focus();
            }
        }

        btn.addEventListener('click', tryLogin);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') tryLogin();
        });
    }

    // ---- Inicial: si no hay token, mostrar overlay; si hay, validarlo ----
    function init() {
        const token = getToken();
        if (!token) {
            showLoginOverlay();
            return;
        }
        // Validamos el token contra el server. Si falla, el monkey patch de
        // fetch va a disparar el overlay solo por la 401.
        window.fetch('/api/auth/check').catch(function () {});
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Exponer helpers por si algún módulo los necesita explícitamente
    window.BCRAuth = { getToken: getToken, clearToken: clearToken, showLogin: showLoginOverlay };
})();
