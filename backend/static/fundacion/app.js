/* ============================================================
   Agenda de la Fundación BCR.
   - Vista de solo lectura vía token del link (/fundacion/{token}).
   - Modo EDICIÓN opcional: quien tiene sesión (login por usuario, rol
     Comunicación) puede crear/editar/archivar. El link público sigue
     siendo solo-lectura; editar exige login.
   App independiente (no toca la Agenda de Comunicación/Secretaría).
   ============================================================ */
(function () {
    "use strict";

    var parts = location.pathname.split("/").filter(Boolean);
    var URL_TOKEN = parts.length ? parts[parts.length - 1] : "";   // token del link (lectura)
    var STORE_TK = "bcr_session_token", STORE_ROLE = "bcr_session_role";

    var MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
        "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
    var DOW = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

    function $(s) { return document.querySelector(s); }
    function esc(s) {
        return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function sessionToken() { try { return localStorage.getItem(STORE_TK) || ""; } catch (e) { return ""; } }
    function sessionRole() { try { return localStorage.getItem(STORE_ROLE) || ""; } catch (e) { return ""; } }
    function hoyISO() {
        var d = new Date();
        return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    }
    function parseFecha(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
        if (!m) return null;
        return { y: +m[1], mo: +m[2], d: +m[3], dow: new Date(+m[1], +m[2] - 1, +m[3]).getDay() };
    }
    function fechaLarga(iso) {
        var f = parseFecha(iso);
        return f ? (f.d + " de " + MESES[f.mo - 1] + " " + f.y) : (iso || "");
    }

    var TODOS = [];
    var EDIT = false;

    // ---- API ----
    function cargar() {
        fetch("/api/fundacion/actividades?token=" + encodeURIComponent(URL_TOKEN))
            .then(function (r) {
                if (r.status === 401) throw new Error("401");
                if (!r.ok) throw new Error("err");
                return r.json();
            })
            .then(function (data) {
                TODOS = Array.isArray(data) ? data : [];
                $("#estado").classList.add("hidden");
                $("#controls").classList.remove("hidden");
                render($("#buscar").value || "");
            })
            .catch(function (e) {
                var est = $("#estado");
                est.classList.remove("hidden");
                est.textContent = e.message === "401"
                    ? "Link inválido o vencido. Pedí el enlace actualizado al área de Comunicación."
                    : "No se pudo cargar la agenda. Reintentá en un momento.";
            });
    }

    function authFetch(url, opts) {
        opts = opts || {};
        opts.headers = opts.headers || {};
        opts.headers["Authorization"] = "Bearer " + sessionToken();
        return fetch(url, opts);
    }

    // ---- Render ----
    function render(filtro) {
        var lista = $("#lista"), vacio = $("#vacio");
        filtro = (filtro || "").trim().toLowerCase();
        var items = TODOS.filter(function (a) {
            if (!filtro) return true;
            return (a.evento + " " + a.equipo + " " + a.metricas + " " + a.hora).toLowerCase().indexOf(filtro) >= 0;
        });

        var grupos = {};
        items.forEach(function (a) {
            var f = parseFecha(a.fecha);
            var key = f ? (f.y + "-" + String(f.mo).padStart(2, "0")) : "0000-00";
            (grupos[key] = grupos[key] || []).push(a);
        });
        var keys = Object.keys(grupos).sort().reverse();
        var hoy = hoyISO();
        var html = "";
        keys.forEach(function (key) {
            var arr = grupos[key];
            arr.sort(function (a, b) {
                return (a.fecha || "").localeCompare(b.fecha || "") || (a.hora || "").localeCompare(b.hora || "");
            });
            var fa = parseFecha(arr[0].fecha);
            var titulo = fa ? (MESES[fa.mo - 1] + " " + fa.y) : "Sin fecha";
            html += '<section class="mes"><div class="mes-head"><span>' + esc(titulo) + '</span></div>';
            arr.forEach(function (a) {
                var f = parseFecha(a.fecha);
                var dia = f ? f.d : "–", dow = f ? DOW[f.dow] : "";
                var esHoy = a.fecha === hoy;
                var tags = "";
                if (a.equipo) tags += '<span class="tag tag-equipo">' + esc(a.equipo) + '</span>';
                if (a.metricas) tags += '<span class="tag tag-metrica">' + esc(a.metricas) + '</span>';
                html += '<article class="act' + (esHoy ? " hoy" : "") + (EDIT ? " editable" : "") + '" data-id="' + esc(a.id) + '">' +
                    '<div class="fecha-col"><div class="fecha-dia">' + dia + '</div><div class="fecha-dow">' + esc(dow) + '</div></div>' +
                    '<div class="act-body">' +
                        (a.hora ? '<div class="act-hora">' + esc(a.hora) + '</div>' : '') +
                        '<div class="act-evento">' + esc(a.evento || "(sin detalle)") + '</div>' +
                        (tags ? '<div class="act-tags">' + tags + '</div>' : '') + '</div>' +
                    (EDIT ? '<button class="pencil" title="Editar">✎</button>' : '') +
                '</article>';
            });
            html += '</section>';
        });
        lista.innerHTML = html;
        vacio.classList.toggle("hidden", items.length > 0);
    }

    // ---- Edición ----
    function toggleEdit() {
        if (!EDIT && !sessionToken()) { pedirLogin(); return; }
        EDIT = !EDIT;
        document.body.classList.toggle("modo-edit", EDIT);
        $("#fab-edit").textContent = EDIT ? "✓ Listo" : "✎ Editar";
        $("#fab-nueva").classList.toggle("hidden", !EDIT);
        render($("#buscar").value || "");
    }

    function byId(id) { for (var i = 0; i < TODOS.length; i++) if (TODOS[i].id === id) return TODOS[i]; return null; }

    function abrirPanel(act) {
        var esNueva = !act;
        act = act || { fecha: "", hora: "", evento: "", equipo: "", metricas: "" };
        var ov = document.createElement("div");
        ov.className = "modal-ov";
        ov.innerHTML =
            '<div class="modal">' +
            '<h2>' + (esNueva ? "Nueva actividad" : "Editar actividad") + '</h2>' +
            '<label>Fecha</label><input id="f-fecha" type="date" value="' + esc(act.fecha) + '">' +
            '<label>Hora <span class="opt">(opcional)</span></label><input id="f-hora" type="text" placeholder="15 hs · 9 a 12 hs" value="' + esc(act.hora) + '">' +
            '<label>Evento</label><textarea id="f-evento" rows="2" placeholder="Descripción de la actividad">' + esc(act.evento) + '</textarea>' +
            '<label>Equipo <span class="opt">(quién participa)</span></label><input id="f-equipo" type="text" placeholder="Ana · Nico · Ana y Nico" value="' + esc(act.equipo) + '">' +
            '<label>Métricas <span class="opt">(opcional)</span></label><input id="f-metricas" type="text" placeholder="70 estudiantes, 4 docentes" value="' + esc(act.metricas) + '">' +
            '<div class="modal-msg" id="f-msg"></div>' +
            '<div class="modal-acc">' +
                (esNueva ? '' : '<button class="btn btn-arch" id="f-arch">Archivar</button>') +
                '<span class="sp"></span>' +
                '<button class="btn btn-cancel" id="f-cancel">Cancelar</button>' +
                '<button class="btn btn-save" id="f-save">Guardar</button>' +
            '</div></div>';
        document.body.appendChild(ov);
        ov.addEventListener("click", function (e) { if (e.target === ov) ov.remove(); });
        ov.querySelector("#f-cancel").onclick = function () { ov.remove(); };

        function datos() {
            return {
                fecha: ov.querySelector("#f-fecha").value,
                hora: ov.querySelector("#f-hora").value.trim(),
                evento: ov.querySelector("#f-evento").value.trim(),
                equipo: ov.querySelector("#f-equipo").value.trim(),
                metricas: ov.querySelector("#f-metricas").value.trim()
            };
        }
        function err(m) { ov.querySelector("#f-msg").textContent = m; }

        ov.querySelector("#f-save").onclick = function () {
            var d = datos();
            if (!d.evento) { err("El evento no puede estar vacío."); return; }
            var save = ov.querySelector("#f-save"); save.disabled = true; save.textContent = "Guardando…";
            var url = "/api/fundacion/actividades" + (esNueva ? "" : "/" + act.id);
            authFetch(url, {
                method: esNueva ? "POST" : "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(d)
            }).then(function (r) {
                if (r.status === 401 || r.status === 403) { err("Tu sesión no tiene permiso. Volvé a entrar."); throw 0; }
                if (!r.ok) throw 0;
                return r.json();
            }).then(function () {
                ov.remove(); cargar();
            }).catch(function () {
                save.disabled = false; save.textContent = "Guardar";
                if (!ov.querySelector("#f-msg").textContent) err("No se pudo guardar. Reintentá.");
            });
        };

        if (!esNueva) {
            ov.querySelector("#f-arch").onclick = function () {
                if (!confirm("¿Archivar esta actividad? Deja de verse en la agenda (es recuperable).")) return;
                authFetch("/api/fundacion/actividades/" + act.id, { method: "DELETE" })
                    .then(function (r) { if (!(r.status === 204 || r.ok)) throw 0; ov.remove(); cargar(); })
                    .catch(function () { err("No se pudo archivar. Reintentá."); });
            };
        }
    }

    function pedirLogin() {
        var ov = document.createElement("div");
        ov.className = "modal-ov";
        ov.innerHTML =
            '<div class="modal modal-login">' +
            '<h2>Entrar para editar</h2>' +
            '<p class="login-sub">Con tu usuario de la BCR. El link de consulta sigue siendo solo lectura.</p>' +
            '<label>Email</label><input id="l-email" type="email" autocomplete="username" placeholder="tuusuario@bcr.com.ar">' +
            '<label>Contraseña</label><input id="l-pass" type="password" autocomplete="current-password">' +
            '<div class="modal-msg" id="l-msg"></div>' +
            '<div class="modal-acc"><span class="sp"></span>' +
            '<button class="btn btn-cancel" id="l-cancel">Cancelar</button>' +
            '<button class="btn btn-save" id="l-entrar">Entrar</button></div></div>';
        document.body.appendChild(ov);
        ov.addEventListener("click", function (e) { if (e.target === ov) ov.remove(); });
        ov.querySelector("#l-cancel").onclick = function () { ov.remove(); };
        setTimeout(function () { ov.querySelector("#l-email").focus(); }, 50);

        function entrar() {
            var email = ov.querySelector("#l-email").value.trim();
            var pass = ov.querySelector("#l-pass").value;
            if (!email || !pass) { ov.querySelector("#l-msg").textContent = "Completá email y contraseña."; return; }
            var b = ov.querySelector("#l-entrar"); b.disabled = true; b.textContent = "Entrando…";
            fetch("/api/auth/login", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: email, password: pass })
            }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
              .then(function (res) {
                if (!res.ok) throw new Error((res.d && res.d.detail) || "Email o contraseña incorrectos");
                try {
                    localStorage.setItem(STORE_TK, res.d.token);
                    if (res.d.role) localStorage.setItem(STORE_ROLE, res.d.role);
                } catch (e) {}
                ov.remove();
                EDIT = false; toggleEdit();   // entra en modo edición
            }).catch(function (e) {
                b.disabled = false; b.textContent = "Entrar";
                ov.querySelector("#l-msg").textContent = e.message || "No se pudo entrar.";
            });
        }
        ov.querySelector("#l-entrar").onclick = entrar;
        ov.querySelector("#l-pass").addEventListener("keydown", function (e) { if (e.key === "Enter") entrar(); });
    }

    // ---- Eventos ----
    $("#buscar").addEventListener("input", function (e) { render(e.target.value); });
    $("#fab-edit").addEventListener("click", toggleEdit);
    $("#fab-nueva").addEventListener("click", function () { abrirPanel(null); });
    $("#lista").addEventListener("click", function (e) {
        if (!EDIT) return;
        var art = e.target.closest(".act"); if (!art) return;
        abrirPanel(byId(art.getAttribute("data-id")));
    });

    cargar();
})();
