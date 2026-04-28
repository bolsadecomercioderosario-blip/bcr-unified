/**
 * AI Content Engine v1.8
 * Focus: Journalistic synthesis, institutional tone, and zero emojis.
 */

import { BCR_AUTHORITIES } from './authorities.js';

/**
 * Removes emojis and special unicode symbols (like sparkles, stars, etc.)
 */
export function cleanText(text) {
    if (!text) return '';
    // This regex targets emojis and many common UI symbols
    return text.replace(/([\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF])/g, '')
               .replace(/[✳️💡✅🚀🔥✨]/g, '') // Explicitly targeted symbols
               .replace(/\s+/g, ' ')
               .trim();
}

/**
 * Synthesizes a list of items or long description into a narrative sentence.
 */
function synthesizeDescription(desc) {
    const cleaned = cleanText(desc);
    if (!cleaned) return '';

    // If it looks like a list (newlines or bullet points)
    if (cleaned.includes('\n') || cleaned.includes('|') || cleaned.match(/[-*•]/)) {
        const items = cleaned.split(/[\n|,\-\*•]/)
                             .map(i => i.trim())
                             .filter(i => i.length > 5);
        
        if (items.length > 0) {
            const listText = items.length > 2 
                ? `${items.slice(0, 2).join(', ')} y otras temáticas clave`
                : items.join(' y ');
            return `Durante el encuentro se abordaron cuestiones vinculadas a ${listText.toLowerCase()}, en una jornada de intercambio técnico y profesional.`;
        }
    }
    
    // Default: Truncate and add connector
    return cleaned.length > 150 ? cleaned.substring(0, 150) + '...' : cleaned;
}

export function generateIGCopy(title, description) {
    const cleanTitle = cleanText(title);
    const cleanDesc = synthesizeDescription(description);

    let header = cleanTitle.toUpperCase();
    let action = "participó de";
    let mainTopic = cleanTitle;

    if (cleanTitle.includes(':')) {
        const parts = cleanTitle.split(':');
        header = `${parts[0].trim().toUpperCase()}: ${parts[1].trim().toLowerCase()}`;
        mainTopic = parts[0].trim();
        action = parts[1].trim().toLowerCase();
    }

    const p1 = `La Bolsa de Comercio de Rosario ${action} ${mainTopic}, un encuentro institucional orientado a fortalecer la vinculación y el desarrollo del sector productivo regional.`;
    const p2 = cleanDesc 
        ? `${cleanDesc} La actividad permitió profundizar en la agenda de trabajo de la institución y coordinar esfuerzos conjuntos.`
        : `La jornada promovió un espacio de diálogo y reflexión sobre las oportunidades que se presentan para las organizaciones en el contexto actual.`;

    return `${header}\n\n${p1}\n\n${p2}`;
}

export function generateLICopy(title, igCopy, participantsText, responsible) {
    const cleanTitle = cleanText(title);
    const liTitle = `𝗣𝗿𝗲𝘀𝗲𝗻𝗰𝗶𝗮 𝗱𝗲 𝗹𝗮 𝗕𝗖𝗥 𝗲𝗻 ${cleanTitle}`;
    
    const paragraphs = igCopy.split('\n\n');
    const newsContent = paragraphs.length > 1 ? paragraphs.slice(1).join('\n\n') : igCopy;
    
    let liText = `${liTitle}\n\n${newsContent}`;

    if (participantsText) {
        let workingString = cleanText(participantsText);
        const matched = [];
        const noise = [/Participan\s+/i, /Participa\s+/i, /Estuvieron\s+/i, /Estuvo\s+/i, /Por BCR\s+/i];
        noise.forEach(r => workingString = workingString.replace(r, ''));

        BCR_AUTHORITIES.forEach(auth => {
            if (workingString.toLowerCase().includes(auth.name.toLowerCase())) {
                matched.push(auth);
                const regex = new RegExp(auth.name, 'gi');
                workingString = workingString.replace(regex, '');
            }
        });

        const others = workingString
            .split(/[,\by\b]/gi)
            .map(s => s.trim())
            .filter(s => s.length > 2);

        matched.sort((a, b) => a.priority - b.priority);

        if (matched.length > 0 || others.length > 0) {
            liText += `\n\nPor parte de la BCR estuvieron presentes: `;
            const staffStrings = matched.map(m => `${m.cargo} ${m.name}`);
            liText += staffStrings.join('; ');
            
            if (others.length > 0) {
                liText += `${matched.length > 0 ? '; junto a ' : ''}${others.join(', ')}.`;
            } else if (matched.length > 0) {
                liText += `.`;
            }
        }
    }

    const area = (responsible && responsible !== '') ? `área de ${responsible}` : 'la institución';
    liText += `\n\nLa actividad fue impulsada por ${area}.`;
    
    return liText;
}
