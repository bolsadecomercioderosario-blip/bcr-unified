/**
 * Generates only the HTML news blocks for the newsletter in a 2-column layout
 */
export function generateNewsletterHTML(activities) {
    const baseUrl = window.location.origin;
    
    // Agrupar actividades de a dos para las columnas
    const rows = [];
    for (let i = 0; i < activities.length; i += 2) {
        rows.push(activities.slice(i, i + 2));
    }

    const rowsHTML = rows.map((pair, rowIndex) => {
        const left = pair[0];
        const right = pair[1]; // Puede ser undefined si es impar

        const renderCell = (act) => {
            if (!act) return '<th style="width: 50%; padding: 10px;"></th>';
            
            const title = act.title || '';
            const text = act.copy_linkedin || act.conectados_text || '';
            const imageUrl = act.image_url ? 
                (act.image_url.startsWith('http') ? act.image_url : baseUrl + act.image_url) : 
                'https://via.placeholder.com/600x400?text=BCR+Agenda';

            return `
                <th data-container="true" class="columnContainer" style="vertical-align: top; width: 50%; padding: 10px; font-weight: normal; text-align: left;" role="presentation">
                    <div data-editorblocktype="Image" style="margin-bottom: 15px;">
                        <div align="center" class="imageWrapper">
                            <img src="${imageUrl}" style="width: 100%; max-width: 280px; height: auto; display: block; border-radius: 4px;" alt="${title}">
                        </div>
                    </div>
                    <div data-editorblocktype="Text">
                        <h3 style="color: #000000; font-family: Arial, sans-serif; font-size: 18px; font-weight: bold; line-height: 1.2; margin: 0 0 10px 0; padding: 0;">${title}</h3>
                        <p style="color: #242424; font-family: Arial, sans-serif; font-size: 15px; line-height: 1.4; margin: 0; text-align: left; white-space: pre-wrap;">${text}</p>
                    </div>
                </th>
            `;
        };

        return `
        <!-- Fila de Noticias ${rowIndex + 1} -->
        <div data-section="true" class="columns-equal-class wrap-section" style="margin: 0px; border-radius: 0px;">
            <table class="outer" align="center" cellpadding="0" cellspacing="0" style="width: 600px; margin: 0 auto; border-collapse: collapse;" role="presentation">
                <tbody>
                    <tr>
                        <th style="padding: 10px 0; border-bottom: 1px solid #e1dfdd;" role="presentation">
                            <table style="width: 100%; border-collapse: collapse;" cellpadding="0" cellspacing="0" role="presentation">
                                <tbody>
                                    <tr>
                                        ${renderCell(left)}
                                        ${renderCell(right)}
                                    </tr>
                                </tbody>
                            </table>
                        </th>
                    </tr>
                </tbody>
            </table>
        </div>
        `;
    }).join('');

    return rowsHTML;
}
