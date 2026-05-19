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

export async function generateIGCopy(title, description, observations) {
    try {
        const response = await fetch('/api/agenda/generate-copy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: 'ig',
                title: title || '',
                description: description || '',
                observations: observations || ''
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Error al generar copy IG');
        }
        
        const data = await response.json();
        return data.copy;
    } catch (error) {
        console.error(error);
        alert("Error de IA: " + error.message);
        return "";
    }
}

/**
 * Genera el contenido (título + cuerpo) de un bloque de Conectados,
 * reformulando un texto base en tono periodístico.
 *
 * Prioridad de la fuente:
 *   1. copy_linkedin si está cargado
 *   2. copy_instagram si está cargado
 *   3. campos básicos (título + descripción + lugar)
 *
 * Devuelve { title, copy }. Si la llamada falla, devuelve null y el caller
 * decide qué hacer (no pisa el contenido actual).
 */
export async function generateNewsletterBlock(activity) {
    let base_text = '';
    let base_source = 'basic';

    if (activity.copy_linkedin && activity.copy_linkedin.trim()) {
        base_text = activity.copy_linkedin.trim();
        base_source = 'linkedin';
    } else if (activity.copy_instagram && activity.copy_instagram.trim()) {
        base_text = activity.copy_instagram.trim();
        base_source = 'instagram';
    } else {
        const parts = [];
        if (activity.title) parts.push(`Título: ${activity.title}`);
        if (activity.description) parts.push(`Descripción: ${activity.description}`);
        if (activity.location) parts.push(`Lugar: ${activity.location}`);
        base_text = parts.join('. ');
        base_source = 'basic';
    }

    try {
        const response = await fetch('/api/agenda/generate-copy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: 'newsletter_block',
                title: activity.title || '',
                base_text,
                base_source,
            })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Error al generar bloque');
        }
        const data = await response.json();
        return { title: data.title || '', copy: data.copy || '', source: base_source };
    } catch (error) {
        console.error('generateNewsletterBlock:', error);
        alert("Error de IA: " + error.message);
        return null;
    }
}

export async function generateLICopy(title, description, observations, participantsText) {
    // 1. Enriquecer los nombres de los participantes usando BCR_AUTHORITIES
    let enrichedParticipants = "";
    if (participantsText) {
        let workingString = cleanText(participantsText);
        const matched = [];
        
        // Remove common words
        const noise = [/Participan\s+/i, /Participa\s+/i, /Estuvieron\s+/i, /Estuvo\s+/i, /Por BCR\s+/i];
        noise.forEach(r => workingString = workingString.replace(r, ''));

        // Extract and match
        BCR_AUTHORITIES.forEach(auth => {
            const parts = auth.name.split(' ');
            const lastName = parts[parts.length - 1]; // last word is usually the last name
            const regex = new RegExp(`\\b${lastName}\\b`, 'i');
            
            if (workingString.toLowerCase().includes(auth.name.toLowerCase()) || regex.test(workingString)) {
                if (!matched.some(m => m.name === auth.name)) {
                    matched.push(auth);
                }
                // remove matched part from working string to find "others" later
                workingString = workingString.replace(new RegExp(auth.name, 'gi'), '');
                workingString = workingString.replace(regex, '');
            }
        });

        const others = workingString
            .split(/[,\by\b\/]/gi)
            .map(s => s.trim())
            .filter(s => s.length > 2);

        matched.sort((a, b) => a.priority - b.priority);

        // Build enriched string using the required structure
        const enrichedList = [];
        
        const cargosConNombre = matched.filter(m => m.priority <= 4 || m.priority >= 14);
        const otrosDirectivos = matched.filter(m => m.priority > 4 && m.priority < 14);

        cargosConNombre.forEach(m => {
            const articulo = m.cargo.includes('Gerenta') || m.cargo.includes('Prosecretaria') || m.cargo.includes('Directora') ? 'la' : 'el';
            enrichedList.push(`${articulo} ${m.cargo} ${m.name}`);
        });

        if (otrosDirectivos.length > 1) {
            const names = otrosDirectivos.map(m => m.name);
            const last = names.pop();
            enrichedList.push(`los directivos BCR ${names.join(', ')} y ${last}`);
        } else if (otrosDirectivos.length === 1) {
            enrichedList.push(`el directivo BCR ${otrosDirectivos[0].name}`);
        }

        others.forEach(o => {
            enrichedList.push(o);
        });
        
        // Join properly: "A, B y C"
        if (enrichedList.length > 1) {
            const last = enrichedList.pop();
            enrichedParticipants = enrichedList.join(', ') + ' y ' + last;
        } else if (enrichedList.length === 1) {
            enrichedParticipants = enrichedList[0];
        }
    }

    // 2. Llamar a la API
    try {
        const response = await fetch('/api/agenda/generate-copy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: 'li',
                title: title || '',
                description: description || '',
                observations: observations || '',
                participants_enriched: enrichedParticipants
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Error al generar copy LI');
        }
        
        const data = await response.json();
        return data.copy;
    } catch (error) {
        console.error(error);
        alert("Error de IA: " + error.message);
        return "";
    }
}
