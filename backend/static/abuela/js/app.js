/* ============================================================
   Panel interno de la murga — login + Caja (movimientos, proyección, remeras).
   Ensayos y Toques se suman en los próximos pasos.
   ============================================================ */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var TOKEN = localStorage.getItem("abuela_token") || "";

  // ---------- helpers ----------
  var pesos = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
  function fmt(n) { return "$ " + pesos.format(Math.round(n || 0)); }
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function hoy() { return new Date().toISOString().slice(0, 10); }
  function fechaCorta(f) {
    if (!f) return "";
    var p = String(f).slice(0, 10).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0].slice(2) : f;
  }
  function toast(msg) { var t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove("show"); }, 2600); }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Authorization": "Bearer " + TOKEN }, opts.headers || {});
    if (opts.body && typeof opts.body !== "string") { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.body); }
    return fetch("/api/abuela" + path, opts).then(function (r) {
      if (r.status === 401) { logout(); throw new Error("401"); }
      return r.json().then(function (d) { if (!r.ok) throw new Error(d.detail || "Error"); return d; });
    });
  }

  // ---------- login ----------
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); }
  function logout() { TOKEN = ""; localStorage.removeItem("abuela_token"); $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }

  $("#login-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var pass = $("#login-pass").value, err = $("#login-err");
    err.textContent = "";
    fetch("/api/abuela/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: pass }) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.d.detail || "Contraseña incorrecta");
        TOKEN = res.d.token; localStorage.setItem("abuela_token", TOKEN);
        showApp(); initCaja();
      })
      .catch(function (e2) { err.textContent = e2.message; });
  });
  $("#btn-logout").addEventListener("click", logout);

  // ---------- tabs ----------
  var SECCIONES = { caja: "Caja", ensayos: "Ensayos", toques: "Toques" };
  var tabActual = "caja";
  document.querySelectorAll(".tabbtn").forEach(function (b) {
    b.addEventListener("click", function () {
      tabActual = b.getAttribute("data-tab");
      document.querySelectorAll(".tabbtn").forEach(function (x) { x.classList.toggle("active", x === b); });
      document.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("active", t.id === "tab-" + tabActual); });
      $("#tb-section").textContent = SECCIONES[tabActual];
      actualizarFab();
    });
  });

  // ---------- modal ----------
  var modal = $("#modal");
  function abrirModal(titulo, html) { $("#modal-title").textContent = titulo; $("#modal-body").innerHTML = html; modal.classList.remove("hidden"); }
  function cerrarModal() { modal.classList.add("hidden"); }
  $("#modal-close").addEventListener("click", cerrarModal);
  modal.addEventListener("click", function (e) { if (e.target === modal) cerrarModal(); });

  // ---------- FAB ----------
  var fab = $("#fab");
  function actualizarFab() {
    if (tabActual === "caja") {
      fab.classList.remove("hidden");
      fab.onclick = (cajaSub === "remeras") ? formRemera : function () { formMovimiento(cajaSub === "proyeccion"); };
    } else { fab.classList.add("hidden"); }
  }

  // ============================================================
  // CAJA
  // ============================================================
  var cajaSub = "movimientos";

  function initCaja() {
    cargarResumen();
    document.querySelectorAll("[data-caja]").forEach(function (c) {
      c.addEventListener("click", function () {
        cajaSub = c.getAttribute("data-caja");
        document.querySelectorAll("[data-caja]").forEach(function (x) { x.classList.toggle("chip-on", x === c); });
        renderCajaSub();
        actualizarFab();
      });
    });
    renderCajaSub();
    actualizarFab();
  }

  function cargarResumen() {
    api("/caja").then(function (d) {
      var neg = d.saldo < 0;
      var html = '<div class="r-lbl">Saldo real</div>' +
        '<div class="r-saldo ' + (neg ? "neg" : "") + '">' + fmt(d.saldo) + '</div>' +
        '<div class="r-io"><span class="ing">Ingresos <b>' + fmt(d.ingresos) + '</b></span>' +
        '<span class="egr">Egresos <b>' + fmt(d.egresos) + '</b></span></div>' +
        '<div class="r-cuentas">' + d.cuentas.map(function (c) {
          return '<div class="r-cuenta"><span class="cu">' + esc(c.cuenta) + '</span><span class="sa">' + fmt(c.saldo) + '</span></div>';
        }).join("") + '</div>';
      if (d.proy_ingresos || d.proy_egresos) {
        html += '<div class="r-proy"><span>Con proyección</span><b>' + fmt(d.saldo_proyectado) + '</b></div>';
      }
      $("#caja-resumen").innerHTML = html;
    }).catch(function () {});
  }

  function renderCajaSub() {
    if (cajaSub === "remeras") return renderRemeras();
    renderMovimientos(cajaSub === "proyeccion");
  }

  function renderMovimientos(proy) {
    var body = $("#caja-body");
    body.innerHTML = '<div class="empty">Cargando…</div>';
    api("/caja/movimientos?proyectado=" + (proy ? "true" : "false")).then(function (d) {
      var items = d.movimientos || [];
      var total = items.reduce(function (a, x) { return a + (x.tipo.toLowerCase() === "ingreso" ? x.monto : -x.monto); }, 0);
      var head = '<div class="list-head"><span class="lh-t">' + (proy ? "Proyección" : "Movimientos") + '</span>' +
        '<span class="lh-sub">' + items.length + ' · neto ' + fmt(total) + '</span></div>';
      if (!items.length) { body.innerHTML = head + '<div class="empty">Sin movimientos. Tocá el + para agregar.</div>'; return; }
      body.innerHTML = head + '<div class="list">' + items.map(function (x) {
        var ing = x.tipo.toLowerCase() === "ingreso";
        return '<div class="row" data-id="' + x.id + '">' +
          '<div class="rc-main"><div class="rc-concepto">' + esc(x.concepto || "(sin concepto)") + '</div>' +
          '<div class="rc-meta">' + (x.fecha ? fechaCorta(x.fecha) + " · " : "") + esc(x.cuenta || "—") + '</div></div>' +
          '<div class="rc-monto ' + (ing ? "ing" : "egr") + '">' + (ing ? "+" : "−") + fmt(x.monto) + '</div>' +
          '<button class="rc-del" title="Borrar">🗑</button></div>';
      }).join("") + '</div>';
      body.querySelectorAll(".row").forEach(function (row) {
        row.querySelector(".rc-del").addEventListener("click", function () {
          if (!confirm("¿Borrar este movimiento?")) return;
          api("/caja/movimientos/" + row.getAttribute("data-id"), { method: "DELETE" })
            .then(function () { toast("Borrado."); cargarResumen(); renderMovimientos(proy); }).catch(function () { toast("No se pudo."); });
        });
      });
    }).catch(function () { body.innerHTML = '<div class="empty">Error al cargar.</div>'; });
  }

  function formMovimiento(proy) {
    abrirModal(proy ? "Nueva proyección" : "Nuevo movimiento",
      '<div class="field"><label>Tipo</label><div class="seg" id="f-seg">' +
        '<button type="button" data-t="Egreso" class="on-egr">Egreso</button>' +
        '<button type="button" data-t="Ingreso">Ingreso</button></div></div>' +
      (proy ? "" : '<div class="field"><label>Cuenta</label><select id="f-cuenta"><option>ClaroPay</option><option>Brubank</option><option value="">Otra…</option></select></div>') +
      '<div class="field"><label>Monto</label><input id="f-monto" type="number" inputmode="numeric" placeholder="0"></div>' +
      '<div class="field"><label>Concepto</label><input id="f-concepto" type="text" placeholder="¿De qué se trata?"></div>' +
      (proy ? "" : '<div class="field"><label>Fecha</label><input id="f-fecha" type="date" value="' + hoy() + '"></div>') +
      '<div class="form-err" id="f-err"></div>' +
      '<button class="btn btn-oro" id="f-save">Guardar</button>');
    var tipo = "Egreso";
    $("#f-seg").querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        tipo = b.getAttribute("data-t");
        $("#f-seg").querySelectorAll("button").forEach(function (x) { x.className = ""; });
        b.className = tipo === "Ingreso" ? "on-ing" : "on-egr";
      });
    });
    $("#f-save").addEventListener("click", function () {
      var monto = parseFloat($("#f-monto").value), err = $("#f-err");
      if (!monto || monto <= 0) { err.textContent = "Poné un monto mayor a 0."; return; }
      var payload = { tipo: tipo, monto: monto, concepto: $("#f-concepto").value.trim(), proyectado: !!proy,
        cuenta: proy ? "" : $("#f-cuenta").value, fecha: proy ? "" : $("#f-fecha").value };
      $("#f-save").disabled = true;
      api("/caja/movimientos", { method: "POST", body: payload })
        .then(function () { cerrarModal(); toast("Guardado."); cargarResumen(); renderMovimientos(!!proy); })
        .catch(function (e) { err.textContent = e.message; $("#f-save").disabled = false; });
    });
  }

  // ---------- Remeras ----------
  function renderRemeras() {
    var body = $("#caja-body");
    body.innerHTML = '<div class="empty">Cargando…</div>';
    api("/remeras").then(function (d) {
      var head = '<div class="list-head"><span class="lh-t">Remeras</span>' +
        '<span class="lh-sub">' + d.pagas + ' pagas · ' + d.deben + ' deben · ' + fmt(d.recaudado) + '</span></div>';
      if (!d.remeras.length) { body.innerHTML = head + '<div class="empty">Sin remeras. Tocá el + para agregar.</div>'; return; }
      body.innerHTML = head + '<div class="list">' + d.remeras.map(function (r) {
        return '<div class="row ' + (r.pago ? "paga" : "") + '" data-id="' + r.id + '">' +
          '<button class="rem-toggle ' + (r.pago ? "on" : "") + '" title="Marcar pago"></button>' +
          '<div class="rc-main"><div class="rc-concepto">' + esc(r.nombre) + '</div>' +
          (r.nota ? '<div class="rc-meta">' + esc(r.nota) + '</div>' : "") + '</div>' +
          '<div class="rc-monto">' + fmt(r.monto) + '</div>' +
          '<button class="rc-del" title="Borrar">🗑</button></div>';
      }).join("") + '</div>';
      body.querySelectorAll(".row").forEach(function (row) {
        var id = row.getAttribute("data-id");
        row.querySelector(".rem-toggle").addEventListener("click", function () {
          api("/remeras/" + id + "/toggle", { method: "POST" }).then(function () { renderRemeras(); }).catch(function () {});
        });
        row.querySelector(".rc-del").addEventListener("click", function () {
          if (!confirm("¿Borrar de la lista?")) return;
          api("/remeras/" + id, { method: "DELETE" }).then(function () { renderRemeras(); }).catch(function () {});
        });
      });
    }).catch(function () { body.innerHTML = '<div class="empty">Error al cargar.</div>'; });
  }

  function formRemera() {
    abrirModal("Nueva remera",
      '<div class="field"><label>Nombre</label><input id="r-nombre" type="text" placeholder="Nombre"></div>' +
      '<div class="field"><label>Monto</label><input id="r-monto" type="number" inputmode="numeric" value="20000"></div>' +
      '<div class="field"><label>Nota (opcional)</label><input id="r-nota" type="text" placeholder="Ej: familia, seña…"></div>' +
      '<label style="display:flex;gap:9px;align-items:center;margin-bottom:14px;font-weight:600;color:var(--soft)"><input id="r-pago" type="checkbox" style="width:20px;height:20px;accent-color:var(--ok)"> Ya pagó</label>' +
      '<div class="form-err" id="r-err"></div><button class="btn btn-oro" id="r-save">Agregar</button>');
    $("#r-save").addEventListener("click", function () {
      var nombre = $("#r-nombre").value.trim(), err = $("#r-err");
      if (!nombre) { err.textContent = "Falta el nombre."; return; }
      $("#r-save").disabled = true;
      api("/remeras", { method: "POST", body: { nombre: nombre, monto: parseFloat($("#r-monto").value) || 20000, nota: $("#r-nota").value.trim(), pago: $("#r-pago").checked } })
        .then(function () { cerrarModal(); toast("Agregada."); renderRemeras(); })
        .catch(function (e) { err.textContent = e.message; $("#r-save").disabled = false; });
    });
  }

  // ---------- arranque ----------
  if (TOKEN) {
    // validar el token con una llamada liviana
    api("/caja").then(function () { showApp(); initCaja(); }).catch(function () { logout(); });
  }
})();
