const API_BASE = "/api/lluvias"; // En Render/FastAPI unificado usamos rutas relativas

let pollInterval = null;

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
        const response = await fetch(`${API_BASE}/api/generar_pieza`);
        if (!response.ok) throw new Error(`Error HTTP: ${response.status}`);
        
        const data = await response.json();
        
        textarea.value = data.texto;
        if(data.imagen_url) {
            imagenMapa.src = `${API_BASE}${data.imagen_url}?t=${Date.now()}`;
            descargarBtn.href = `${API_BASE}${data.imagen_url}`;
        }

        statusMsg.classList.add('hidden');
        resultado.classList.remove('hidden');
        btn.disabled = false;

        pollVideoStatus();

    } catch (error) {
        console.error('Error:', error);
        alert('Error al conectar con el servidor.');
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
            const resp = await fetch(`${API_BASE}/api/video_status`);
            const data = await resp.json();

            if (data.status === 'ready') {
                clearInterval(pollInterval);
                
                const videoUrl = `${API_BASE}${data.video_url}?t=${Date.now()}`;
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
