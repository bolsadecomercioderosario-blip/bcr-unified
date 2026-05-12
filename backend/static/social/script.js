let sessionData = {
    session_id: null,
    pdf_path: null
};

// Función centralizada para generar piezas
async function generateFinalPieces() {
    const title = document.getElementById('titleInput').value;
    const generateBtn = document.getElementById('generateBtn');
    const preProcessBtn = document.getElementById('preProcessBtn');
    const loader = document.getElementById('loader');
    const results = document.getElementById('results');

    generateBtn.disabled = true;
    preProcessBtn.disabled = true;
    loader.style.display = 'block';

    const formData = new FormData();
    formData.append('session_id', sessionData.session_id);
    formData.append('pdf_path', sessionData.pdf_path);
    formData.append('title', title);

    try {
        const response = await fetch('/api/social/generar', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.error) {
            alert("Error al generar piezas: " + data.error);
        } else {
            document.getElementById('twitterText').value = data.twitter_text;
            
            document.getElementById('comunicadoImg').src = `${data.comunicado_img}?t=${new Date().getTime()}`;
            document.getElementById('downloadComunicadoBtn').href = data.comunicado_url;
            
            document.getElementById('storyImg').src = `${data.story_img}?t=${new Date().getTime()}`;
            document.getElementById('downloadStoryBtn').href = data.story_url;

            results.style.display = window.innerWidth <= 768 ? 'block' : 'grid';
            window.scrollTo({ top: results.offsetTop - 20, behavior: 'smooth' });
        }
    } catch (error) {
        alert("Ocurrió un error al generar: " + error.message);
    } finally {
        generateBtn.disabled = false;
        preProcessBtn.disabled = false;
        loader.style.display = 'none';
    }
}

// Handler para Analizar PDF (Paso inicial automático)
document.getElementById('preProcessBtn').addEventListener('click', async () => {
    const fileInput = document.getElementById('pdfInput');
    if (!fileInput.files.length) {
        alert("Por favor, selecciona un documento PDF.");
        return;
    }

    const btn = document.getElementById('preProcessBtn');
    const loader = document.getElementById('loader');
    const step2 = document.getElementById('step2');
    const results = document.getElementById('results');

    btn.disabled = true;
    loader.style.display = 'block';
    results.style.display = 'none';
    step2.style.display = 'none';

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const response = await fetch('/api/social/pre-procesar', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.error) {
            alert("Error al analizar: " + data.error);
            btn.disabled = false;
            loader.style.display = 'none';
        } else {
            sessionData.session_id = data.session_id;
            sessionData.pdf_path = data.pdf_path;
            
            document.getElementById('titleInput').value = data.title;
            document.getElementById('pdfPreviewImg').src = `${data.preview_url}?t=${new Date().getTime()}`;
            step2.style.display = 'block';

            // AQUÍ ESTÁ EL CAMBIO: Disparar generación automática inmediatamente
            await generateFinalPieces();
        }
    } catch (error) {
        alert("Error de conexión: " + error.message);
        btn.disabled = false;
        loader.style.display = 'none';
    }
});

// Handler para Regenerar manualmente (por si hay error en el título)
document.getElementById('generateBtn').addEventListener('click', async () => {
    await generateFinalPieces();
});

// Handler para Copiar texto de X
document.getElementById('copyXBtn').addEventListener('click', () => {
    const text = document.getElementById('twitterText');
    text.select();
    navigator.clipboard.writeText(text.value);
    const originalText = document.getElementById('copyXBtn').innerText;
    document.getElementById('copyXBtn').innerText = "✅ ¡Copiado!";
    setTimeout(() => {
        document.getElementById('copyXBtn').innerText = originalText;
    }, 2000);
});


// Handler para Publicar en X
document.getElementById('publishXBtn').addEventListener('click', async () => {
    const btn = document.getElementById('publishXBtn');
    const statusBox = document.getElementById('publishStatus');
    const texto = document.getElementById('twitterText').value.trim();
    const imgEl = document.getElementById('comunicadoImg');
    const imagen_url = (imgEl && imgEl.src) ? new URL(imgEl.src).pathname : null;

    if (!texto) {
        showSocialStatus('error', 'No hay texto para publicar.');
        return;
    }

    const confirmed = confirm(
        'Vas a publicar este tweet en la cuenta @BolsaRosario AHORA.\n\n' +
        'El tweet va con la imagen del comunicado adjunta.\n\n' +
        '¿Continuar?'
    );
    if (!confirmed) return;

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Publicando…';
    showSocialStatus('uploading', 'Subiendo imagen y publicando en X… No cierres la pestaña.');

    try {
        const res = await fetch('/api/social/publicar-twitter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto, imagen_url })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || `HTTP ${res.status}`);
        }
        showSocialStatus('success',
            `✅ Tweet publicado. <a href="${data.url}" target="_blank" rel="noopener" style="color: #1da1f2; font-weight: 600;">Verlo en X →</a>`
        );
    } catch (e) {
        console.error(e);
        showSocialStatus('error', `❌ ${e.message || 'Error inesperado'}`);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
});

function showSocialStatus(kind, html) {
    const box = document.getElementById('publishStatus');
    const styles = {
        uploading: 'background: #fff4e6; border: 1px solid #ffd99c; color: #7a4500;',
        success:   'background: #e7f7ec; border: 1px solid #a5dfb6; color: #186829;',
        error:     'background: #fdecea; border: 1px solid #f5b0a8; color: #8a1a10;',
    };
    box.style.cssText = `margin-top: 12px; padding: 10px 12px; border-radius: 8px; font-size: 0.85rem; display: block; ${styles[kind] || ''}`;
    box.innerHTML = html;
}

// Ajuste dinámico de grid al redimensionar (opcional para robustez)
window.addEventListener('resize', () => {
    const results = document.getElementById('results');
    if (results.style.display !== 'none') {
        results.style.display = window.innerWidth <= 768 ? 'block' : 'grid';
    }
});