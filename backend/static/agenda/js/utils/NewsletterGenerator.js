/**
 * Genera los bloques HTML del newsletter Conectados con la estructura que
 * Dynamics 365 Marketing reconoce como bloques editables (nested tables
 * con data-section, data-container, data-editorblocktype, data-container-width).
 *
 * El usuario pega estos bloques en su template del CRM, entre el header
 * ("Te contamos lo que pasó…") y el footer (copyright / unsubscribe).
 *
 * Cada fila tiene 2 columnas (50/50). Si la cantidad de actividades es impar,
 * la última fila tiene una columna llena y otra vacía (igual que el template
 * de Dynamics).
 */

// --- Helpers ----------------------------------------------------------------

function escapeHtml(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Genera un ID único para `<th data-container>`, replicando el patrón de
 * Dynamics: "container" + 12 hex chars + timestamp (~13 dígitos).
 * Ej: containerc13ed8f70a73681762179701950
 */
function uniqueContainerId() {
    const hex = Math.random().toString(16).slice(2, 14).padEnd(12, '0');
    return 'container' + hex + Date.now();
}

/**
 * Convierte texto plano (con saltos de línea simples y dobles) en una serie
 * de <p> con la estructura/estilos que Dynamics produce. Los saltos simples
 * dentro de un párrafo se preservan como <br>; los saltos dobles separan
 * párrafos.
 */
function textToParagraphs(text) {
    if (!text) return '';
    const blocks = String(text).replace(/\r\n/g, '\n').split(/\n\s*\n/);
    return blocks
        .map(p => p.trim())
        .filter(p => p.length > 0)
        .map(p => {
            const escaped = escapeHtml(p).replace(/\n/g, '<br>');
            return `<p dir="ltr" style="margin: 0 0 12px 0; padding: 0; line-height: 1.4; font-family: Arial, Verdana, sans-serif; font-size: 14px; color: rgb(0, 0, 0); font-weight: normal; text-align: justify;">${escaped}</p>`;
        })
        .join('');
}

/**
 * Bloque divider (líneita gris al final de cada columna), idéntico al que
 * inserta Dynamics cuando agregás el componente "Divider".
 */
function dividerHtml() {
    return `<div data-editorblocktype="Divider" style="margin: 20px 10px;"><div class="dividerWrapper" align="center"><table style="padding: 0px; margin: 0px; width: 100%; border-collapse: collapse;" role="presentation" class="" cellpadding="0" cellspacing="0"><tbody><tr style="padding: 0px;"><th style="margin:0px; padding: 0px; vertical-align:top;border-top-width: 2px; border-top-style: solid; border-top-color: #e1dfdd;"><p style="margin: 0px; padding: 0px; line-height: 0px; width: 100%;"><span><!--[if gte mso 9]><br/><![endif]-->&nbsp;</span></p></th></tr></tbody></table></div></div>`;
}

// --- Render de columna ------------------------------------------------------

/**
 * Renderiza una columna del newsletter. Si act es null/undefined devuelve
 * un <th> vacío (relleno cuando hay un número impar de bloques) — exactamente
 * el patrón que usa el template del CRM en su última fila.
 */
function renderColumn(act, baseUrl) {
    if (!act) {
        return `<th style="width: 50%; padding: 10px;" role="presentation"></th>`;
    }

    const containerId = uniqueContainerId();
    const title = act.title || '';
    const text = act.copy_linkedin || act.conectados_text || '';
    const imageUrl = act.image_url
        ? (act.image_url.startsWith('http') ? act.image_url : baseUrl + act.image_url)
        : 'https://via.placeholder.com/600x400?text=BCR+Agenda';

    const titleEsc = escapeHtml(title);
    const altEsc = escapeHtml(title);
    const imgSrcEsc = escapeHtml(imageUrl);
    const paragraphs = textToParagraphs(text);

    return `<th data-container="true" class="columnContainer" data-container-width="50.00" style="vertical-align: top; min-width: 5px; width: 290px; height: 0px;" id="${containerId}" role="presentation">
        <table width="100%" cellpadding="0" cellspacing="0" style="height: 100%;" role="presentation">
            <tbody>
                <tr>
                    <th class="columnContainer inner" style="min-width: 5px; padding: 10px; vertical-align: top; word-wrap: break-word; word-break: break-word; font-weight: normal;" role="presentation">
                        <div data-editorblocktype="Image" style="margin: 10px;">
                            <div align="Center" class="imageWrapper" style="">
                                <img src="${imgSrcEsc}" style="max-height: 100%; max-width: 100%; box-sizing: border-box; display: block;" alt="${altEsc}">
                            </div>
                        </div>
                        <div data-editorblocktype="Text" style="margin: 10px;">
                            <h3 style="color: rgb(0, 0, 0); font-family: Arial, Verdana, sans-serif; font-size: 18px; font-weight: bold; line-height: 1.25; margin: 0;">${titleEsc}</h3>
                        </div>
                        <div data-editorblocktype="Text" style="margin: 10px; text-align: justify; line-height: 1.4;">
                            ${paragraphs}
                        </div>
                        ${dividerHtml()}
                    </th>
                </tr>
            </tbody>
        </table>
    </th>`;
}

// --- Entry point ------------------------------------------------------------

export function generateNewsletterHTML(activities) {
    const baseUrl = window.location.origin;

    // Agrupar de a dos para layout 50/50
    const rows = [];
    for (let i = 0; i < activities.length; i += 2) {
        rows.push(activities.slice(i, i + 2));
    }

    return rows.map(pair => {
        const left = renderColumn(pair[0], baseUrl);
        const right = renderColumn(pair[1] || null, baseUrl);

        return `<div data-section="true" class="emptyContainer columns-equal-class wrap-section" style="margin: 0px; border-radius: 0px;">
    <table class="outer" align="center" cellpadding="0" cellspacing="0" style="width: 600px; display: block;" role="presentation">
        <tbody>
            <tr>
                <th style="padding: 10px; border-color: rgb(0, 0, 0); border-width: 0px; border-style: none; border-radius: 0px;" role="presentation">
                    <table style="width: 100%; border-collapse: collapse;" class="containerWrapper tbContainer multi" cellpadding="0" cellspacing="0" role="presentation">
                        <tbody>
                            <tr>
                                ${left}
                                ${right}
                            </tr>
                        </tbody>
                    </table>
                </th>
            </tr>
        </tbody>
    </table>
</div>`;
    }).join('\n');
}
