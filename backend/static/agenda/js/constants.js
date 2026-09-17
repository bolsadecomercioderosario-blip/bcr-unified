// Responsables de eventos que maneja Secretaría (campo `sec_responsible` de la
// Agenda de Compromisos). Se usa en dos lugares: el desplegable "Responsable"
// del formulario (ActivityForm) y el filtro por responsable de la vista
// (AgendaCompromisos). Agregar un nombre acá lo hace aparecer en ambos.
export const SEC_RESPONSABLES = ['Daniel Vicente', 'Jorge Magariños', 'Andrés Williams', 'Silvia Rolando'];

// Nombres lindos de las áreas (Funcionarios). Los slugs matchean auth.py (AREAS).
// Se usan para mostrar de quién es cada actividad en la "Agenda completa".
export const AREA_NOMBRE = {
    diyee: 'DIyEE',
    innova: 'Innova',
    cac: 'CAC',
    bcrdigital: 'BCR Digital',
    fundacion: 'Fundación BCR',
    legales: 'Legales',
    bcrlabs: 'BCRlabs',
};

// Etiqueta del "dueño" de una actividad para las tarjetas de la agenda completa.
export function ownerLabel(act) {
    if (act.origen === 'secretaria') return 'Mesa Ejecutiva';
    if (act.origen === 'area') return AREA_NOMBRE[act.area] || (act.area || 'Área');
    return '';
}
