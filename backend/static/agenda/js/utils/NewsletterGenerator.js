/**
 * Generates the full HTML for the newsletter based on the user's template
 */
export function generateNewsletterHTML(activities) {
    const baseImageUrl = window.location.origin;

    const itemsHTML = activities.map((act, index) => {
        const title = act.title || '';
        const text = act.copy_linkedin || act.conectados_text || '';
        const imageUrl = act.image_url ? (act.image_url.startsWith('http') ? act.image_url : baseImageUrl + act.image_url) : 'https://via.placeholder.com/600x300?text=BCR+Agenda';

        return `
        <!-- Bloque de Noticia ${index + 1} -->
        <div data-section="true" class="columns-equal-class wrap-section" style="margin: 0px; border-radius: 0px;">
            <table class="outer" align="center" cellpadding="0" cellspacing="0" style="width: 600px; display: block;" role="presentation">
                <tbody>
                    <tr>
                        <th style="padding: 10px; border-color: rgb(0, 0, 0); border-width: 0px; border-style: none; border-radius: 0px;" role="presentation">
                            <table style="width: 100%; border-collapse: collapse;" class="containerWrapper tbContainer" cellpadding="0" cellspacing="0" role="presentation">
                                <tbody>
                                    <tr>
                                        <th data-container="true" class="columnContainer" data-container-width="100" style="vertical-align: top; min-width: 5px; width: 580px; height: 0px;" role="presentation">
                                            <table width="100%" cellpadding="0" cellspacing="0" style="height: 100%;" role="presentation">
                                                <tbody>
                                                    <tr>
                                                        <th class="columnContainer inner" style="min-width: 5px; padding: 10px; vertical-align: top; word-wrap: break-word; word-break: break-word; font-weight: normal;" role="presentation">
                                                            <div data-editorblocktype="Image" style="margin: 10px;">
                                                                <div align="Center" class="imageWrapper">
                                                                    <img src="${imageUrl}" style="max-height: 100%; max-width: 100%; box-sizing: border-box; display: block; border-radius: 8px;">
                                                                </div>
                                                            </div>
                                                            <div data-editorblocktype="Text" style="margin: 10px;">
                                                                <h3 style="color: #242424; font-family: Arial, sans-serif; font-size: 20px; font-weight: 700; line-height: 1.25; margin-bottom: 8px;">
                                                                    ${title}
                                                                </h3>
                                                                <p style="color: #242424; font-family: Arial, sans-serif; font-size: 16px; line-height: 1.5; text-align: justify; white-space: pre-wrap;">
                                                                    ${text}
                                                                </p>
                                                            </div>
                                                            <div data-editorblocktype="Divider" style="margin: 20px 10px;">
                                                                <div class="dividerWrapper" align="center">
                                                                    <table style="padding: 0px; margin: 0px; width: 100%; border-collapse: collapse;" role="presentation" cellpadding="0" cellspacing="0">
                                                                        <tbody>
                                                                            <tr style="padding: 0px;">
                                                                                <th style="margin:0px; padding: 0px; vertical-align:top; border-top: 2px solid #e1dfdd;">&nbsp;</th>
                                                                            </tr>
                                                                        </tbody>
                                                                    </table>
                                                                </div>
                                                            </div>
                                                        </th>
                                                    </tr>
                                                </tbody>
                                            </table>
                                        </th>
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

    return `
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Newsletter BCR</title>
    <style>
        body { font-family: Arial, Verdana, sans-serif; font-size: 14px; color: #000; background-color: #fff; margin: 0; padding: 0; }
        a { color: #0082dd; text-decoration: none; }
        .outer { width: 600px; margin: 0 auto; }
        @media screen and (max-width: 600px) {
            .outer { width: 100% !important; }
        }
    </style>
</head>
<body dir="ltr">
    <div data-layout="true" style="max-width: 600px; margin: auto; background-color: #ffffff;">
        <!-- Header -->
        <div data-section="true" class="columns-equal-class wrap-section">
            <table class="outer" align="center" cellpadding="0" cellspacing="0" style="border-collapse: collapse; width: 600px; display: block;" role="presentation">
                <tbody>
                    <tr>
                        <th style="padding: 10px" role="presentation">
                            <table style="width: 100%; border-collapse: collapse;" class="containerWrapper tbContainer" cellpadding="0" cellspacing="0" role="presentation">
                                <tbody>
                                    <tr>
                                        <th data-container="true" class="columnContainer" data-container-width="100" style="min-width: 20px; width: 580px; height: 0px;" role="presentation">
                                            <table width="100%" cellpadding="0" cellspacing="0" style="height: 100%;" role="presentation">
                                                <tbody>
                                                    <tr>
                                                        <th class="inner" style="min-width: 20px; padding: 10px; vertical-align: top; word-wrap: break-word; font-weight: normal;" role="presentation">
                                                            <div data-editorblocktype="Text" style="margin: 10px;">
                                                                <p style="text-align: center;"><span style="color: rgb(51, 51, 51); font-family: Arial, sans-serif; font-size: 12px;">Si no puedes visualizar este mail haz <a href="{{ViewEmailInBrowserUrl_1}}">Click aquí</a></span></p>
                                                            </div>
                                                            <div data-editorblocktype="Image" style="margin: 10px;">
                                                                <div align="Center" class="imageWrapper">
                                                                    <img src="https://assets-sam.mkt.dynamics.com/ec3b6484-3b62-447e-90f8-d779a104643c/digitalassets/images/0824e0fc-f6d5-f011-8543-6045bd394a72?ts=639009885285643388" style="max-height: 100%; max-width: 100%; display: block;">
                                                                </div>
                                                            </div>
                                                            <div data-editorblocktype="Text" style="margin: 10px;">
                                                                <p style="text-align: center;"><span style="font-weight: bold; font-size: 18px; font-family: Arial, sans-serif; color: #242424;">Te contamos lo que pasó en la Bolsa de Comercio de Rosario</span></p>
                                                            </div>
                                                        </th>
                                                    </tr>
                                                </tbody>
                                            </table>
                                        </th>
                                    </tr>
                                </tbody>
                            </table>
                        </th>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Noticias -->
        ${itemsHTML}

        <!-- Footer -->
        <div data-section="true" class="columns-equal-class wrap-section">
            <table class="outer" align="center" cellpadding="0" cellspacing="0" style="border-collapse: collapse; width: 600px; display: block;" role="presentation">
                <tbody>
                    <tr>
                        <th style="padding: 20px; text-align: center; color: #666; font-size: 12px; font-family: Arial, sans-serif;" role="presentation">
                            Bolsa de Comercio de Rosario © 2024
                        </th>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
    `;
}
