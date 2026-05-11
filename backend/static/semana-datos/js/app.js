// La Semana en Datos — M1 (preview de portada, título y descripción)
const $ = (sel) => document.querySelector(sel);

const btnGenerar = $('#btn-generar');
const errorMsg = $('#error-msg');
const previewSection = $('#preview-section');

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

        // 2) Portada (PNG)
        const portadaRes = await fetch('/api/semana-datos/preview-portada', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ titulos, copetes }),
        });
        if (!portadaRes.ok) {
            throw new Error('Error al generar la portada');
        }
        const blob = await portadaRes.blob();
        const blobUrl = URL.createObjectURL(blob);
        $('#portada-preview').src = blobUrl;
        $('#btn-download-portada').href = blobUrl;

        // 3) Título + descripción
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
