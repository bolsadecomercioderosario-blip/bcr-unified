/* ============================================================
   Murga "Y Parió La Abuela" — El Más Acá. Front del sorteo.

   SPA de un solo archivo: mira location.pathname para decidir qué vista
   mostrar. El formulario (/murga/) es público; las vistas del presentador
   (/murga/voluntades, /murga/sorteo, /murga/export) leen el token de ?k=... y
   se lo pasan al API, que es quien realmente valida el acceso.
   ============================================================ */
(function () {
    "use strict";

    var API = "/api/murga";
    var TOKEN = new URLSearchParams(location.search).get("k") || "";
    // Ruta sin barra final: /murga, /murga/voluntades, ...
    var PATH = location.pathname.replace(/\/+$/, "");

    // ---------- helpers ----------
    function $(sel, root) { return (root || document).querySelector(sel); }
    function show(id) {
        var views = document.querySelectorAll(".view");
        for (var i = 0; i < views.length; i++) views[i].classList.remove("active");
        var el = document.getElementById(id);
        if (el) el.classList.add("active");
    }
    function toast(msg) {
        var t = $("#toast");
        t.textContent = msg;
        t.classList.add("show");
        clearTimeout(toast._t);
        toast._t = setTimeout(function () { t.classList.remove("show"); }, 2600);
    }
    function esc(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function withToken(url) {
        return url + (url.indexOf("?") === -1 ? "?" : "&") + "k=" + encodeURIComponent(TOKEN);
    }

    // ================= (1) FORMULARIO =================
    function initForm() {
        show("view-form");
        var form = $("#form"), err = $("#form-err"), btn = $("#btn-enviar");

        form.addEventListener("submit", function (ev) {
            ev.preventDefault();
            err.textContent = "";
            var nombre = $("#f-nombre").value.trim();
            var celular = $("#f-celular").value.trim();
            var voluntad = $("#f-voluntad").value.trim();
            if (!nombre || !celular || !voluntad) {
                err.textContent = "Faltan datos: los tres campos son obligatorios.";
                return;
            }
            btn.disabled = true; btn.textContent = "Registrando…";
            fetch(API + "/registrar", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ nombre: nombre, celular: celular, voluntad: voluntad })
            })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
                if (!res.ok) throw new Error((res.d && res.d.detail) || "Error al registrar");
                $("#g-nombre").textContent = res.d.nombre || nombre;
                form.reset();
                show("view-gracias");
                window.scrollTo({ top: 0, behavior: "smooth" });
            })
            .catch(function (e) { err.textContent = e.message || "No se pudo registrar. Reintentá."; })
            .finally(function () { btn.disabled = false; btn.textContent = "Registrar mi voluntad"; });
        });
    }

    // ================= (3) VOLUNTADES =================
    function initVoluntades() {
        show("view-voluntades");
        var lista = $("#v-lista"), vacio = $("#v-vacio"), deneg = $("#v-denegado"), total = $("#v-total");

        function render(items) {
            lista.innerHTML = items.map(function (v) {
                return '<div class="vol-item"><div class="vol-nombre">' + esc(v.nombre) +
                       '</div><div class="vol-texto">' + esc(v.voluntad) + "</div></div>";
            }).join("");
            vacio.style.display = items.length ? "none" : "block";
        }
        function load() {
            fetch(withToken(API + "/voluntades"))
                .then(function (r) {
                    if (r.status === 401) { deneg.style.display = "block"; throw new Error("401"); }
                    return r.json();
                })
                .then(function (d) {
                    deneg.style.display = "none";
                    total.textContent = d.total || 0;
                    render(d.voluntades || []);
                })
                .catch(function () { /* silencioso: reintenta en el próximo tick */ });
        }
        load();
        setInterval(load, 5000);              // auto-refresh cada 5s
        $("#v-refresh").addEventListener("click", load);
    }

    // ================= (4) SORTEO =================
    function initSorteo() {
        show("view-sorteo");
        var ruleta = $("#ruleta"), info = $("#s-info"), deneg = $("#s-denegado");
        var btnGo = $("#s-go"), btnGan = $("#s-ganador"), chkExcluir = $("#s-excluir");
        var participantes = [];   // lista completa (con flag excluido)
        var actual = null;        // ganador mostrado
        var girando = false;

        function elegibles() {
            return participantes.filter(function (p) {
                return chkExcluir.checked ? !p.excluido : true;
            });
        }
        function actualizarInfo() {
            var e = elegibles().length, t = participantes.length;
            info.textContent = t + " inscripto" + (t === 1 ? "" : "s") +
                " · " + e + " en juego";
            btnGo.disabled = e === 0;
        }
        function load(cb) {
            fetch(withToken(API + "/participantes"))
                .then(function (r) {
                    if (r.status === 401) { deneg.style.display = "block"; throw new Error("401"); }
                    return r.json();
                })
                .then(function (d) {
                    deneg.style.display = "none";
                    participantes = d.participantes || [];
                    actualizarInfo();
                    if (cb) cb();
                })
                .catch(function () {});
        }

        function sortear() {
            if (girando) return;
            var pool = elegibles();
            if (!pool.length) { toast("No quedan participantes en juego."); return; }
            girando = true;
            btnGo.disabled = true; btnGan.classList.add("hidden");
            actual = null;
            ruleta.classList.remove("ganador");
            ruleta.classList.add("girando");

            // Ganador definido de antemano; la animación es puro suspenso.
            var ganador = pool[Math.floor(Math.random() * pool.length)];
            var t0 = Date.now(), dur = 2600, delay = 60;

            function tick() {
                var elapsed = Date.now() - t0;
                var pick = pool[Math.floor(Math.random() * pool.length)];
                ruleta.textContent = pick.nombre;
                if (elapsed >= dur) {
                    ruleta.textContent = ganador.nombre;
                    ruleta.classList.remove("girando");
                    ruleta.classList.add("ganador");
                    actual = ganador;
                    girando = false;
                    btnGo.disabled = false;
                    btnGo.textContent = "Volver a sortear";
                    btnGan.classList.remove("hidden");
                    return;
                }
                // Va desacelerando: el intervalo crece cerca del final.
                delay = 60 + Math.pow(elapsed / dur, 3) * 320;
                setTimeout(tick, delay);
            }
            tick();
        }

        function marcarGanador() {
            if (!actual) return;
            btnGan.disabled = true;
            fetch(withToken(API + "/participantes/" + actual.id + "/excluir"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ excluido: true })
            })
            .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
            .then(function () {
                toast(actual.nombre + " marcado/a como ganador/a.");
                btnGan.classList.add("hidden");
                load();   // refresca flags y contador
            })
            .catch(function () { toast("No se pudo marcar. Reintentá."); })
            .finally(function () { btnGan.disabled = false; });
        }

        btnGo.addEventListener("click", sortear);
        btnGan.addEventListener("click", marcarGanador);
        chkExcluir.addEventListener("change", actualizarInfo);
        load();
    }

    // ================= (5) EXPORT =================
    function initExport() {
        show("view-export");
        var btn = $("#e-go"), deneg = $("#e-denegado"), count = $("#e-count");

        // Previsualiza cuántos hay (y valida el token de entrada).
        fetch(withToken(API + "/participantes"))
            .then(function (r) {
                if (r.status === 401) { deneg.style.display = "block"; btn.disabled = true; throw new Error("401"); }
                return r.json();
            })
            .then(function (d) { count.textContent = (d.total || 0) + " inscripto(s) para exportar."; })
            .catch(function () {});

        // Borrado total (limpiar datos de prueba / vaciar después del estreno).
        var btnReset = $("#e-reset");
        btnReset.addEventListener("click", function () {
            if (!confirm("¿Seguro que querés BORRAR TODOS los registros?\n\nEsto no se puede deshacer. Si no descargaste el Excel, hacelo antes.")) return;
            if (!confirm("Última confirmación: se borran TODAS las respuestas. ¿Continuar?")) return;
            btnReset.disabled = true; btnReset.textContent = "Borrando…";
            fetch(withToken(API + "/reset"), { method: "POST" })
                .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
                .then(function (d) {
                    toast("Listo: se borraron " + (d.borrados || 0) + " registro(s).");
                    count.textContent = "0 inscripto(s) para exportar.";
                })
                .catch(function () { toast("No se pudo borrar. Reintentá."); })
                .finally(function () { btnReset.disabled = false; btnReset.textContent = "Borrar todos los registros"; });
        });

        btn.addEventListener("click", function () {
            btn.disabled = true; btn.textContent = "Generando…";
            fetch(withToken(API + "/participantes"))
                .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
                .then(function (d) {
                    var rows = (d.participantes || []).map(function (p) {
                        return {
                            "Nombre": p.nombre,
                            "Celular": p.celular,
                            "Última voluntad": p.voluntad,
                            "Fecha/Hora": p.created_at ? new Date(p.created_at).toLocaleString("es-AR") : "",
                            "Ya ganó": p.excluido ? "Sí" : ""
                        };
                    });
                    var ws = XLSX.utils.json_to_sheet(rows);
                    ws["!cols"] = [{ wch: 24 }, { wch: 16 }, { wch: 50 }, { wch: 20 }, { wch: 8 }];
                    var wb = XLSX.utils.book_new();
                    XLSX.utils.book_append_sheet(wb, ws, "Inscriptos");
                    XLSX.writeFile(wb, "sorteo-la-abuela.xlsx");
                })
                .catch(function () { toast("No se pudo generar el Excel."); })
                .finally(function () { btn.disabled = false; btn.textContent = "Descargar Excel (.xlsx)"; });
        });
    }

    // ---------- router ----------
    if (/\/voluntades$/.test(PATH))      initVoluntades();
    else if (/\/sorteo$/.test(PATH))     initSorteo();
    else if (/\/export$/.test(PATH))     initExport();
    else                                 initForm();
})();
