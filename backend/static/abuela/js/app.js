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
  function fechaDMY(f) {  // deja las fechas en DD/MM/AAAA cuando se puede
    f = String(f || "").trim();
    var iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(f);
    if (iso) return iso[3] + "/" + iso[2] + "/" + iso[1];
    var dmy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(f);
    if (dmy) return dmy[1].padStart(2, "0") + "/" + dmy[2].padStart(2, "0") + "/" + dmy[3];
    return f;
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
      if (tabActual === "ensayos" && !ensayosInit) { ensayosInit = true; initEnsayos(); }
      if (tabActual === "toques" && !toquesInit) { toquesInit = true; renderToquesList(); }
      actualizarFab();
    });
  });

  // ---------- modal ----------
  var modal = $("#modal"), _onModalClose = null;
  function abrirModal(titulo, html) { _onModalClose = null; $("#modal-title").textContent = titulo; $("#modal-body").innerHTML = html; modal.classList.remove("hidden"); }
  function cerrarModal() { modal.classList.add("hidden"); if (_onModalClose) { var f = _onModalClose; _onModalClose = null; f(); } }
  $("#modal-close").addEventListener("click", cerrarModal);
  modal.addEventListener("click", function (e) { if (e.target === modal) cerrarModal(); });

  // ---------- FAB ----------
  var fab = $("#fab");
  function actualizarFab() {
    if (tabActual === "caja") {
      fab.classList.remove("hidden");
      fab.onclick = function () { formMovimiento(cajaSub === "proyeccion"); };
    } else if (tabActual === "ensayos") {
      fab.classList.remove("hidden"); fab.onclick = formNuevoEnsayo;
    } else if (tabActual === "toques") {
      fab.classList.remove("hidden"); fab.onclick = formNuevoToque;
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
        '<div class="r-cuentas">' + d.cuentas.map(function (c) {
          return '<div class="r-cuenta"><span class="cu">' + esc(c.cuenta) + '</span><span class="sa">' + fmt(c.saldo) + '</span></div>';
        }).join("") + '</div>';
      if (d.proy_ingresos || d.proy_egresos) {
        html += '<div class="r-proy"><span>Con proyección</span><b>' + fmt(d.saldo_proyectado) + '</b></div>';
      }
      $("#caja-resumen").innerHTML = html;
    }).catch(function () {});
  }

  function renderCajaSub() { renderMovimientos(cajaSub === "proyeccion"); }

  function renderMovimientos(proy) {
    var body = $("#caja-body");
    body.innerHTML = '<div class="empty">Cargando…</div>';
    api("/caja/movimientos?proyectado=" + (proy ? "true" : "false")).then(function (d) {
      var items = d.movimientos || [];
      var head = '<div class="list-head"><span class="lh-t">' + (proy ? "Proyección" : "Movimientos") + '</span></div>';
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

  // ============================================================
  // ENSAYOS  (registro histórico único · puntaje por rango · evolución)
  // ============================================================
  var ensayosInit = false, ensSub = "ensayos", ensRango = "mes", rosterActivos = null;
  var DOW = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

  function fechaLarga(f) {
    var mt = /^(\d{4})-(\d{2})-(\d{2})/.exec(f || "");
    if (!mt) return f || "";
    var d = new Date(+mt[1], +mt[2] - 1, +mt[3]);
    return DOW[d.getDay()] + " " + mt[3] + "/" + mt[2] + "/" + mt[1];
  }
  function proximoEnsayo() {  // próximo martes o sábado (días de ensayo)
    var d = new Date();
    for (var i = 0; i < 7; i++) { var g = d.getDay(); if (g === 2 || g === 6) break; d.setDate(d.getDate() + 1); }
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function desdeRango(r) {
    var d = new Date();
    if (r === "mes") d.setMonth(d.getMonth() - 1);
    else if (r === "3meses") d.setMonth(d.getMonth() - 3);
    else if (r === "2026") return "2026-01-01";
    else return "";
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function cargarRoster(cb) {
    if (rosterActivos) { cb(); return; }
    api("/roster").then(function (d) { rosterActivos = d.murguistas.filter(function (x) { return x.activo; }); cb(); }).catch(function () { rosterActivos = []; cb(); });
  }

  function initEnsayos() {
    document.querySelectorAll("[data-ens]").forEach(function (c) {
      c.addEventListener("click", function () {
        ensSub = c.getAttribute("data-ens");
        document.querySelectorAll("[data-ens]").forEach(function (x) { x.classList.toggle("chip-on", x === c); });
        renderEnsayosSub();
      });
    });
    renderEnsayosSub();
  }
  function renderEnsayosSub() { if (ensSub === "puntaje") renderPuntaje(); else renderEnsayosList(); }

  function renderEnsayosList() {
    var body = $("#ensayos-body");
    body.innerHTML = '<div class="empty">Cargando…</div>';
    api("/ensayos/todos").then(function (d) {
      var items = d.ensayos || [];
      if (!items.length) { body.innerHTML = '<div class="empty">Sin ensayos. Tocá el + para registrar uno.</div>'; return; }
      body.innerHTML = '<div class="list-head"><span class="lh-t">Ensayos</span></div><div class="list">' +
        items.map(function (e) {
          return '<button class="ens-row" data-id="' + e.id + '" data-fecha="' + esc(e.fecha) + '">' +
            '<div><div class="ed">' + fechaLarga(e.fecha) + '</div><div class="em">' + e.marcas + ' marcadas</div></div><span class="earr">›</span></button>';
        }).join("") + "</div>";
      body.querySelectorAll(".ens-row").forEach(function (r) { r.addEventListener("click", function () { openMarcado(r.getAttribute("data-id"), r.getAttribute("data-fecha")); }); });
    }).catch(function () { body.innerHTML = '<div class="empty">Error al cargar.</div>'; });
  }

  function openMarcado(id, fecha) {
    cargarRoster(function () {
      api("/ensayos/id/" + id).then(function (d) {
        var marcas = d.marcas || {}, CODES = ["P", "T", "M", "A", "X"];
        var rows = rosterActivos.map(function (mu) {
          var cur = marcas[mu.nombre] || "";
          return '<div class="marca-row" data-nom="' + esc(mu.nombre) + '"><span class="marca-nom">' + esc(mu.nombre) + '</span><div class="marca-btns">' +
            CODES.map(function (cd) { return '<button class="mb mb-' + cd + (cur === cd ? " on" : "") + '" data-cod="' + cd + '">' + cd + "</button>"; }).join("") + "</div></div>";
        }).join("");
        abrirModal("Ensayo · " + fechaLarga(fecha),
          '<div class="marca-help">P presente · T tarde · M muy tarde · A ausente c/aviso · X ausente s/aviso. Tocá de nuevo para desmarcar.</div>' +
          rows + '<button class="btn btn-danger modal-del" id="ens-del">Borrar este ensayo</button>');
        _onModalClose = renderEnsayosList;
        $("#modal-body").querySelectorAll(".marca-row").forEach(function (row) {
          var nom = row.getAttribute("data-nom");
          row.querySelectorAll(".mb").forEach(function (b) {
            b.addEventListener("click", function () {
              var nuevo = b.classList.contains("on") ? "" : b.getAttribute("data-cod");
              api("/ensayos/marca", { method: "POST", body: { ensayo_id: +id, nombre: nom, codigo: nuevo } }).then(function () {
                row.querySelectorAll(".mb").forEach(function (x) { x.classList.remove("on"); });
                if (nuevo) b.classList.add("on");
              }).catch(function () { toast("No se pudo."); });
            });
          });
        });
        $("#ens-del").addEventListener("click", function () {
          if (!confirm("¿Borrar este ensayo y todas sus marcas?")) return;
          api("/ensayos/id/" + id, { method: "DELETE" }).then(function () { _onModalClose = null; cerrarModal(); toast("Ensayo borrado."); renderEnsayosList(); }).catch(function () { toast("No se pudo."); });
        });
      }).catch(function () { toast("No se pudo abrir."); });
    });
  }

  function renderPuntaje() {
    var body = $("#ensayos-body");
    var opts = [["mes", "Último mes"], ["3meses", "Últimos 3 meses"], ["2026", "2026"], ["todo", "Todo"]];
    var chips = opts.map(function (r) { return '<button class="chip' + (ensRango === r[0] ? " chip-on" : "") + '" data-rango="' + r[0] + '">' + r[1] + "</button>"; }).join("");
    body.innerHTML = '<div class="subnav" style="margin-bottom:12px">' + chips + '</div><div id="rank-list"><div class="empty">Cargando…</div></div>';
    body.querySelectorAll("[data-rango]").forEach(function (c) { c.addEventListener("click", function () { ensRango = c.getAttribute("data-rango"); renderPuntaje(); }); });
    api("/ensayos/puntaje?desde=" + encodeURIComponent(desdeRango(ensRango))).then(function (d) {
      var r = d.ranking || [], cont = $("#rank-list");
      if (!r.length) { cont.innerHTML = '<div class="empty">Sin datos.</div>'; return; }
      cont.innerHTML = '<div class="list-head"><span class="lh-t">Puntaje</span><span class="lh-sub">' + d.ensayos + ' ensayos</span></div><div class="list">' +
        r.map(function (x, i) {
          return '<button class="rank-row ' + (x.activo ? "" : "inact") + '" data-nom="' + esc(x.nombre) + '"><span class="rank-pos">' + (i + 1) + '</span>' +
            '<div class="rank-main"><div class="rank-nom">' + esc(x.nombre) + (x.activo ? "" : " · histórico") + '</div>' +
            '<div class="rank-detalle">P' + x.P + " · T" + x.T + " · M" + x.M + " · A" + x.A + " · X" + x.X + '</div></div>' +
            '<span class="rank-pts">' + x.puntaje + "</span></button>";
        }).join("") + "</div>";
      cont.querySelectorAll(".rank-row").forEach(function (row) { row.addEventListener("click", function () { openEvolucion(row.getAttribute("data-nom")); }); });
    }).catch(function () { $("#rank-list").innerHTML = '<div class="empty">Error al cargar.</div>'; });
  }

  function openEvolucion(nombre) {
    api("/ensayos/murguista?nombre=" + encodeURIComponent(nombre) + "&limit=16").then(function (d) {
      var evo = (d.evolucion || []).slice().reverse();  // izquierda = más viejo, derecha = más nuevo
      var cells = evo.map(function (x) {
        var cod = x.codigo || "", cls = cod ? "evo-" + cod : "evo-none";
        return '<span class="evo-cell ' + cls + '" title="' + esc(fechaLarga(x.fecha)) + '">' + (cod || "·") + "</span>";
      }).join("");
      var ult = evo.slice(-5);
      var faltas = ult.filter(function (x) { return !x.codigo || x.codigo === "A" || x.codigo === "X"; }).length;
      var alerta = (ult.length >= 3 && faltas >= 3) ? '<div class="evo-alerta">⚠ Viene faltando en los últimos ensayos.</div>' : "";
      abrirModal(nombre,
        '<div class="marca-help">Evolución reciente (← más viejo · más nuevo →). Puntaje del tramo: <b>' + d.puntaje + '</b></div>' +
        '<div class="evo-wrap">' + cells + '</div>' + alerta +
        '<div class="marca-help">P presente · T tarde · M muy tarde · A ausente c/aviso · X ausente s/aviso · &nbsp;·&nbsp; sin registro</div>');
    }).catch(function () { toast("No se pudo abrir."); });
  }

  function formNuevoEnsayo() {
    abrirModal("Nuevo ensayo",
      '<div class="field"><label>Fecha</label><input id="ne-fecha" type="date" value="' + proximoEnsayo() + '"></div>' +
      '<div class="marca-help">Sugerida: el próximo martes o sábado (días de ensayo).</div>' +
      '<div class="form-err" id="ne-err"></div><button class="btn btn-oro" id="ne-save">Crear y marcar</button>');
    $("#ne-save").addEventListener("click", function () {
      var fecha = $("#ne-fecha").value, err = $("#ne-err");
      if (!fecha) { err.textContent = "Elegí una fecha."; return; }
      $("#ne-save").disabled = true;
      api("/ensayos", { method: "POST", body: { fecha: fecha } }).then(function (nw) {
        _onModalClose = null; cerrarModal(); toast("Ensayo creado."); ensSub = "ensayos";
        document.querySelectorAll("[data-ens]").forEach(function (x) { x.classList.toggle("chip-on", x.getAttribute("data-ens") === "ensayos"); });
        renderEnsayosList(); openMarcado(nw.id, nw.fecha);
      }).catch(function (e) { err.textContent = e.message; $("#ne-save").disabled = false; });
    });
  }

  // ============================================================
  // TOQUES
  // ============================================================
  var toquesInit = false;
  var FICHA = [
    { k: "nombre", l: "Título", t: "text" }, { k: "fecha", l: "Fecha (DD/MM/AAAA)", t: "text" },
    { k: "lugar", l: "Lugar", t: "text" }, { k: "evento", l: "Evento", t: "text" },
    { k: "condicion_eco", l: "Condición económica", t: "text" }, { k: "duracion", l: "Duración", t: "text" },
    { k: "horario", l: "Horario y convocatoria", t: "text" }, { k: "sonido", l: "Sonido", t: "text" },
    { k: "prueba_sonido", l: "Prueba de sonido", t: "text" }, { k: "camarin", l: "Camarín", t: "text" },
    { k: "cachet", l: "Cachet / retribución", t: "text" }, { k: "factura", l: "Con/sin factura", t: "text" },
    { k: "entradas", l: "Entradas (valor)", t: "text" }, { k: "viaticos", l: "Viáticos", t: "text" },
    { k: "comida", l: "Comida", t: "text" }, { k: "bebida", l: "Bebida", t: "text" },
    { k: "otros", l: "Otros", t: "textarea" }, { k: "contacto", l: "Contacto", t: "text" },
    { k: "encargado", l: "Encargado ejecutiva", t: "text" }, { k: "repertorio", l: "Repertorio", t: "text" },
  ];

  function renderToquesList() {
    var body = $("#toques-body");
    body.innerHTML = '<div class="empty">Cargando…</div>';
    api("/toques").then(function (d) {
      var items = d.toques || [];
      if (!items.length) { body.innerHTML = '<div class="empty">Sin toques. Tocá el + para agregar.</div>'; return; }
      body.innerHTML = '<div class="list-head"><span class="lh-t">Toques</span><span class="lh-sub">' + items.length + '</span></div><div class="list">' +
        items.map(function (t) {
          var meta = [fechaDMY(t.fecha), fechaDMY(t.lugar), t.condicion_eco].filter(Boolean).map(esc).join(" · ");
          return '<button class="ens-row" data-id="' + t.id + '"><div><div class="ed">' + esc(t.nombre || t.lugar || "Toque") + '</div><div class="em">' + meta + '</div></div><span class="earr">›</span></button>';
        }).join("") + "</div>";
      body.querySelectorAll(".ens-row").forEach(function (r) { r.addEventListener("click", function () { openToque(r.getAttribute("data-id")); }); });
    }).catch(function () { body.innerHTML = '<div class="empty">Error al cargar.</div>'; });
  }

  function openToque(id) {
    cargarRoster(function () {
      api("/toques/" + id).then(function (t) {
        var campos = FICHA.map(function (f) {
          var v = esc(t[f.k] || "");
          if (f.t === "textarea") return '<div class="field"><label>' + f.l + '</label><textarea data-k="' + f.k + '">' + v + "</textarea></div>";
          return '<div class="field"><label>' + f.l + '</label><input data-k="' + f.k + '" type="text" value="' + v + '"></div>';
        }).join("");
        var asist = t.asistencia || {};
        var chips = rosterActivos.map(function (mu) {
          return '<button class="sub-chip' + (asist[mu.nombre] ? " on" : "") + '" data-nom="' + esc(mu.nombre) + '">' + esc(mu.nombre) + "</button>";
        }).join("");
        var subieron = Object.keys(asist).filter(function (n) { return asist[n]; }).length;
        abrirModal(t.nombre || "Toque",
          '<div class="tsec">Ficha del toque</div>' + campos +
          '<div class="tsec">¿Quién subió? (' + subieron + ')</div><div class="subs" id="tq-subs">' + chips + "</div>" +
          '<button class="btn btn-oro" id="tq-save" style="margin-top:18px">Guardar cambios</button>' +
          '<button class="btn btn-danger modal-del" id="tq-del">Borrar toque</button>');
        _onModalClose = renderToquesList;
        $("#tq-subs").querySelectorAll(".sub-chip").forEach(function (b) {
          b.addEventListener("click", function () {
            var nom = b.getAttribute("data-nom"), nuevo = !b.classList.contains("on");
            api("/toques/subio", { method: "POST", body: { toque_id: +id, nombre: nom, subio: nuevo } })
              .then(function () { b.classList.toggle("on", nuevo); }).catch(function () { toast("No se pudo."); });
          });
        });
        $("#tq-save").addEventListener("click", function () {
          var payload = {};
          $("#modal-body").querySelectorAll("[data-k]").forEach(function (el) { payload[el.getAttribute("data-k")] = el.value; });
          $("#tq-save").disabled = true;
          api("/toques/" + id, { method: "PUT", body: payload }).then(function () {
            toast("Guardado."); $("#modal-title").textContent = payload.nombre || "Toque"; $("#tq-save").disabled = false;
          }).catch(function (e) { toast(e.message); $("#tq-save").disabled = false; });
        });
        $("#tq-del").addEventListener("click", function () {
          if (!confirm("¿Borrar este toque?")) return;
          api("/toques/" + id, { method: "DELETE" }).then(function () { _onModalClose = null; cerrarModal(); toast("Toque borrado."); renderToquesList(); }).catch(function () { toast("No se pudo."); });
        });
      }).catch(function () { toast("No se pudo abrir."); });
    });
  }

  function formNuevoToque() {
    abrirModal("Nuevo toque",
      '<div class="field"><label>Nombre / lugar</label><input id="nt-nombre" type="text" placeholder="Ej: Carnaval Barrio X"></div>' +
      '<div class="field"><label>Fecha</label><input id="nt-fecha" type="text" placeholder="Ej: 15/11 o 2026-11-15"></div>' +
      '<div class="field"><label>Condición económica</label><input id="nt-cond" type="text" placeholder="Cachet / % / gratuito / viáticos"></div>' +
      '<div class="marca-help">Después de crear se abre la ficha completa para cargar el resto.</div>' +
      '<div class="form-err" id="nt-err"></div><button class="btn btn-oro" id="nt-save">Crear y completar</button>');
    $("#nt-save").addEventListener("click", function () {
      var nombre = $("#nt-nombre").value.trim(), err = $("#nt-err");
      if (!nombre) { err.textContent = "Poné el nombre o lugar."; return; }
      $("#nt-save").disabled = true;
      api("/toques", { method: "POST", body: { nombre: nombre, fecha: $("#nt-fecha").value.trim(), condicion_eco: $("#nt-cond").value.trim() } })
        .then(function (nw) { _onModalClose = null; cerrarModal(); toast("Toque creado."); renderToquesList(); openToque(nw.id); })
        .catch(function (e) { err.textContent = e.message; $("#nt-save").disabled = false; });
    });
  }

  // ---------- arranque ----------
  if (TOKEN) {
    // validar el token con una llamada liviana
    api("/caja").then(function () { showApp(); initCaja(); }).catch(function () { logout(); });
  }
})();
