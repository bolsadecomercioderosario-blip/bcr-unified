/* ============================================================
   Agenda de la Fundación BCR — vista de solo lectura.
   Lee el token del path (/fundacion/{token}), pide las actividades al API,
   las agrupa por mes y las muestra. App independiente (no toca la Agenda).
   ============================================================ */
(function () {
    "use strict";

    // Token = último segmento no vacío del path.
    var parts = location.pathname.split("/").filter(Boolean);
    var TOKEN = parts.length ? parts[parts.length - 1] : "";

    var MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
        "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
    var DOW = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

    function $(s) { return document.querySelector(s); }
    function esc(s) {
        return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function hoyISO() {
        var d = new Date();
        return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    }
    function parseFecha(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
        if (!m) return null;
        return { y: +m[1], mo: +m[2], d: +m[3], dow: new Date(+m[1], +m[2] - 1, +m[3]).getDay() };
    }

    var TODOS = [];

    function render(filtro) {
        var lista = $("#lista"), vacio = $("#vacio");
        filtro = (filtro || "").trim().toLowerCase();

        var items = TODOS.filter(function (a) {
            if (!filtro) return true;
            return (a.evento + " " + a.equipo + " " + a.metricas + " " + a.hora).toLowerCase().indexOf(filtro) >= 0;
        });

        // Agrupar por mes (clave y-mo). Orden de meses: más nuevo primero.
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
            // dentro del mes: ascendente por día y hora
            arr.sort(function (a, b) {
                return (a.fecha || "").localeCompare(b.fecha || "") || (a.hora || "").localeCompare(b.hora || "");
            });
            var fa = parseFecha(arr[0].fecha);
            var titulo = fa ? (MESES[fa.mo - 1] + " " + fa.y) : "Sin fecha";
            html += '<section class="mes">';
            html += '<div class="mes-head"><span>' + esc(titulo) + '</span>' +
                    '<span class="mes-n">' + arr.length + (arr.length === 1 ? " actividad" : " actividades") + '</span></div>';
            arr.forEach(function (a) {
                var f = parseFecha(a.fecha);
                var dia = f ? f.d : "–";
                var dow = f ? DOW[f.dow] : "";
                var esHoy = a.fecha === hoy;
                var tags = "";
                if (a.hora) tags += '<span class="tag tag-hora">' + esc(a.hora) + '</span>';
                if (a.equipo) tags += '<span class="tag tag-equipo">' + esc(a.equipo) + '</span>';
                if (a.metricas) tags += '<span class="tag tag-metrica">' + esc(a.metricas) + '</span>';
                html += '<article class="act' + (esHoy ? " hoy" : "") + '">' +
                    '<div class="fecha-col"><div class="fecha-dia">' + dia + '</div>' +
                        '<div class="fecha-dow">' + esc(dow) + '</div></div>' +
                    '<div class="act-body"><div class="act-evento">' + esc(a.evento || "(sin detalle)") + '</div>' +
                        (tags ? '<div class="act-tags">' + tags + '</div>' : '') +
                    '</div>' +
                '</article>';
            });
            html += '</section>';
        });

        lista.innerHTML = html;
        vacio.classList.toggle("hidden", items.length > 0);
    }

    function cargar() {
        fetch("/api/fundacion/actividades?token=" + encodeURIComponent(TOKEN))
            .then(function (r) {
                if (r.status === 401) throw new Error("401");
                if (!r.ok) throw new Error("err");
                return r.json();
            })
            .then(function (data) {
                TODOS = Array.isArray(data) ? data : [];
                $("#estado").classList.add("hidden");
                $("#controls").classList.remove("hidden");
                $("#meta-count").textContent = TODOS.length + (TODOS.length === 1 ? " actividad" : " actividades");
                render("");
            })
            .catch(function (e) {
                var est = $("#estado");
                est.classList.remove("hidden");
                est.textContent = e.message === "401"
                    ? "Link inválido o vencido. Pedí el enlace actualizado al área de Comunicación."
                    : "No se pudo cargar la agenda. Reintentá en un momento.";
            });
    }

    $("#buscar").addEventListener("input", function (e) { render(e.target.value); });
    cargar();
})();
