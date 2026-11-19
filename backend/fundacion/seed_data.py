# -*- coding: utf-8 -*-
"""Seed de la Agenda de la Fundación BCR: importación única de la planilla
histórica (Google Sheet). Se carga sólo si la tabla está vacía (ver migrate).
De acá en más las nuevas actividades entran por la web o por WhatsApp.
"""

ACTIVIDADES = [
  {
    "fecha": "2026-03-02",
    "hora": "13:30 a 14:00 hs",
    "evento": "Reunión equipo FBCR Tema: Coordinación de tareas",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-03-03",
    "hora": "13:00 a 14:00 hs",
    "evento": "Reunión con el Area de Seguridad e Higiene BCR Tema: Reporte y Memoria",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-03-04",
    "hora": "09:30 hs",
    "evento": "Desayuno de trabajo y Recorrida Institucional del Banco de Alimentos Rosario, BAR",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-03-04",
    "hora": "16:30 hs",
    "evento": "Reunión con A3 y Fixit Tema: Estrategias de Sostenibilidad",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-05",
    "hora": "09:30 a 11:00 hs",
    "evento": "Reunión con Intendentes, Presidentes Comunales y otros Colaboradores BCR",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-03-05",
    "hora": "11:30 a 13:30 hs",
    "evento": "Formación Internacional de Ashoka",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-06",
    "hora": "11:30 hs",
    "evento": "Reunión con Simioni Tema: UNICEF",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-07",
    "hora": "09:45 hs",
    "evento": "Entrevista Radio La Red, con la Periodista Lucila Roman Tema: Toque de Campana por la Igualdad de Genero",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-09",
    "hora": "10:00 a 12:00 hs",
    "evento": "Toque de Campana por la Igualdad de Género 2026",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-03-11",
    "hora": "09:30 a 10:00 hs",
    "evento": "Armar redes para Fundación",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-11",
    "hora": "10:00 a 13:00 hs",
    "evento": "Expoagro 2026- Lugar: San Nicolas",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-03-12",
    "hora": "09:15 a 10:45 hs",
    "evento": "Reunion por Sostenibilidad BCR",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-03-12",
    "hora": "10:00 a 11:00 hs",
    "evento": "Agromaker (financiamineto)",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-03-12",
    "hora": "15:00 a 15:30 hs",
    "evento": "Actialización Tecnoteca",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-16",
    "hora": "10:30 a 11:00 hs",
    "evento": "Reunion con Provincia",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-17",
    "hora": "08:30 a 09:30 hs",
    "evento": "Presentacion de Agromakers a escuelas de Rosario (presencial)",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-17",
    "hora": "11:00 a 11:30 hs",
    "evento": "Fabian Fiori",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-18",
    "hora": "11:00 a 12:30 hs",
    "evento": "Evento de Lanzamiento: Impulsar la Igualdad de Genero a traves del Dialogo Social",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-18",
    "hora": "12:00 a 13:00 hs",
    "evento": "BCR en Territorio",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-18",
    "hora": "15:00 a 16 hs",
    "evento": "Pitcheo BASF – Conectar para Transformar",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-03-19",
    "hora": "09:30 a 10:00 hs",
    "evento": "Reporte de Sostenibilidad",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-07",
    "hora": "",
    "evento": "Reunión de trabajo Agromakers",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-04-08",
    "hora": "09:00 a 10:30 hs",
    "evento": "Reunión Presencial en Tecnoteca",
    "equipo": "Nico/Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-04-08",
    "hora": "10:00 a 11:30 hs",
    "evento": "Taller de Alfabetización Digital para Socios Vitaclicios",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-08",
    "hora": "11:00 a 11:30 hs",
    "evento": "Reunion con Maria Eugenia de Municipio de Alcorta",
    "equipo": "Ana/Juanma/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-04-09",
    "hora": "10:15 a 10:45 hs",
    "evento": "Reunion de Sostenibilidad",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-15",
    "hora": "09:00 hs",
    "evento": "a 10:00 hs – Reunión de Consejo de Fundacion",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-15",
    "hora": "10:00 a 11:30 hs",
    "evento": "Taller de Alfabetizacion digital Asociados Vitalicios",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-04-16",
    "hora": "09:00 a 12:00 hs",
    "evento": "Capacitacion Mesa y OXY 46",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-04-16",
    "hora": "09:30 a 10:00 hs",
    "evento": "Reunion de Sostenibilidad",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-21",
    "hora": "09:00 a 10:30 hs",
    "evento": "Preparacion 1era Clase Formación Docente",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-04-21",
    "hora": "10:30 a 11:30 hs",
    "evento": "Charla Makers",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-04-21",
    "hora": "11:30 a 12:30 hs",
    "evento": "Repaso charla Sostentabilidad",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-22",
    "hora": "09:30 a 10:00 hs",
    "evento": "Reunion Redes FBCR",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-04-22",
    "hora": "10:00 a 11:30 hs",
    "evento": "Taller de Alfabetizacion Digital para Asociados Vitalicios",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-23",
    "hora": "09:00 a 10:00 hs",
    "evento": "Taller de Educacion Financiera – Colegio Boneo",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-04-23",
    "hora": "09:30 a 10:30 hs",
    "evento": "Charla Interna Reporte de Sostentabilidad",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-24",
    "hora": "09:00 a 10:00 hs",
    "evento": "Visita al Lab con UNICEF",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-04-24",
    "hora": "11:30 a 12:30 hs",
    "evento": "Remate 1er Lote de Soja",
    "equipo": "Ana- Nico-Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-04-28",
    "hora": "10:30 a 12:00 hs",
    "evento": "Charla de Gestion Energetica y Financiamiento Sostenible",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-04-29",
    "hora": "09:30 a 11:00 hs",
    "evento": "Ecuentro con Unidades Priductivas. Sede de Gobierno",
    "equipo": "Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-05",
    "hora": "10:00 a 11:00 hs",
    "evento": "Reunion interna Sostenibilidad",
    "equipo": "Ana/Nico/Juanma",
    "metricas": "14 Colaboradores"
  },
  {
    "fecha": "2026-05-05",
    "hora": "17:00 a 19:00 hs",
    "evento": "Reunion de Formación Docente",
    "equipo": "Ana/Nico/Juanma",
    "metricas": "93 Docentes participaron"
  },
  {
    "fecha": "2026-05-06",
    "hora": "",
    "evento": "Reunion Planificacion Agromakers",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-08",
    "hora": "09:00 a 10:00 hs",
    "evento": "Reunión Comisión de Jóvenes Asociados",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-08",
    "hora": "11:30 a 12:30 hs",
    "evento": "Reunion FBCR",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-11",
    "hora": "10:00 a 11:00 hs",
    "evento": "Reunion con Marita de Banco Macro - Presencial",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-11",
    "hora": "11:00 a 12:00 hs",
    "evento": "Reunion OSC Maternidad Martin",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-11",
    "hora": "12:00 a 13:00 hs",
    "evento": "Reunion OSC Vecinal Maradona",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-12",
    "hora": "08:00 a 12 hs",
    "evento": "Agromakers Edicion Local Cafferata",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-12",
    "hora": "11:00 a 11:30 hs",
    "evento": "Reunion informativa con docentes de Bombal",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-12",
    "hora": "17:00 a 19:00 hs",
    "evento": "Curso de Formación Docente",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-13",
    "hora": "08:00 a 12 hs",
    "evento": "Agromakers Edición Local Los Quirquinchos",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-13",
    "hora": "09:30 a 10:00 hs",
    "evento": "Reunion (virtual) Fund. Conectar Solidario",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-14",
    "hora": "08:00 a 12 hs",
    "evento": "Agromakers Edición Local Firmat",
    "equipo": "Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-14",
    "hora": "11:00 a 12:00 hs",
    "evento": "Reunión Informativa Expo Facultades Firmat",
    "equipo": "Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-14",
    "hora": "14:00 a 15:00 hs",
    "evento": "Encuesta Virtual OSC",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-15",
    "hora": "10:30 a 11:00 hs",
    "evento": "Reunión (virtual) de Sostenibilidad",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-18",
    "hora": "10:30 a 11:00 hs",
    "evento": "Reunion (virtual) con Colegio Natividad del Señor - Motivo: Introduccion a Agromakers",
    "equipo": "Nico/Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-18",
    "hora": "12:00 hs",
    "evento": "Reunión con UNR – Repaso próxima edición del curso de Auxiliar en Agroindustria",
    "equipo": "Ana/Juanma/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-18",
    "hora": "14:30 hs",
    "evento": "Reunión con UNICEF por Danzar por la Paz",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-19",
    "hora": "09:00 a 10:00 hs",
    "evento": "Plan Mil65 Lugar: Cultural Fontanarrosa",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-19",
    "hora": "17:00 a 19:00 hs",
    "evento": "Formación Docente 4ta. Clase",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-19",
    "hora": "18:30 hs",
    "evento": "Evento UNICEF Donde Empieza el Futuro – Malba, Bs As",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-20",
    "hora": "08:00 a 12 hs",
    "evento": "Agromakers Edición Local Bigand",
    "equipo": "Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-20",
    "hora": "11:00 a 12:00 hs",
    "evento": "Reunión (virtual)Relevamiento OSC – Eduardo Cruz",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-20",
    "hora": "14:30 a 15:30 hs",
    "evento": "Reunión (virtual) Relevamiento OSC – Caro Roldan - Orillas",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-20",
    "hora": "15:30 a 16:30 hs",
    "evento": "Reunión (virtual) Relevamiento OSC – Gustavo Rios",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-21",
    "hora": "",
    "evento": "15:30 q 16:00 hs – Reunión (virtual) ONG – Emma Pafunddi - Rotary",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-21",
    "hora": "08:00 a 12 hs",
    "evento": "Agromakers Edición Local Cañada de Ucle",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-21",
    "hora": "09:00 a 10:00 hs",
    "evento": "Reunión por BCR en Territorio Ciudad de Galvez",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-21",
    "hora": "10:30 a 11:00 hs",
    "evento": "Reunión con Bernardo Baldarenas – ONG La Casa del Paraná",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-22",
    "hora": "08:00 a 12 hs",
    "evento": "Agromakers Edición Local Chabas",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-26",
    "hora": "10:00 a 11:00 hs",
    "evento": "Reunión de Consejo de Fundación",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-26",
    "hora": "12:00 a 13:00 hs",
    "evento": "Meet Virtual con Estudiantes de la Austral",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-26",
    "hora": "17 a 19 hs",
    "evento": "Formacion Docente – 5ta Clase",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-27",
    "hora": "11:00 a 13:30 hs",
    "evento": "Inauguración de Colectivo de Sueños. Lugar: Estacion Fluvial – Salón Embarcadero",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-27",
    "hora": "15:00 a 16:00 hs",
    "evento": "Charla Boom de la Economía Espacial",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-28",
    "hora": "",
    "evento": "Polotecnoligorosario -Tentativo",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-28",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers Edición Local – Cruz Alta (Cordoba)",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-28",
    "hora": "10:00 a 11:00 hs",
    "evento": "Charla Sum del Espacio Marker",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-05-28",
    "hora": "15:00 a 16 hs",
    "evento": "Encuesta (Virtual) OSC – Coop. Normal 2",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-05-28",
    "hora": "18:30 hs",
    "evento": "a 19:30 hs – Semana Superior 2026. Lugar: Escuela Superior de Comercio",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-05-29",
    "hora": "09:00 a 12:00 hs",
    "evento": "Viaje a Galvez x BCR en Territorio",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-01",
    "hora": "08:00 a 09:00 hs",
    "evento": "Reunión con Pcia. Tema: Evento de Seguridad",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-01",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers Edición Local Pto. San Martin",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-01",
    "hora": "09:30 a 10:30 hs",
    "evento": "Comisión de Asociados",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-01",
    "hora": "10:30 a 12:00 hs",
    "evento": "Reunión por BCR en Territorio",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-01",
    "hora": "13:00 a 16:00 hs",
    "evento": "Agromakers Edición Local Andino",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-02",
    "hora": "09:30 a 11:00 hs",
    "evento": "Reunión con JCI",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-02",
    "hora": "16:30 a 17:00 hs",
    "evento": "Participación en Reunión de Mesa BCR",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-03",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers Edición Local Chanear Ladeado",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-03",
    "hora": "09:30 hs",
    "evento": "Actividad de Pacto Global – Reunión con Flavio Fuentes – Dir. Ejecutivo",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-03",
    "hora": "12:00 a 12:45 hs",
    "evento": "Reunión Virtual OSC – Silvina GIulato – Centro Fisherton",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-03",
    "hora": "13:30 a 14:15 hs",
    "evento": "Reunión Virtual OSC – María Rosa Julián APPLIR",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-04",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers Edición Local – Villa Eloisa",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-04",
    "hora": "10:00 a 14:00 hs",
    "evento": "Visita a Agroactiva",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-05",
    "hora": "08:00 a 14:00 hs",
    "evento": "Expo Carreras Alcorta",
    "equipo": "Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-08",
    "hora": "09:00 a 14:00 hs",
    "evento": "Exposición de Carreras y Oficios de Acebal 2026",
    "equipo": "Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-08",
    "hora": "10:30 a 11:15 hs",
    "evento": "Entrevista (virtual) OSC – Diego Dorta MUCAR",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-08",
    "hora": "11:00 a 12:00 hs",
    "evento": "Taller de Educación Financiera en BCR",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-08",
    "hora": "12:00 a 13:00 hs",
    "evento": "Entrevista (virtual) OSC – Adrian Lazzatti",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-09",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers Edicion Local- Armstrong",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-10",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers Local – Sagrado Corazón (Rosario)",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-10",
    "hora": "08:30 a 10:30 hs",
    "evento": "Diplomatura Dirigencial Centro de Corredores",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-10",
    "hora": "10:30 a 11:30 hs",
    "evento": "Afabetizacion Digital (Asociados)",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-11",
    "hora": "09:30 a 10:00 hs",
    "evento": "Reunion de Sostenibilidad",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-11",
    "hora": "10:00 a 10:30 hs",
    "evento": "Reunión con el área de Comunicación",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-11",
    "hora": "10:30 a 11:30 hs",
    "evento": "Reunión con DIYEE por BCR en Territorio y Gremial de Acopiadores",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-16",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromaker Edicion Local Bouquet",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-16",
    "hora": "12:00 a 13:00 hs",
    "evento": "Reunión con Comisión de Cultura",
    "equipo": "Ana",
    "metricas": "Cancelada"
  },
  {
    "fecha": "2026-06-16",
    "hora": "13:00 hs",
    "evento": "Reunión con Municipalidad de Venado Tuerto",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-16",
    "hora": "14:00 a 16:00 hs",
    "evento": "Curso de IA",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-17",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers – Edicion local Soldini",
    "equipo": "Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-17",
    "hora": "08:30 a 10:30 hs",
    "evento": "Diplomatura Dirigencial Centro de Corredores",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-17",
    "hora": "10:30 a 12:00 hs",
    "evento": "Curso para Socios Vitalicios",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-17",
    "hora": "20:30 hs",
    "evento": "Danzar por la Paz a beneficio de UNICEF Lugar: Teatro el Nacional - Caba",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-18",
    "hora": "",
    "evento": "Agomakers Edicion Local Acebal (mañana) - Los Nogales (tarde)",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-18",
    "hora": "",
    "evento": "18:00 – After Jóvenes Asociados",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-18",
    "hora": "15:00 a 15:30 hs",
    "evento": "Reunión por BCR en Territorio",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-19",
    "hora": "",
    "evento": "08:00 a 14: 00 hs – Ferias de Facultades- Firmat",
    "equipo": "Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-22",
    "hora": "11:00 a 12:00 hs",
    "evento": "Reunión por BCR en Territorio",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-23",
    "hora": "09:00 a 10:00 hs",
    "evento": "Reunión con Municipalidad - Tema: Programa 1000 + 65",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-23",
    "hora": "13:00 a 14:30 hs",
    "evento": "Reunión con- ONG Conciencia",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-23",
    "hora": "14:00 a 15:30 hs",
    "evento": "Decano UCA – Ciencias Económicas",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-24",
    "hora": "08:00 a 10:30 hs",
    "evento": "Diplomatura Dirigencial Centro de Corredores",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-24",
    "hora": "10:30 a 11:30 hs",
    "evento": "Taller para Socios Vitalicios",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-06-26",
    "hora": "",
    "evento": "BCR En Territorio – Ciudad de Galvez",
    "equipo": "Ana/Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-29",
    "hora": "10:00 a 11:00 hs",
    "evento": "Taller Educación Financiera para Colegio de Soldini en BCR",
    "equipo": "Nico",
    "metricas": "36 \nEstudiantes"
  },
  {
    "fecha": "2026-06-29",
    "hora": "11:15 a 13:00 hs",
    "evento": "1° Jornada de Investigación sobre Inclusión Social y Discapacidad: problemas, perspectivas y abordajes actuales – UGR (Universidad del Gran Rosario)",
    "equipo": "Ana/Juanma",
    "metricas": "30 Personas presencial y 69 virtual"
  },
  {
    "fecha": "2026-06-29",
    "hora": "13:00 a 17:00 hs",
    "evento": "Agromakers Local - Esc. La Paz",
    "equipo": "Nico/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-06-29",
    "hora": "16:30 a 18:00 hs",
    "evento": "Foro de Vinculación RSO – Gestión de Sostenibilidad e Innovación",
    "equipo": "Ana",
    "metricas": "17 Personas conectadas Virtual y 8 Presencial"
  },
  {
    "fecha": "2026-06-30",
    "hora": "08:00 a 13:00 hs",
    "evento": "Agromakers Local - Berabevú",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-06-30",
    "hora": "16:30 a 18:00 hs",
    "evento": "Clase Posgrado – Agronegocios UBA/Bayer - Visita al Lab",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-01",
    "hora": "08:30 a 09:30 hs",
    "evento": "Diplomatura Dirigencial Centro de Corredores – Presentación de Proyectos",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-01",
    "hora": "09:30 hs",
    "evento": "Presentación Plan Acción Climática - Provincia",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-01",
    "hora": "11:00 hs",
    "evento": "Reunión Institucional",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-01",
    "hora": "12:00 hs",
    "evento": "Reunión con Fundación Consilior",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-01",
    "hora": "15:00 a 16:00 hs",
    "evento": "Reunión con Caro Carbinell – Taller de Finanzas",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-02",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromaker Local en Villa Mugueta",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-02",
    "hora": "09:30 hs",
    "evento": "Reunión UNICEF",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-02",
    "hora": "11 hs",
    "evento": "Reunion Escuela Comunidad de La paz Donación mobiliario",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-02",
    "hora": "12:00 hs",
    "evento": "Reunión con ONG La Higuera",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-02",
    "hora": "13:30 hs",
    "evento": "Entrevista Virtual ONG",
    "equipo": "Ana/Juanma",
    "metricas": ""
  },
  {
    "fecha": "2026-07-03",
    "hora": "09:15 hs",
    "evento": "Reunión de Gerentes y Directores",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-14",
    "hora": "10 hs",
    "evento": "Reunion con Defensoría del Pueblo",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-15",
    "hora": "11 hs",
    "evento": "Reunion con A3 mercados y MAV",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-16",
    "hora": "11 hs",
    "evento": "Reunion con JCI",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-16",
    "hora": "11:30 hs",
    "evento": "Visita Vecinal FONAVI (Bv. Seguí y Roullon)",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-17",
    "hora": "",
    "evento": "10.30 Reunion planificación con asociados por conversatorio",
    "equipo": "ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-17",
    "hora": "",
    "evento": "11.30 Reunion con A3 Mercados. Repaso GRI",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-17",
    "hora": "12:30 hs",
    "evento": "Formulario Sostenibilidad",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-17",
    "hora": "9:30 hs",
    "evento": "Reunion con UNICEF por CIA",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-07-20",
    "hora": "10:30 hs",
    "evento": "Reunión de repaso Charla Educación Financiera con A3 y MAV",
    "equipo": "Ana/ Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-20",
    "hora": "11:30 hs",
    "evento": "reunion por presupuesto FBCR",
    "equipo": "Ana/ Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-20",
    "hora": "12:30 hs",
    "evento": "Reunion Bolsa de Santa Fe",
    "equipo": "Ana/ Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-21",
    "hora": "10:30 hs",
    "evento": "Reunion de Concejo FBCR",
    "equipo": "Concejo",
    "metricas": ""
  },
  {
    "fecha": "2026-07-21",
    "hora": "9:30 hs",
    "evento": "Reunion Embajadores PDA",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-22",
    "hora": "8 a 12 hs",
    "evento": "Instancia Local Agromakers en Cañada de Gomez",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-23",
    "hora": "8 a 12 hs",
    "evento": "Instancia Local en Pablo VI",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-24",
    "hora": "8 a 12 hs",
    "evento": "Instancia Local Agromakers en Alvarez",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-29",
    "hora": "",
    "evento": "Taller de Educación Financiera para OSC",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-07-30",
    "hora": "08:00 a 12:00 hs",
    "evento": "Agromakers en Bombal",
    "equipo": "Ana/Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-03",
    "hora": "",
    "evento": "Visita Esc San Miguel de Arcangel. Charla de Ed. finaniciera",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-04",
    "hora": "",
    "evento": "AgroMakers Local en Villa Minetti",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-04",
    "hora": "",
    "evento": "Taller de Ed. Financiera en Villa Minetti",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-04",
    "hora": "15 hs",
    "evento": "Reunión con KKL Fundación Israel en Bs As",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-04",
    "hora": "16:30 hs",
    "evento": "Reunión CEIA Consejo UNICEF",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-05",
    "hora": "",
    "evento": "AgroMakers Local en Tostado",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-05",
    "hora": "",
    "evento": "AgroMakers Local Ceres",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-05",
    "hora": "14 hs",
    "evento": "Reunión con Cargill y empresas del sector agro para profundizar en inversión social",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-06",
    "hora": "11 hs",
    "evento": "Reunión con Pacto Global",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-07",
    "hora": "10 hs",
    "evento": "Participación en la inauguración de la planta de alimentos de la UNR",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-11",
    "hora": "",
    "evento": "AgroMakers Local Boneo, Rosario",
    "equipo": "Ana y Nico",
    "metricas": "70 estudiantes, 4 docentes"
  },
  {
    "fecha": "2026-08-11",
    "hora": "14 hs",
    "evento": "Armado de ppt institucional para recaudar fondos para la final",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-12",
    "hora": "",
    "evento": "Reunión con Galvez por BCR en territorio",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-12",
    "hora": "10 hs",
    "evento": "Taller vitalicios de alfabetización digital",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-12",
    "hora": "11:30 hs",
    "evento": "Reunión con A3 Mercados para el armado de un programa",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-12",
    "hora": "15 hs",
    "evento": "Charla a mujeres en el Barrio Banana",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-13",
    "hora": "",
    "evento": "Agromakers local en Maria Juana",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-13",
    "hora": "",
    "evento": "Taller de Ed. Financiera en Maria Juana",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-13",
    "hora": "11 hs",
    "evento": "Charla con el Ministerio de Ambiente de la Pcia de Santa Fe",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-14",
    "hora": "",
    "evento": "Izamiento de la bandera (Monumento)",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-14",
    "hora": "",
    "evento": "Agromakers Local en Piamonte",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-18",
    "hora": "",
    "evento": "Agromakers Local en Las Parejas",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-18",
    "hora": "12 hs",
    "evento": "Reporte de sostenibilidad BCR",
    "equipo": "Ana",
    "metricas": ""
  },
  {
    "fecha": "2026-08-19",
    "hora": "",
    "evento": "Agromakers Local en Carcaraña",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-20",
    "hora": "",
    "evento": "Charla Matias Manna",
    "equipo": "Ana/ Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-20",
    "hora": "",
    "evento": "Agromakers Local Alcorta",
    "equipo": "Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-21",
    "hora": "",
    "evento": "Reunion CEIA UNICEF",
    "equipo": "Ana/ Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-21",
    "hora": "",
    "evento": "Aniversario Institucional BCR",
    "equipo": "Ana/ Nico",
    "metricas": ""
  },
  {
    "fecha": "2026-08-25",
    "hora": "",
    "evento": "Hackaton docente Tacuarendi y Florencia",
    "equipo": "Ana/ Nico",
    "metricas": "12 docentes"
  },
  {
    "fecha": "2026-08-26",
    "hora": "",
    "evento": "Charla: ¿Cómo reportar sostenibilidad: introduccón GRI?",
    "equipo": "Ana",
    "metricas": "100 inscripciones, 56 personas"
  }
]
