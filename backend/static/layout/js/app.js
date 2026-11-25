/* ============================================================
   Armador de placas de cobertura — BCR.
   Composición 1080x1920 (9:16) en <canvas>: fondo azul BCR, 1-3 fotos
   ajustables (mover + zoom), un párrafo (IBM Plex Sans) y el logo BCR.
   Exporta PNG a resolución real. Todo client-side (sin backend).
   ============================================================ */
(function () {
    "use strict";

    var W = 1080, H = 1920;
    var canvas = document.getElementById("canvas");
    var ctx = canvas.getContext("2d");

    // Plantillas: rects (en espacio 1080x1920). frames = marcos de foto; text = bloque de texto.
    var TEMPLATES = {
        1: { frames: [{ x: 56, y: 56, w: 968, h: 1040 }], text: { x: 88, y: 1130, w: 904, h: 540 } },
        2: { frames: [{ x: 56, y: 56, w: 968, h: 678 }, { x: 56, y: 1026, w: 968, h: 644 }], text: { x: 88, y: 762, w: 904, h: 236 } },
        3: { frames: [{ x: 56, y: 56, w: 968, h: 700 }, { x: 56, y: 788, w: 470, h: 548 }, { x: 554, y: 788, w: 470, h: 548 }], text: { x: 88, y: 1372, w: 904, h: 300 } }
    };
    var RADIUS = 24;

    var state = {
        tpl: 2,
        text: document.getElementById("txt").value,
        photos: {},   // "tpl:index" -> {img, scale, ox, oy}
        sel: null     // index del marco seleccionado
    };

    var logo = new Image();
    var logoReady = false;
    logo.onload = function () { logoReady = true; render(); };
    logo.src = "logo_bcr_white.png";

    function key(i) { return state.tpl + ":" + i; }
    function getPhoto(i) { return state.photos[key(i)]; }

    // ---------- helpers ----------
    function $(s) { return document.querySelector(s); }
    function toast(m) {
        var t = $("#toast"); t.textContent = m; t.classList.add("show");
        clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove("show"); }, 2400);
    }
    function roundRect(c, x, y, w, h, r) {
        r = Math.min(r, w / 2, h / 2);
        c.beginPath();
        c.moveTo(x + r, y);
        c.arcTo(x + w, y, x + w, y + h, r);
        c.arcTo(x + w, y + h, x, y + h, r);
        c.arcTo(x, y + h, x, y, r);
        c.arcTo(x, y, x + w, y, r);
        c.closePath();
    }
    function coverScale(img, f) { return Math.max(f.w / img.width, f.h / img.height); }
    function clampOffsets(p, f) {
        var s = coverScale(p.img, f) * p.scale;
        var dw = p.img.width * s, dh = p.img.height * s;
        var mx = Math.max(0, (dw - f.w) / 2), my = Math.max(0, (dh - f.h) / 2);
        p.ox = Math.max(-mx, Math.min(mx, p.ox));
        p.oy = Math.max(-my, Math.min(my, p.oy));
    }

    // ---------- fuentes ----------
    function ensureFonts() {
        if (!document.fonts || !document.fonts.load) return Promise.resolve();
        return Promise.all([
            document.fonts.load("500 52px 'IBM Plex Sans'"),
            document.fonts.load("600 52px 'IBM Plex Sans'")
        ]).catch(function () {});
    }

    // ---------- render ----------
    function drawBackground() {
        var g = ctx.createLinearGradient(0, 0, 0, H);
        g.addColorStop(0, "#163a73");
        g.addColorStop(1, "#112d5c");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
    }

    function drawPhoto(i, f, exporting) {
        var p = getPhoto(i);
        ctx.save();
        roundRect(ctx, f.x, f.y, f.w, f.h, RADIUS);
        ctx.clip();
        if (p && p.img) {
            var s = coverScale(p.img, f) * p.scale;
            var dw = p.img.width * s, dh = p.img.height * s;
            var dx = f.x + (f.w - dw) / 2 + p.ox;
            var dy = f.y + (f.h - dh) / 2 + p.oy;
            ctx.drawImage(p.img, dx, dy, dw, dh);
        } else {
            // placeholder
            ctx.fillStyle = "rgba(255,255,255,.06)";
            ctx.fillRect(f.x, f.y, f.w, f.h);
            ctx.fillStyle = "rgba(255,255,255,.5)";
            ctx.textAlign = "center"; ctx.textBaseline = "middle";
            ctx.font = "600 34px 'IBM Plex Sans'";
            ctx.fillText("＋ Agregar foto", f.x + f.w / 2, f.y + f.h / 2);
        }
        ctx.restore();
        // selección (no se exporta)
        if (!exporting && state.sel === i) {
            ctx.save();
            roundRect(ctx, f.x + 2, f.y + 2, f.w - 4, f.h - 4, RADIUS);
            ctx.strokeStyle = "#3EA3DC"; ctx.lineWidth = 6; ctx.stroke();
            ctx.restore();
        }
    }

    function wrapLines(text, maxW, font) {
        ctx.font = font;
        var out = [];
        text.split(/\n/).forEach(function (para) {
            var words = para.split(/\s+/), line = "";
            for (var i = 0; i < words.length; i++) {
                var test = line ? line + " " + words[i] : words[i];
                if (ctx.measureText(test).width > maxW && line) { out.push(line); line = words[i]; }
                else line = test;
            }
            out.push(line);
        });
        return out;
    }

    function drawText(t) {
        var txt = (state.text || "").trim();
        if (!txt) return;
        // auto-fit: bajamos el tamaño hasta que entre en el alto del bloque.
        var size = 54, lh = 1.3, lines, font;
        for (; size >= 28; size -= 2) {
            font = "500 " + size + "px 'IBM Plex Sans'";
            lines = wrapLines(txt, t.w, font);
            if (lines.length * size * lh <= t.h) break;
        }
        ctx.font = font;
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        var total = lines.length * size * lh;
        var cy = t.y + t.h / 2 - total / 2 + size * lh / 2;
        // acento sobre el texto (vuelta de rosca)
        ctx.save();
        ctx.strokeStyle = "#3EA3DC"; ctx.lineWidth = 5; ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(t.x + t.w / 2 - 44, t.y - 2); ctx.lineTo(t.x + t.w / 2 + 44, t.y - 2); ctx.stroke();
        ctx.restore();
        lines.forEach(function (ln, idx) {
            ctx.fillText(ln, t.x + t.w / 2, cy + idx * size * lh);
        });
    }

    function drawLogo() {
        if (!logoReady) return;
        var targetW = 280;
        var r = logo.height / logo.width;
        var lw = targetW, lh = targetW * r;
        var x = (W - lw) / 2, y = H - 64 - lh;
        ctx.drawImage(logo, x, y, lw, lh);
    }

    function render(exporting) {
        var tpl = TEMPLATES[state.tpl];
        drawBackground();
        tpl.frames.forEach(function (f, i) { drawPhoto(i, f, exporting); });
        drawText(tpl.text);
        drawLogo();
    }

    // ---------- interacción (mover + zoom) ----------
    var pointers = {};   // id -> {x,y}
    var dragging = false, lastPt = null, pinch = null;

    function toCanvas(e) {
        var r = canvas.getBoundingClientRect();
        return { x: (e.clientX - r.left) * (W / r.width), y: (e.clientY - r.top) * (H / r.height) };
    }
    function frameAt(pt) {
        var fr = TEMPLATES[state.tpl].frames;
        for (var i = 0; i < fr.length; i++) {
            var f = fr[i];
            if (pt.x >= f.x && pt.x <= f.x + f.w && pt.y >= f.y && pt.y <= f.y + f.h) return i;
        }
        return null;
    }

    canvas.addEventListener("pointerdown", function (e) {
        canvas.setPointerCapture(e.pointerId);
        var pt = toCanvas(e);
        pointers[e.pointerId] = pt;
        var ids = Object.keys(pointers);
        if (ids.length === 1) {
            var i = frameAt(pt);
            if (i === null) return;
            selectFrame(i);
            if (!getPhoto(i)) { openPicker(i); return; }
            dragging = true; lastPt = pt;
        } else if (ids.length === 2 && getPhoto(state.sel)) {
            var a = pointers[ids[0]], b = pointers[ids[1]];
            pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), scale: getPhoto(state.sel).scale };
            dragging = false;
        }
    });

    canvas.addEventListener("pointermove", function (e) {
        if (!(e.pointerId in pointers)) return;
        var pt = toCanvas(e);
        pointers[e.pointerId] = pt;
        var ids = Object.keys(pointers);
        if (pinch && ids.length >= 2) {
            var a = pointers[ids[0]], b = pointers[ids[1]];
            var d = Math.hypot(a.x - b.x, a.y - b.y);
            var p = getPhoto(state.sel); if (!p) return;
            p.scale = Math.max(1, Math.min(4, pinch.scale * (d / pinch.d)));
            clampOffsets(p, TEMPLATES[state.tpl].frames[state.sel]);
            $("#zoom").value = p.scale;
            render();
        } else if (dragging && lastPt) {
            var p2 = getPhoto(state.sel); if (!p2) return;
            p2.ox += (pt.x - lastPt.x); p2.oy += (pt.y - lastPt.y);
            clampOffsets(p2, TEMPLATES[state.tpl].frames[state.sel]);
            lastPt = pt; render();
        }
    });

    function endPointer(e) {
        delete pointers[e.pointerId];
        if (Object.keys(pointers).length < 2) pinch = null;
        if (Object.keys(pointers).length === 0) { dragging = false; lastPt = null; }
    }
    canvas.addEventListener("pointerup", endPointer);
    canvas.addEventListener("pointercancel", endPointer);

    // ---------- selección / tools ----------
    function selectFrame(i) {
        state.sel = i;
        var p = getPhoto(i);
        $("#no-sel").classList.toggle("hidden", !!p);
        $("#sel-tools").classList.toggle("hidden", !p);
        if (p) $("#zoom").value = p.scale;
        render();
    }

    // ---------- carga de archivos ----------
    var pendingFrame = null;
    var fileInput = document.getElementById("file");
    function openPicker(i) { pendingFrame = i; fileInput.value = ""; fileInput.click(); }

    fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file || pendingFrame === null) return;
        var reader = new FileReader();
        reader.onload = function (ev) {
            var img = new Image();
            img.onload = function () {
                state.photos[key(pendingFrame)] = { img: img, scale: 1, ox: 0, oy: 0 };
                selectFrame(pendingFrame);
                render();
            };
            img.src = ev.target.result;
        };
        reader.readAsDataURL(file);
    });

    $("#zoom").addEventListener("input", function (e) {
        var p = getPhoto(state.sel); if (!p) return;
        p.scale = parseFloat(e.target.value);
        clampOffsets(p, TEMPLATES[state.tpl].frames[state.sel]);
        render();
    });
    $("#btn-replace").addEventListener("click", function () { if (state.sel !== null) openPicker(state.sel); });
    $("#btn-remove").addEventListener("click", function () {
        if (state.sel === null) return;
        delete state.photos[key(state.sel)];
        selectFrame(state.sel);
    });

    // ---------- plantilla ----------
    document.getElementById("tpl-seg").addEventListener("click", function (e) {
        var b = e.target.closest("button[data-tpl]"); if (!b) return;
        var t = this.querySelectorAll("button");
        for (var i = 0; i < t.length; i++) t[i].classList.toggle("on", t[i] === b);
        state.tpl = +b.getAttribute("data-tpl");
        state.sel = null;
        $("#no-sel").classList.remove("hidden"); $("#sel-tools").classList.add("hidden");
        render();
    });

    // ---------- texto ----------
    document.getElementById("txt").addEventListener("input", function (e) {
        state.text = e.target.value; render();
    });

    // ---------- descarga ----------
    function doDownload() {
        var faltan = TEMPLATES[state.tpl].frames.some(function (f, i) { return !getPhoto(i); });
        ensureFonts().then(function () {
            var selBak = state.sel; state.sel = null;   // sin marco de selección
            render(true);
            state.sel = selBak;
            canvas.toBlob(function (blob) {
                render();
                if (!blob) { toast("No se pudo generar la imagen."); return; }
                var url = URL.createObjectURL(blob);
                $("#dl-img").src = url;
                $("#dl-link").href = url;
                $("#dl-modal").classList.remove("hidden");
                if (faltan) toast("Ojo: hay recuadros sin foto.");
            }, "image/png");
        });
    }
    document.getElementById("btn-download").addEventListener("click", doDownload);
    $("#dl-close").addEventListener("click", function () { $("#dl-modal").classList.add("hidden"); });

    // ---------- init ----------
    ensureFonts().then(render);
    render();
})();
