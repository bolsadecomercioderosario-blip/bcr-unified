const API_BASE = "/api/lluvias"; // En Render/FastAPI unificado usamos rutas relativas

let pollInterval = null;

// State del cliente: localidades crudas que vinieron del scrape + el header
// del tweet. Sirven para recalcular el texto al cambiar el contador sin
// pegarle de nuevo al server (que tendría que re-scrapear y demoraría 1-2s).
const lluviasState = {
    localidades: [],      // array de {localidad, mm} ordenado desc
    tweetHeader: '',      // primera línea del texto del tweet (sin el "- foo: 1 mm")
    tweetFooter: '',      // últimas líneas del texto del tweet (link al mapa)
    count: 5,             // cuántas localidades mostrar en el texto
    noLluvias: false,
};

// Reconstruye el texto del tweet con `count` localidades + header + footer.
function buildTweetText(count) {
    if (lluviasState.noLluvias || lluviasState.localidades.length === 0) {
        return "No se registraron precipitaciones en la red de estaciones de la BCR durante el período relevado.";
    }
    const top = lluviasState.localidades.slice(0, count);
    const lines = top.map(d => `- ${d.localidad}: ${d.mm} mm`).join('\n');
    return `${lluviasState.tweetHeader}\n\n${lines}\n${lluviasState.tweetFooter}`;
}

// Parsea el texto que vino del backend para extraer header y footer una sola
// vez, y reusar el formato exacto al recalcular client-side.
function parseTweetSections(texto) {
    if (!texto || lluviasState.noLluvias) return;
    const lines = texto.split('\n');
    const firstDashIdx = lines.findIndex(l => l.startsWith('- '));
    const lastDashIdx = (() => {
        for (let i = lines.length - 1; i >= 0; i--) if (lines[i].startsWith('- ')) return i;
        return -1;
    })();
    if (firstDashIdx === -1) return;
    lluviasState.tweetHeader = lines.slice(0, firstDashIdx).join('\n').replace(/\n+$/, '');
    lluviasState.tweetFooter = lines.slice(lastDashIdx + 1).join('\n').replace(/^\n+/, '');
}

function updateCountControls() {
    const row = document.getElementById('textCountRow');
    const value = document.getElementById('textCountValue');
    const max = document.getElementById('textCountMax');
    const minus = document.getElementById('textCountMinus');
    const plus = document.getElementById('textCountPlus');
    const n = lluviasState.localidades.length;

    if (lluviasState.noLluvias || n === 0) {
        row.classList.add('hidden');
        return;
    }
    row.classList.remove('hidden');
    value.textContent = lluviasState.count;
    max.textContent = `(máximo ${n} con lluvia registrada)`;
    minus.disabled = lluviasState.count <= 1;
    plus.disabled = lluviasState.count >= n;
}

// Handlers del +/-
document.getElementById('textCountMinus').addEventListener('click', () => {
    if (lluviasState.count <= 1) return;
    lluviasState.count -= 1;
    document.getElementById('textoResultado').value = buildTweetText(lluviasState.count);
    updateCountControls();
});
document.getElementById('textCountPlus').addEventListener('click', () => {
    if (lluviasState.count >= lluviasState.localidades.length) return;
    lluviasState.count += 1;
    document.getElementById('textoResultado').value = buildTweetText(lluviasState.count);
    updateCountControls();
});

document.getElementById('generarBtn').addEventListener('click', async () => {
    const btn = document.getElementById('generarBtn');
    const statusMsg = document.getElementById('statusMsg');
    const resultado = document.getElementById('resultado');
    const textarea = document.getElementById('textoResultado');
    const imagenMapa = document.getElementById('imagenMapa');
    const descargarBtn = document.getElementById('descargarBtn');
    const videoCard = document.getElementById('videoCard');
    const videoLoader = document.getElementById('videoLoader');
    const videoContent = document.getElementById('videoContent');
    const historiaVideo = document.getElementById('historiaVideo');

    // Reset UI
    btn.disabled = true;
    statusMsg.classList.remove('hidden');
    resultado.classList.add('hidden');
    videoCard.classList.remove('hidden');
    videoLoader.classList.remove('hidden');
    videoContent.classList.add('hidden');
    
    if (pollInterval) clearInterval(pollInterval);

    try {
        const response = await fetch(`${API_BASE}/generar_pieza`);
        if (!response.ok) throw new Error(`Error HTTP: ${response.status}`);

        const data = await response.json();

        // Guardamos el array crudo + header/footer del tweet en el state
        // del cliente para poder recalcular el texto cuando cambia el contador.
        lluviasState.localidades = Array.isArray(data.localidades) ? data.localidades : [];
        lluviasState.noLluvias = !!data.no_lluvias;
        lluviasState.count = Math.min(5, lluviasState.localidades.length || 5);
        parseTweetSections(data.texto);
        textarea.value = data.texto;
        updateCountControls();

        if(data.imagen_url) {
            imagenMapa.src = `${data.imagen_url}?t=${Date.now()}`;
            descargarBtn.href = `${data.imagen_url}`;
        }

        statusMsg.classList.add('hidden');
        resultado.classList.remove('hidden');
        btn.disabled = false;

        if (data.no_lluvias) {
            videoCard.classList.add('hidden');
            console.log("No se registraron lluvias, video desactivado.");
        } else {
            pollVideoStatus();
        }

    } catch (error) {
        console.error('Error:', error);
        alert('Error al conectar: ' + error.message);
        btn.disabled = false;
        statusMsg.classList.add('hidden');
    }
});

async function pollVideoStatus() {
    const videoLoader = document.getElementById('videoLoader');
    const videoContent = document.getElementById('videoContent');
    const historiaVideo = document.getElementById('historiaVideo');
    const descargarVideoBtn = document.getElementById('descargarVideoBtn');
    const videoStatusText = document.getElementById('videoStatusText');

    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/video_status`);
            const data = await resp.json();

            if (data.status === 'ready') {
                clearInterval(pollInterval);
                
                const videoUrl = `${data.video_url}?t=${Date.now()}`;
                historiaVideo.src = videoUrl;
                historiaVideo.load();
                descargarVideoBtn.href = videoUrl;

                videoLoader.classList.add('hidden');
                videoContent.classList.remove('hidden');
                console.log("Video listo!");
            } else if (data.status === 'error') {
                clearInterval(pollInterval);
                videoStatusText.innerHTML = `❌ Error al generar video: ${data.message}`;
            } else {
                console.log("Video procesándose...");
            }
        } catch (e) {
            console.error("Error polling:", e);
        }
    }, 3000);
}

document.getElementById('copiarBtn').addEventListener('click', () => {
    const textarea = document.getElementById('textoResultado');
    textarea.select();
    navigator.clipboard.writeText(textarea.value);

    const copyBtn = document.getElementById('copiarBtn');
    const originalText = copyBtn.textContent;
    copyBtn.textContent = '✅ ¡Copiado!';
    setTimeout(() => { copyBtn.textContent = originalText; }, 2000);
});


// Publicar en X (Twitter)
document.getElementById('publicarBtn').addEventListener('click', async () => {
    const btn = document.getElementById('publicarBtn');
    const statusBox = document.getElementById('publishStatus');
    const texto = document.getElementById('textoResultado').value.trim();
    const imgEl = document.getElementById('imagenMapa');
    const imagen_url = (imgEl && imgEl.src) ? new URL(imgEl.src).pathname : null;

    if (!texto) {
        showStatus('error', 'No hay texto para publicar.');
        return;
    }

    const confirmed = confirm(
        'Vas a publicar este tweet en la cuenta @BolsaRosario AHORA.\n\n' +
        'El tweet va con la imagen del mapa adjunta.\n\n' +
        '¿Continuar?'
    );
    if (!confirmed) return;

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Publicando…';
    showStatus('uploading', 'Subiendo imagen y publicando en X… No cierres la pestaña.');

    try {
        const res = await fetch(`${API_BASE}/publicar-twitter`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto, imagen_url })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || `HTTP ${res.status}`);
        }
        showStatus('success',
            `✅ Tweet publicado. <a href="${data.url}" target="_blank" rel="noopener">Verlo en X →</a>`
        );
    } catch (e) {
        console.error(e);
        showStatus('error', `❌ ${e.message || 'Error inesperado'}`);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
});

function showStatus(kind, html) {
    const box = document.getElementById('publishStatus');
    box.className = `publish-status ${kind}`;
    box.innerHTML = html;
    box.classList.remove('hidden');
}
