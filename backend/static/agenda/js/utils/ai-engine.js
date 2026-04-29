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

export async function generateLICopy(title, description, observations, participantsText) {
    // 1. Enriquecer los nombres de los participantes usando BCR_AUTHORITIES
    let enrichedParticipants = "";
    if (participantsText) {
        let workingString = cleanText(participantsText);
        const matched = [];
        
        // Remove common words
        const noise = [/Participan\s+/i, /Participa\s+/i, /Estuvieron\s+/i, /Estuvo\s+/i, /Por BCR\s+/i];
        noise.forEach(r => workingString = workingString.replace(r, ''));

        // Match against database
        BCR_AUTHORITIES.forEach(auth => {
            // Simplified matching (case insensitive)
            if (workingString.toLowerCase().includes(auth.name.toLowerCase())) {
                matched.push(auth);
                // Remove matched name from the working string
                const regex = new RegExp(auth.name, 'gi');
                workingString = workingString.replace(regex, '');
            }
        });

        // Get unmatched people
        const others = workingString
            .split(/[,\by\b\/]/gi)
            .map(s => s.trim())
            .filter(s => s.length > 2);

        matched.sort((a, b) => a.priority - b.priority);

        // Build enriched string
        const enrichedList = [];
        matched.forEach(m => {
            enrichedList.push(`${m.name} (${m.cargo})`);
        });
        others.forEach(o => {
            enrichedList.push(o); // Unmatched names passed as is
        });
        
        enrichedParticipants = enrichedList.join(', ');
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
