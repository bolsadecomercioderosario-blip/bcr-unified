/* ============================================================
   Armador de "El Más Acá" — versión 45/50'.

   Herramienta de planificación (sin encuesta, sin backend): se tildan
   bloques del show y se ve el total en vivo, apuntando a la banda 45-50'.
   Los bloques (canciones + intervenciones) viven acá embebidos. La
   selección se guarda en el navegador (localStorage) para no perderla.
   ============================================================ */
(function () {
    "use strict";

    // Objetivo y máximo de esta versión (en segundos).
    var OBJ = 45 * 60;   // 45:00
    var MAX = 50 * 60;   // 50:00
    var STORE = "mas_aca_45_sel";

    var GRUPOS = [
        { id: "apertura",  label: "Apertura" },
        { id: "primero",   label: "Primer bloque" },
        { id: "habitos",   label: "Buenos hábitos" },
        { id: "fantasmas", label: "Fantasmas / Macabra" },
        { id: "funeraria", label: "Funeraria · trámites · última voluntad" },
        { id: "final",     label: "Final" }
    ];

    function m(mm, ss) { return mm * 60 + ss; }

    // Bloques del espectáculo, en orden. id estable, dur en segundos.
    var BLOQUES = [
        { id: 1,  grupo: "apertura",  nombre: "Clarinada + Presentación",                     tipo: "Canción · Apertura",  dur: m(4, 18) },

        { id: 2,  grupo: "primero",   nombre: "Intervención 1 – Personaje, radio y pitonisa",  tipo: "Intervención",        dur: m(4, 55) },
        { id: 3,  grupo: "primero",   nombre: "Alegorías de la muerte",                        tipo: "Canción",             dur: m(0, 55) },
        { id: 4,  grupo: "primero",   nombre: "Intervención 2 – Radio / canciones sobre la muerte", tipo: "Intervención",   dur: m(1, 1) },
        { id: 5,  grupo: "primero",   nombre: "Salpicón",                                      tipo: "Canción",             dur: m(3, 19) },

        { id: 6,  grupo: "habitos",   nombre: "Intervención 3 – Médico",                       tipo: "Intervención",        dur: m(1, 20) },
        { id: 7,  grupo: "habitos",   nombre: "Buenos Hábitos – Busca lo más vital + Bacilos", tipo: "Canción",             dur: m(1, 45) },
        { id: 8,  grupo: "habitos",   nombre: "Chacarera / Puente carretero",                  tipo: "Canción",             dur: m(1, 12) },
        { id: 9,  grupo: "habitos",   nombre: "Intervención 4 – Churros y manzanas",           tipo: "Intervención",        dur: m(2, 8) },
        { id: 10, grupo: "habitos",   nombre: "Churros vs. Manzanas + canciones de cancha",    tipo: "Cuplé",               dur: m(4, 25) },
        { id: 11, grupo: "habitos",   nombre: "Reflexión Buenos Hábitos",                      tipo: "Canción · Reflexión", dur: m(2, 30) },

        { id: 12, grupo: "fantasmas", nombre: "Intervención 5 – Contacto con el más allá",     tipo: "Intervención",        dur: m(4, 0) },
        { id: 13, grupo: "fantasmas", nombre: "Cuplé de los Fantasmas",                        tipo: "Cuplé",               dur: m(4, 40) },
        { id: 14, grupo: "fantasmas", nombre: "Intervención 6 – Fantasmas / Bum Bum / vocales", tipo: "Intervención",       dur: m(2, 35) },
        { id: 15, grupo: "fantasmas", nombre: "Macabra + reflexión política (Reina Batata + Razón de vivir + Témpano)", tipo: "Canción · Bloque", dur: m(5, 10) },

        { id: 16, grupo: "funeraria", nombre: "Intervención 7A – Llegada de la funeraria",     tipo: "Intervención",        dur: m(1, 40) },
        { id: 17, grupo: "funeraria", nombre: "Caballero",                                     tipo: "Canción",             dur: m(1, 50) },
        { id: 18, grupo: "funeraria", nombre: "Intervención 7B – Cajones / CURDA",             tipo: "Intervención",        dur: m(1, 10) },
        { id: 19, grupo: "funeraria", nombre: "Animaniacs / Trámites",                         tipo: "Canción",             dur: m(1, 15) },
        { id: 20, grupo: "funeraria", nombre: "Intervención 7C – Formulario / última voluntad", tipo: "Intervención",      dur: m(0, 55) },
        { id: 21, grupo: "funeraria", nombre: "Último Deseo",                                  tipo: "Canción",             dur: m(1, 50) },

        { id: 22, grupo: "final",     nombre: "Intervención 8 – Resolución personaje/pitonisa", tipo: "Intervención",       dur: m(4, 45) },
        { id: 23, grupo: "final",     nombre: "Canción Final",                                 tipo: "Canción",             dur: m(2, 45) },
        { id: 24, grupo: "final",     nombre: "Retirada",                                      tipo: "Canción · Retirada",  dur: m(5, 35) },
        { id: 25, grupo: "final",     nombre: "Pre-bajada (Árbol + Abel Pintos) / Bajada",     tipo: "Canción · Bajada",    dur: m(1, 57) }
    ];

    var DUR = {};
    BLOQUES.forEach(function (b) { DUR[b.id] = b.dur; });

    // ---------- helpers ----------
    function $(s, r) { return (r || document).querySelector(s); }
    function fmt(sec) {
        sec = Math.max(0, Math.round(sec));
        return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
    }
    function esc(s) {
        return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function toast(msg) {
        var t = $("#toast"); t.textContent = msg; t.classList.add("show");
        clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove("show"); }, 2600);
    }

    // selección
    var sel = {};   // id -> true
    function cargarSel() {
        try {
            var raw = JSON.parse(localStorage.getItem(STORE) || "[]");
            if (Array.isArray(raw)) raw.forEach(function (id) { if (DUR[id] != null) sel[id] = true; });
        } catch (e) {}
    }
    function guardarSel() {
        try {
            var ids = Object.keys(sel).filter(function (k) { return sel[k]; }).map(Number);
            localStorage.setItem(STORE, JSON.stringify(ids));
        } catch (e) {}
    }

    function total() {
        var t = 0;
        for (var id in sel) if (sel[id]) t += DUR[id] || 0;
        return t;
    }
    function count() {
        return Object.keys(sel).filter(function (k) { return sel[k]; }).length;
    }

    // Zona según el total (segundos), relativa a la banda objetivo [OBJ, MAX].
    function zona(t) {
        if (t === 0)      return { cls: "z-neutral", txt: "Elegí partes" };
        if (t < OBJ)      return { cls: "z-neutral", txt: "Te falta para los 45'" };
        if (t <= MAX)     return { cls: "z-ideal",   txt: "Zona ideal 🎯" };
        return { cls: "z-over", txt: "Te pasaste de 50'" };
    }

    var cont = $("#grupos"),
        barra = $("#barra"), bTime = $("#b-time"), bFill = $("#b-fill"), bEstado = $("#b-estado");

    function durGrupoSel(gid) {
        var t = 0;
        BLOQUES.forEach(function (b) { if (b.grupo === gid && sel[b.id]) t += b.dur; });
        return t;
    }
    function refrescarGrupos() {
        GRUPOS.forEach(function (g) {
            var items = BLOQUES.filter(function (b) { return b.grupo === g.id; });
            var durG = items.reduce(function (a, b) { return a + b.dur; }, 0);
            var head = cont.querySelector('.grupo[data-g="' + g.id + '"] .grupo-dur');
            if (head) head.textContent = fmt(durGrupoSel(g.id)) + " / " + fmt(durG);
        });
    }
    function refrescar() {
        var t = total(), z = zona(t), n = count();
        barra.className = "barra " + z.cls;
        bTime.textContent = fmt(t);
        bFill.style.width = Math.min(t / MAX, 1) * 100 + "%";
        bEstado.innerHTML = esc(z.txt) + ' · <b>' + n + '</b> parte' + (n === 1 ? "" : "s");
        refrescarGrupos();
        guardarSel();
    }

    function render() {
        var html = "";
        GRUPOS.forEach(function (g) {
            var items = BLOQUES.filter(function (b) { return b.grupo === g.id; });
            var durG = items.reduce(function (a, b) { return a + b.dur; }, 0);
            html += '<div class="grupo" data-g="' + g.id + '">';
            html += '<div class="grupo-head"><span class="grupo-label">' + esc(g.label) + '</span>' +
                    '<span class="grupo-dur">' + fmt(durGrupoSel(g.id)) + " / " + fmt(durG) + '</span></div>';
            html += '<div class="grupo-items">';
            items.forEach(function (b) {
                var on = !!sel[b.id];
                html += '<label class="bloque' + (on ? " on" : "") + '" data-id="' + b.id + '">' +
                    '<input type="checkbox"' + (on ? " checked" : "") + '>' +
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
            var id = +lab.getAttribute("data-id");
            sel[id] = ev.target.checked;
            lab.classList.toggle("on", ev.target.checked);
            refrescar();
        });
    }

    // Texto plano de la lista armada (ordenada por show), para copiar/pegar.
    function listaTexto() {
        var ids = BLOQUES.filter(function (b) { return sel[b.id]; });
        if (!ids.length) return "";
        var lineas = ["EL MÁS ACÁ — versión " + fmt(total()) + " (" + ids.length + " partes)", ""];
        var gActual = null;
        ids.forEach(function (b) {
            if (b.grupo !== gActual) {
                gActual = b.grupo;
                var gl = GRUPOS.filter(function (g) { return g.id === gActual; })[0];
                lineas.push("— " + (gl ? gl.label : gActual) + " —");
            }
            lineas.push("• " + b.nombre + "  (" + fmt(b.dur) + ")");
        });
        lineas.push("");
        lineas.push("TOTAL: " + fmt(total()));
        return lineas.join("\n");
    }

    $("#c-copiar").addEventListener("click", function () {
        var txt = listaTexto();
        if (!txt) { toast("Todavía no tildaste nada."); return; }
        function ok() { toast("Lista copiada ✓ — pegala donde quieras."); }
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(txt).then(ok).catch(fallback);
        } else { fallback(); }
        function fallback() {
            var ta = document.createElement("textarea");
            ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0";
            document.body.appendChild(ta); ta.focus(); ta.select();
            try { document.execCommand("copy"); ok(); } catch (e) { toast("No se pudo copiar."); }
            document.body.removeChild(ta);
        }
    });

    $("#c-clear").addEventListener("click", function () {
        if (!count()) return;
        if (!confirm("¿Destildar todo y empezar de cero?")) return;
        sel = {};
        var labs = cont.querySelectorAll(".bloque");
        for (var i = 0; i < labs.length; i++) {
            labs[i].classList.remove("on");
            var cb = labs[i].querySelector("input"); if (cb) cb.checked = false;
        }
        refrescar();
    });

    // ---------- init ----------
    cargarSel();
    render();
    refrescar();
})();
