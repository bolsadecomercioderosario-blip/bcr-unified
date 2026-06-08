/* ==========================================================================
   BCR Capacita — lógica del formulario de captación de leads.

   Responsabilidades:
   - Validar en el cliente (al menos un contacto, formato email/whatsapp,
     al menos un interés, autorización marcada).
   - Armar el objeto de datos y enviarlo al endpoint.
   - Mostrar el mensaje de confirmación.

   El objeto que se envía tiene esta forma (lo que se persiste / integra con
   un CRM, Google Sheets, base de datos o endpoint externo):

       {
         email: "",
         whatsapp: "",
         intereses: [],
         autorizacion: true,
         fechaRegistro: "",   // ISO 8601, generada en el cliente
         origen: "redes"      // la gente llega desde publicidad en redes
       }
   ========================================================================== */

(function () {
    'use strict';

    // --- Configuración de la integración -----------------------------------
    // Endpoint que recibe el lead. Hoy apunta al backend de la app (FastAPI,
    // que persiste en la base de datos). Para integrarlo con otro destino
    // (CRM, Google Apps Script, Zapier, etc.) basta con cambiar esta constante.
    const ENDPOINT = '/api/capacita/leads';

    // De dónde llega la gente (campaña en redes). Queda registrado con el lead.
    const ORIGEN = 'redes';

    // --- Referencias al DOM ------------------------------------------------
    const form        = document.getElementById('lead-form');
    const emailEl     = document.getElementById('email');
    const whatsappEl  = document.getElementById('whatsapp');
    const autorizEl   = document.getElementById('autorizacion');
    const submitBtn   = document.getElementById('submit-btn');
    const alertErr    = document.getElementById('alert-error');
    const formCard    = document.getElementById('form-card');
    const successCard = document.getElementById('success-card');
    const anotherBtn  = document.getElementById('another-btn');

    // --- Helpers de UI -----------------------------------------------------
    function showError(msg) {
        alertErr.textContent = msg;
        alertErr.classList.add('show');
        // Llevamos el foco/scroll al error para que no pase desapercibido.
        alertErr.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function clearError() {
        alertErr.classList.remove('show');
        alertErr.textContent = '';
        emailEl.classList.remove('invalid');
        whatsappEl.classList.remove('invalid');
    }

    // --- Validadores (espejados en el backend, nunca se confía solo en JS) -
    // Email simple pero suficiente: algo@algo.algo
    const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

    // Devuelve solo los dígitos (descarta +, espacios, guiones, paréntesis).
    function soloDigitos(valor) {
        return (valor || '').replace(/\D/g, '');
    }

    // Lee las áreas de interés tildadas.
    function leerIntereses() {
        const checks = form.querySelectorAll('input[name="intereses"]:checked');
        return Array.from(checks).map((c) => c.value);
    }

    // --- Envío -------------------------------------------------------------
    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        clearError();

        const email        = emailEl.value.trim();
        const whatsapp     = whatsappEl.value.trim();
        const whatsappNums = soloDigitos(whatsapp);
        const intereses    = leerIntereses();
        const autorizacion = autorizEl.checked;

        // 1. Al menos un dato de contacto.
        if (!email && !whatsappNums) {
            emailEl.classList.add('invalid');
            whatsappEl.classList.add('invalid');
            showError('Dejanos al menos un dato de contacto: email o WhatsApp.');
            return;
        }

        // 2. Email válido (si se completó).
        if (email && !EMAIL_RE.test(email)) {
            emailEl.classList.add('invalid');
            showError('Revisá el email: el formato no parece válido.');
            return;
        }

        // 3. WhatsApp con cantidad de dígitos razonable (si se completó).
        //    Entre 8 y 15 dígitos cubre números locales y con código país.
        if (whatsapp && (whatsappNums.length < 8 || whatsappNums.length > 15)) {
            whatsappEl.classList.add('invalid');
            showError('Revisá el número de WhatsApp: debe tener entre 8 y 15 dígitos.');
            return;
        }

        // 4. Al menos un área de interés.
        if (intereses.length === 0) {
            showError('Elegí al menos un área de interés.');
            return;
        }

        // 5. Autorización obligatoria.
        if (!autorizacion) {
            showError('Necesitamos tu autorización para poder contactarte.');
            return;
        }

        // --- Objeto de datos que se envía / integra ------------------------
        const datos = {
            email: email,
            whatsapp: whatsapp,
            intereses: intereses,
            autorizacion: autorizacion,
            fechaRegistro: new Date().toISOString(),
            origen: ORIGEN
        };

        submitBtn.disabled = true;
        submitBtn.textContent = 'Enviando…';

        try {
            const res = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(datos)
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'No pudimos registrar tus datos. Probá de nuevo en un minuto.');
            }

            // Éxito: mostramos la confirmación.
            formCard.style.display = 'none';
            successCard.style.display = 'block';
            successCard.scrollIntoView({ behavior: 'smooth', block: 'start' });

        } catch (err) {
            showError(err.message || 'Error de conexión. Revisá tu internet e intentá otra vez.');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Quiero recibir información';
        }
    });

    // --- "Cargar otro contacto" -------------------------------------------
    anotherBtn.addEventListener('click', function () {
        form.reset();                 // limpia inputs; el consent vuelve a checked por el HTML
        clearError();
        submitBtn.disabled = false;
        submitBtn.textContent = 'Quiero recibir información';
        successCard.style.display = 'none';
        formCard.style.display = 'block';
        emailEl.focus();
    });

})();
