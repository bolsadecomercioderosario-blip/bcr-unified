/* ============================================================
   Corte — encuesta versión reducida de "El Más Acá".

   SPA de un archivo: /corte/ es la encuesta pública; /corte/resultados muestra
   los resultados (token en ?k=). Los bloques y el objetivo/máximo se piden a
   /api/corte/bloques. El total se calcula en vivo en el cliente y se revalida
   en el server al guardar.
   ============================================================ */
(function () {
    "use strict";

    var API = "/api/corte";
    var TOKEN = new URLSearchParams(location.search).get("k") || "";
    var PATH = location.pathname.replace(/\/+$/, "");

    // ---------- helpers ----------
    function $(s, r) { return (r || document).querySelector(s); }
    function fmt(sec) {
        sec = Math.max(0, Math.round(sec));
        return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
    }
    function esc(s) {
        return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function show(id) {
        var vs = document.querySelectorAll(".view");
        for (var i = 0; i < vs.length; i++) vs[i].classList.remove("active");
        var el = document.getElementById(id);
        if (el) el.classList.add("active");
    }
    function toast(msg) {
        var t = $("#toast"); t.textContent = msg; t.classList.add("show");
        clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove("show"); }, 2600);
    }

    var OBJ = 1800, MAX = 2100;   // se sobreescriben con la respuesta del server
    var BLOQUES = [], GRUPOS = [], DUR = {};   // DUR: id -> segundos

    // Zona según el total (en segundos). Umbrales: <28 / 28–32 / 32–35 / >35.
    function zona(t) {
        if (t === 0)       return { cls: "z-neutral", txt: "Elegí partes" };
        if (t < 28 * 60)   return { cls: "z-neutral", txt: "Todavía tenés margen" };
        if (t <= 32 * 60)  return { cls: "z-ideal",   txt: "Zona ideal 🎯" };
        if (t <= MAX)      return { cls: "z-ext",     txt: "Versión extendida" };
        return { cls: "z-over", txt: "Te pasaste del máximo" };
    }

    // ================= ENCUESTA =================
    function initEncuesta() {
        show("view-encuesta");
        var barra = $("#barra"), bTime = $("#b-time"), bFill = $("#b-fill"),
            bEstado = $("#b-estado"), bEnviar = $("#b-enviar"),
            cont = $("#grupos"), nombresBox = $("#c-nombres"), nadie = $("#c-nadie");
        var sel = {};       // id -> true
        var selName = "";   // nombre elegido del roster

        function total() {
            var t = 0;
            for (var id in sel) if (sel[id]) t += DUR[id] || 0;
            return t;
        }
        function refrescar() {
            var t = total(), z = zona(t), n = Object.keys(sel).filter(function (k) { return sel[k]; }).length;
            barra.className = "barra " + z.cls;
            bTime.textContent = fmt(t);
            bFill.style.width = Math.min(t / MAX, 1) * 100 + "%";
            bEstado.textContent = z.txt;
            bEnviar.disabled = !(selName && n > 0 && t <= MAX);
        }

        function render() {
            var html = "";
            GRUPOS.forEach(function (g) {
                var items = BLOQUES.filter(function (b) { return b.grupo === g.id; });
                var durG = items.reduce(function (a, b) { return a + b.dur; }, 0);
                html += '<div class="grupo">';
                html += '<div class="grupo-head"><span class="grupo-label">' + esc(g.label) + '</span>' +
                        '<span class="grupo-dur">' + fmt(durG) + '</span></div>';
                html += '<div class="grupo-items">';
                items.forEach(function (b) {
                    html += '<label class="bloque" data-id="' + b.id + '">' +
                        '<input type="checkbox">' +
                        '<span class="bloque-check"></span>' +
                        '<span class="bloque-body">' +
                            '<span class="bloque-nombre">' + esc(b.nombre) + '</span>' +
                            '<span class="bloque-meta">' + esc(b.tipo) + '</span>' +
                        '</span>' +
                        '<span class="bloque-dur">' + fmt(b.dur) + '</span>' +
                    '</label>';
                });
                html += '</div></div>';
            });
            cont.innerHTML = html;

            cont.addEventListener("change", function (ev) {
                var lab = ev.target.closest(".bloque");
                if (!lab) return;
                var id = lab.getAttribute("data-id");
                sel[id] = ev.target.checked;
                lab.classList.toggle("on", ev.target.checked);
                refrescar();
            });
        }

        function renderNombres(items) {
            var libres = 0;
            nombresBox.innerHTML = items.map(function (o) {
                if (!o.tomado) libres++;
                var cls = "nom" + (o.tomado ? " taken" : "") + (o.nombre === selName ? " sel" : "");
                return '<button type="button" class="' + cls + '" data-nombre="' + esc(o.nombre) + '"' +
                       (o.tomado ? " disabled" : "") + ">" + esc(o.nombre) + (o.tomado ? " ✓" : "") + "</button>";
            }).join("");
            nadie.classList.toggle("hidden", libres > 0);
        }
        function cargarNombres() {
            return fetch(API + "/nombres").then(function (r) { return r.json(); })
                .then(function (d) { renderNombres(d.nombres || []); })
                .catch(function () {});
        }

        // Bloques del espectáculo
        fetch(API + "/bloques")
            .then(function (r) { return r.json(); })
            .then(function (d) {
                BLOQUES = d.bloques || []; GRUPOS = d.grupos || [];
                OBJ = d.objetivo_seg || OBJ; MAX = d.max_seg || MAX;
                BLOQUES.forEach(function (b) { DUR[b.id] = b.dur; });
                render();
                barra.classList.remove("hidden");
                cargarNombres();
                refrescar();
            })
            .catch(function () { cont.innerHTML = '<div class="cargando">No se pudo cargar. Refrescá la página.</div>'; });

        nombresBox.addEventListener("click", function (ev) {
            var b = ev.target.closest(".nom");
            if (!b || b.disabled) return;
            selName = b.getAttribute("data-nombre");
            var all = nombresBox.querySelectorAll(".nom");
            for (var i = 0; i < all.length; i++) all[i].classList.toggle("sel", all[i] === b);
            refrescar();
        });

        bEnviar.addEventListener("click", function () {
            var ids = Object.keys(sel).filter(function (k) { return sel[k]; }).map(Number);
            if (!selName) { toast("Elegí tu nombre."); return; }
            if (!ids.length) { toast("Elegí al menos una parte."); return; }
            bEnviar.disabled = true; bEnviar.textContent = "Enviando…";
            fetch(API + "/responder", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ nombre: selName, seleccion: ids })
            })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, status: r.status, d: d }; }); })
            .then(function (res) {
                if (res.status === 409) {   // el nombre ya cargó (p. ej. desde otro celular)
                    toast("Ese nombre ya cargó su selección.");
                    selName = ""; cargarNombres();
                    throw new Error("dup");
                }
                if (!res.ok) throw new Error((res.d && res.d.detail) || "Error");
                $("#g-msg").textContent = "¡Listo! Tu selección dura " + fmt(res.d.total_seg) + ".";
                barra.classList.add("hidden");
                show("view-gracias");
                window.scrollTo({ top: 0, behavior: "smooth" });
            })
            .catch(function (e) { if (e.message !== "dup") toast(e.message || "No se pudo enviar."); })
            .finally(function () { bEnviar.disabled = false; bEnviar.textContent = "Enviar mi selección"; refrescar(); });
        });
    }

    // ================= RESULTADOS =================
    function initResultados() {
        show("view-resultados");
        var barra = $("#barra-r"), brTime = $("#br-time"), brFill = $("#br-fill"),
            brEstado = $("#br-estado"), brCount = $("#br-count"),
            body = $("#r-body"), deneg = $("#r-denegado");
        var bloques = [], total = 0, cut = {}, sort = "votos";

        function durCorte() {
            var t = 0, n = 0;
            bloques.forEach(function (b) { if (cut[b.id]) { t += b.dur; n++; } });
            return { t: t, n: n };
        }
        function refrescarBarra() {
            var c = durCorte(), z = zona(c.t);
            barra.className = "barra " + z.cls;
            brTime.textContent = fmt(c.t);
            brFill.style.width = Math.min(c.t / MAX, 1) * 100 + "%";
            brCount.textContent = c.n;
            brEstado.innerHTML = '<span id="br-count">' + c.n + "</span> parte" + (c.n === 1 ? "" : "s");
        }
        function ordenados() {
            var arr = bloques.slice();
            if (sort === "votos") arr.sort(function (a, b) { return b.votos - a.votos || a.id - b.id; });
            else arr.sort(function (a, b) { return a.id - b.id; });
            return arr;
        }
        function render() {
            body.innerHTML = ordenados().map(function (b) {
                var on = !!cut[b.id];
                return '<tr data-id="' + b.id + '" class="' + (on ? "on" : "") + '">' +
                    '<td class="c-check"><input type="checkbox"' + (on ? " checked" : "") + '></td>' +
                    '<td><div class="r-nombre">' + esc(b.nombre) + '</div>' +
                        '<div class="r-tipo">' + esc(b.tipo) + '</div>' +
                        '<div class="r-bar"><span style="width:' + b.pct + '%"></span></div></td>' +
                    '<td class="c-num r-votos">' + b.votos + '</td>' +
                    '<td class="c-num">' + b.pct + '%</td>' +
                    '<td class="c-num">' + fmt(b.dur) + '</td>' +
                '</tr>';
            }).join("");
        }
        function setSort(mode) {
            sort = mode;
            $("#r-sort-votos").classList.toggle("chip-on", mode === "votos");
            $("#r-sort-orden").classList.toggle("chip-on", mode === "orden");
            render();
        }

        fetch(API + "/resultados?k=" + encodeURIComponent(TOKEN))
            .then(function (r) {
                if (r.status === 401) { deneg.style.display = "block"; throw new Error("401"); }
                return r.json();
            })
            .then(function (d) {
                bloques = d.bloques || []; total = d.total_personas || 0;
                OBJ = d.objetivo_seg || OBJ; MAX = d.max_seg || MAX;
                $("#r-total").textContent = total;
                $("#r-total-lbl").textContent = total === 1 ? "persona respondió" : "personas respondieron";
                render();
                barra.classList.remove("hidden");
                refrescarBarra();
            })
            .catch(function () {});

        body.addEventListener("change", function (ev) {
            var tr = ev.target.closest("tr"); if (!tr) return;
            var id = +tr.getAttribute("data-id");
            cut[id] = ev.target.checked;
            tr.classList.toggle("on", ev.target.checked);
            refrescarBarra();
        });
        $("#r-sort-votos").addEventListener("click", function () { setSort("votos"); });
        $("#r-sort-orden").addEventListener("click", function () { setSort("orden"); });
        $("#r-clear").addEventListener("click", function () { cut = {}; render(); refrescarBarra(); });
        $("#r-reset").addEventListener("click", function () {
            if (!confirm("¿Borrar TODAS las respuestas de la encuesta?\n\nEsto no se puede deshacer.")) return;
            if (!confirm("Última confirmación: se borran todas las selecciones cargadas. ¿Continuar?")) return;
            fetch(API + "/reset?k=" + encodeURIComponent(TOKEN), { method: "POST" })
                .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
                .then(function (d) {
                    total = 0;
                    bloques.forEach(function (b) { b.votos = 0; b.pct = 0; });
                    cut = {};
                    $("#r-total").textContent = 0;
                    $("#r-total-lbl").textContent = "personas respondieron";
                    render(); refrescarBarra();
                    toast("Listo: se borraron " + (d.borradas || 0) + " respuesta(s).");
                })
                .catch(function () { toast("No se pudo borrar. Reintentá."); });
        });

        $("#r-auto").addEventListener("click", function () {
            // Arma un corte de arranque: agrega los más votados hasta llegar a ~30',
            // sin pasar el máximo. Después el organizador lo ajusta a mano.
            cut = {};
            var t = 0;
            bloques.slice().sort(function (a, b) { return b.votos - a.votos || a.id - b.id; })
                .forEach(function (b) {
                    if (t >= OBJ) return;
                    if (t + b.dur <= MAX) { cut[b.id] = true; t += b.dur; }
                });
            render(); refrescarBarra();
        });
    }

    // ---------- router ----------
    if (/\/resultados$/.test(PATH)) initResultados();
    else                           initEncuesta();
})();
