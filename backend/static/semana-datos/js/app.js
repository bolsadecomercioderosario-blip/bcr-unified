// La Semana en Datos — M1 (preview de portada, título y descripción)
const $ = (sel) => document.querySelector(sel);

const btnGenerar = $('#btn-generar');
const errorMsg = $('#error-msg');
const previewSection = $('#preview-section');

// Helpers para regenerar la portada cuando se editan los títulos
const REGEN_DEBOUNCE_MS = 500;
let regenTimer = null;
let lastPortadaUrl = null;

async function regeneratePortada() {
    const titulos = [
        $('#titulo-portada-1').value.trim(),
        $('#titulo-portada-2').value.trim(),
    ].filter(Boolean);
    if (titulos.length === 0) return;

    const wrapper = document.querySelector('.portada-wrapper');
    wrapper.classList.add('regenerating');

    try {
        const r = await fetch('/api/semana-datos/preview-portada', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ titulos, copetes: [] }),
        });
        if (!r.ok) return;
        const blob = await r.blob();
        // Revocar el URL anterior para no acumular blobs en memoria
        if (lastPortadaUrl) URL.revokeObjectURL(lastPortadaUrl);
        lastPortadaUrl = URL.createObjectURL(blob);
        $('#portada-preview').src = lastPortadaUrl;
        $('#btn-download-portada').href = lastPortadaUrl;
    } finally {
        wrapper.classList.remove('regenerating');
    }
}

function scheduleRegenerate() {
    if (regenTimer) clearTimeout(regenTimer);
    regenTimer = setTimeout(regeneratePortada, REGEN_DEBOUNCE_MS);
}

$('#titulo-portada-1').addEventListener('input', scheduleRegenerate);
$('#titulo-portada-2').addEventListener('input', scheduleRegenerate);

function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.classList.remove('hidden');
}

function clearError() {
    errorMsg.classList.add('hidden');
    errorMsg.textContent = '';
}

btnGenerar.addEventListener('click', async () => {
    clearError();

    const urls = [
        $('#url-1').value.trim(),
        $('#url-2').value.trim(),
    ].filter(Boolean);

    if (urls.length === 0) {
        showError('Pegá al menos una URL de informe.');
        return;
    }

    btnGenerar.disabled = true;
    const originalContent = btnGenerar.innerHTML;
    btnGenerar.innerHTML = '<i data-lucide="loader" class="spin"></i> <span>Procesando…</span>';
    lucide.createIcons();

    try {
        // 1) Scrapeo — título + copete de cada informe
        const scrapeRes = await fetch('/api/semana-datos/scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls }),
        });
        if (!scrapeRes.ok) {
            const { detail } = await scrapeRes.json().catch(() => ({ detail: 'Error' }));
            throw new Error(detail || 'No se pudieron leer los informes');
        }
        const { informes } = await scrapeRes.json();

        const titulos = informes.map((i) => i.titulo);
        const copetes = informes.map((i) => i.copete);

        // 2) Pre-llenar los inputs editables de la portada con los títulos
        //    scrapeados. El usuario puede acortarlos si entran muy chicos.
        $('#titulo-portada-1').value = titulos[0] || '';
        if (titulos[1]) {
            $('#titulo-portada-2').value = titulos[1];
            $('#titulo-portada-2-wrapper').classList.remove('hidden');
        } else {
            $('#titulo-portada-2').value = '';
            $('#titulo-portada-2-wrapper').classList.add('hidden');
        }

        // 3) Portada inicial (usando los títulos pre-llenados)
        await regeneratePortada();

        // 4) Título YouTube + descripción (no se regeneran al editar la portada;
        //    el usuario puede modificarlos manualmente).
        const metaRes = await fetch('/api/semana-datos/preview-metadata', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ titulos, copetes }),
        });
        if (!metaRes.ok) {
            throw new Error('Error al generar título/descripción');
        }
        const { titulo, descripcion } = await metaRes.json();
        $('#titulo-output').value = titulo;
        $('#descripcion-output').value = descripcion;

        // Mostrar la sección de preview
        previewSection.classList.remove('hidden');
        previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        updateUploadButton();
    } catch (e) {
        console.error(e);
        showError(e.message || 'Error inesperado');
    } finally {
        btnGenerar.disabled = false;
        btnGenerar.innerHTML = originalContent;
        lucide.createIcons();
    }
});

// Botones "copiar" para título y descripción
document.querySelectorAll('.btn-copy').forEach((btn) => {
    btn.addEventListener('click', async () => {
        const targetId = btn.dataset.target;
        const target = document.getElementById(targetId);
        if (!target) return;
        try {
            await navigator.clipboard.writeText(target.value);
            btn.classList.add('copied');
            const icon = btn.querySelector('i');
            if (icon) {
                icon.setAttribute('data-lucide', 'check');
                lucide.createIcons();
            }
            setTimeout(() => {
                btn.classList.remove('copied');
                if (icon) {
                    icon.setAttribute('data-lucide', 'copy');
                    lucide.createIcons();
                }
            }, 1500);
        } catch (e) {
            console.error('Clipboard error:', e);
        }
    });
});

// Spinner animado (estilo simple)
const style = document.createElement('style');
style.textContent = `
    .spin { animation: spin 1s linear infinite; }
    @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
`;
document.head.appendChild(style);


// -------------------------------------------------------------------------
// Validación de Drive en tiempo real (al pegar/escribir la URL)
// -------------------------------------------------------------------------
const driveInput = $('#url-drive');
const driveStatus = $('#drive-status');
const btnUpload = $('#btn-upload');

let driveValid = false;
let driveCheckTimer = null;

function setDriveStatus(kind, html) {
    driveStatus.className = `drive-status ${kind}`;
    driveStatus.innerHTML = html;
    driveStatus.classList.remove('hidden');
}

function hideDriveStatus() {
    driveStatus.classList.add('hidden');
}

async function checkDrive() {
    const url = driveInput.value.trim();
    if (!url) {
        hideDriveStatus();
        driveValid = false;
        updateUploadButton();
        return;
    }
    setDriveStatus('checking', 'Verificando archivo en Drive…');
    try {
        const res = await fetch('/api/semana-datos/drive-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ drive_url: url }),
        });
        const data = await res.json();
        if (!res.ok) {
            driveValid = false;
            setDriveStatus('error', data.detail || 'No pude leer ese archivo');
        } else {
            driveValid = true;
            const sizeText = data.size_mb ? ` · ${data.size_mb} MB` : '';
            setDriveStatus('ok', `OK: <strong>${data.name}</strong>${sizeText}`);
        }
    } catch (e) {
        driveValid = false;
        setDriveStatus('error', 'Error de conexión al verificar Drive');
    } finally {
        updateUploadButton();
    }
}

driveInput.addEventListener('input', () => {
    driveValid = false;
    updateUploadButton();
    if (driveCheckTimer) clearTimeout(driveCheckTimer);
    driveCheckTimer = setTimeout(checkDrive, 600);
});


// -------------------------------------------------------------------------
// Botón "Subir a YouTube"
// -------------------------------------------------------------------------
const uploadStatus = $('#upload-status');

function updateUploadButton() {
    // Habilitado solo si: hay preview generado + drive válido
    const previewReady = !previewSection.classList.contains('hidden');
    btnUpload.disabled = !(previewReady && driveValid);
}

function setUploadStatus(kind, html) {
    uploadStatus.className = `upload-status ${kind}`;
    uploadStatus.innerHTML = html;
    uploadStatus.classList.remove('hidden');
}

btnUpload.addEventListener('click', async () => {
    if (btnUpload.disabled) return;

    const titulos_portada = [
        $('#titulo-portada-1').value.trim(),
        $('#titulo-portada-2').value.trim(),
    ].filter(Boolean);
    const titulo_youtube = $('#titulo-output').value.trim();
    const descripcion = $('#descripcion-output').value.trim();
    const drive_url = driveInput.value.trim();

    if (!titulo_youtube || !descripcion || !drive_url || titulos_portada.length === 0) {
        setUploadStatus('error', 'Faltan datos para subir el video.');
        return;
    }

    if (!confirm('Vas a subir el video al canal de YouTube de la BCR como PÚBLICO. ¿Continuar?')) {
        return;
    }

    btnUpload.disabled = true;
    const originalContent = btnUpload.innerHTML;
    btnUpload.innerHTML = '<i data-lucide="loader" class="spin"></i> <span>Subiendo…</span>';
    lucide.createIcons();

    setUploadStatus(
        'uploading',
        'Subiendo a YouTube. <strong>Esto puede tardar varios minutos</strong> dependiendo del tamaño del video. No cierres la pestaña.'
    );

    try {
        const res = await fetch('/api/semana-datos/upload-youtube', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                drive_url,
                titulos_portada,
                titulo_youtube,
                descripcion,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Error en el upload');
        }
        const playlistInfo = data.playlist_added
            ? 'Agregado a la playlist <em>La Semana en Datos</em>.'
            : '<strong>Atención:</strong> no se pudo agregar a la playlist automáticamente. Agregalo a mano en YouTube.';
        setUploadStatus(
            'success',
            `✅ Video subido correctamente. ${playlistInfo}<br><br>
             <a href="${data.url}" target="_blank" rel="noopener">Ver en YouTube →</a>`
        );
    } catch (e) {
        console.error(e);
        setUploadStatus('error', `❌ Falló el upload: ${e.message || e}`);
    } finally {
        btnUpload.innerHTML = originalContent;
        lucide.createIcons();
        updateUploadButton();
    }
});
