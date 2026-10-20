#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador V4 de correos sintéticos para clasificación del Buzón de la Ciudadanía
(Donostia / San Sebastián).

Principios:
- La entrada del futuro modelo es SOLO `texto` (asunto + cuerpo).
- `idioma`, categoría, subcategoría, gestor, zona, etc. son metadatos/ground truth
  para entrenamiento, evaluación y QA; NO forman parte del texto de entrada.
- No se genera `confianza`: la confianza debe producirla el modelo en inferencia.
- Los escenarios están ligados a la taxonomía suministrada.
- Se introducen variaciones de longitud, registro, errores, información ausente,
  ubicaciones y formulaciones para evitar un dataset de frases clonadas.

Uso:
  python generador_emails_donostia_v4.py --n 1000000 --out ./dataset_donostia_v3

Dependencias: Python >= 3.10. Sin API y sin conexión.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 1) TAXONOMÍA. Debe coincidir con el documento de referencia.
# ---------------------------------------------------------------------------

TAXONOMY = {
    "ESPACIO PÚBLICO": {
        "Árboles, plantas y jardines": "Mantenimiento y Servicios Urbanos",
        "Aceras y calzadas": "Mantenimiento y Servicios Urbanos",
        "Iluminación": "Mantenimiento y Servicios Urbanos",
        "Parques infantiles": "Mantenimiento y Servicios Urbanos",
        "Playas": "Mantenimiento y Servicios Urbanos / Salud y Medio Ambiente",
        "Ascensores, rampas y escaleras mecánicas": "Mantenimiento y Servicios Urbanos",
        "Tapas, sumideros y arquetas": "Mantenimiento y Servicios Urbanos",
        "Accesibilidad": "Mantenimiento y Servicios Urbanos / Movilidad",
        "Uso del espacio público": "Mantenimiento y Servicios Urbanos",
        "Baños públicos y cabinas": "Mantenimiento y Servicios Urbanos",
        "Mobiliario urbano": "Mantenimiento y Servicios Urbanos",
    },
    "LIMPIEZA Y RESIDUOS": {
        "Contenedores": "Mantenimiento y Servicios Urbanos",
        "Limpieza viaria": "Mantenimiento y Servicios Urbanos",
        "Recogida de residuos": "Mantenimiento y Servicios Urbanos",
        "Residuos orgánicos / Garbia / Joko": "Mantenimiento y Servicios Urbanos",
        "Plagas": "Salud y Medio Ambiente / Mantenimiento",
        "Otros residuos": "Mantenimiento y Servicios Urbanos",
    },
    "MOVILIDAD": {
        "Circulación y tráfico": "Movilidad / Guardia Municipal",
        "Aparcamientos": "Movilidad",
        "OTA": "Movilidad",
        "Bicicletas": "Movilidad",
        "Bidegorris": "Movilidad",
        "Transporte público": "Movilidad / DBUS",
        "Taxis": "Movilidad",
        "Zona de bajas emisiones": "Movilidad",
        "Señalización de tráfico": "Movilidad",
    },
    "FINANCIERA": {
        "Impuestos": "Financiera",
        "Tasas": "Financiera",
        "Domiciliaciones": "Financiera",
        "Recibos": "Financiera",
        "Certificados": "Financiera",
        "Pago online": "Financiera",
        "Multas": "Financiera / Movilidad / Guardia Municipal",
    },
    "SEGURIDAD Y CONVIVENCIA": {
        "Comportamientos incívicos": "Guardia Municipal",
        "Conductas sospechosas": "Guardia Municipal",
        "Conductas delictivas": "Guardia Municipal",
        "Ruido / molestias": "Salud y Medio Ambiente / Guardia Municipal",
        "Animales": "Salud y Medio Ambiente / Guardia Municipal",
        "Asentamientos": "Guardia Municipal / Acción Social",
        "Ocupación indebida del espacio público": "Guardia Municipal",
    },
    "MEDIO AMBIENTE": {
        "Ruido": "Salud y Medio Ambiente",
        "Malos olores": "Salud y Medio Ambiente",
        "Vertidos": "Salud y Medio Ambiente",
        "Calidad del aire": "Salud y Medio Ambiente",
        "Agua / saneamiento": "Salud y Medio Ambiente / Mantenimiento",
        "Plagas": "Salud y Medio Ambiente",
    },
    "URBANISMO": {
        "Obras en viviendas": "Urbanismo Sostenible",
        "Obras en edificios": "Urbanismo Sostenible",
        "Licencias": "Urbanismo Sostenible",
        "Actividades comerciales": "Urbanismo Sostenible",
        "Locales": "Urbanismo Sostenible",
        "Disciplina urbanística": "Urbanismo Sostenible",
        "Vivienda": "Etxegintza",
    },
    "OBRAS": {
        "Obras municipales": "Proyectos y Obras",
        "Obras en vía pública": "Proyectos y Obras / Mantenimiento",
        "Proyectos urbanos": "Proyectos y Obras",
        "Infraestructuras": "Proyectos y Obras",
    },
    "SERVICIOS SOCIALES": {
        "Ayudas sociales": "Acción Social",
        "Atención social": "Acción Social",
        "Personas mayores": "Acción Social",
        "Personas en situación de vulnerabilidad": "Acción Social",
        "Servicios sociales": "Acción Social",
    },
    "EDUCACIÓN": {
        "Centros educativos": "Promoción Social y Educación",
        "Actividades educativas": "Promoción Social y Educación",
        "Programas educativos": "Promoción Social y Educación",
    },
    "DEPORTE": {
        "Instalaciones deportivas": "Patronato Municipal de Deportes",
        "Equipamientos deportivos": "Patronato Municipal de Deportes",
        "Actividades deportivas": "Patronato Municipal de Deportes",
        "Cursos deportivos": "Patronato Municipal de Deportes",
    },
    "CULTURA": {
        "Actividades culturales": "Donostia Kultura",
        "Equipamientos culturales": "Donostia Kultura",
        "San Telmo": "San Telmo Museoa",
        "Victoria Eugenia": "Victoria Eugenia",
    },
    "EUSKERA": {
        "Euskera en servicios municipales": "Euskera",
        "Política lingüística": "Euskera",
        "Traducciones / atención lingüística": "Euskera",
    },
    "TURISMO": {
        "Información turística": "San Sebastián Turismo",
        "Turismo en la ciudad": "San Sebastián Turismo",
        "Actividades turísticas": "San Sebastián Turismo",
    },
    "TRANSPORTE": {
        "Autobuses urbanos": "DBUS",
        "Paradas de autobús": "Movilidad / DBUS",
    },
}

# ---------------------------------------------------------------------------
# 2) UBICACIONES. Lista amplia y deliberadamente variada.
# La fuente oficial dispone de un callejero mucho más extenso; esta lista es
# una base local portable para que el generador funcione sin conexión.
# ---------------------------------------------------------------------------

BARRIOS_ES = [
    "Aiete", "Altza", "Amara Berri", "Añorga", "Antiguo", "Ategorrieta-Ulia",
    "Centro", "Egia", "Gros", "Ibaeta", "Igeldo", "Intxaurrondo", "Loiola",
    "Martutene", "Miracruz-Bidebieta", "Miramon-Zorroaga", "Parte Vieja",
    "Riberas de Loiola", "Zubieta",
]

BARRIOS_EU = {
    "Aiete":"Aiete", "Altza":"Altza", "Amara Berri":"Amara Berri", "Añorga":"Añorga",
    "Antiguo":"Antiguo", "Ategorrieta-Ulia":"Ategorrieta-Ulia", "Centro":"Erdialdea",
    "Egia":"Egia", "Gros":"Gros", "Ibaeta":"Ibaeta", "Igeldo":"Igeldo",
    "Intxaurrondo":"Intxaurrondo", "Loiola":"Loiola", "Martutene":"Martutene",
    "Miracruz-Bidebieta":"Mirakruz-Bidebieta", "Miramon-Zorroaga":"Miramon-Zorroaga",
    "Parte Vieja":"Alde Zaharra", "Riberas de Loiola":"Loiolako Erriberak", "Zubieta":"Zubieta",
}

STREETS_ES = [
    "Avenida de Madrid", "Avenida de la Libertad", "Avenida de Navarra", "Avenida de Zarautz",
    "Avenida de Tolosa", "Avenida del Alcalde José Elosegi", "Avenida de Satrustegi",
    "Avenida de Carlos I", "Avenida de Barcelona", "Avenida de Buenos Aires", "Avenida de Sancho el Sabio",
    "Calle de Aldamar", "Calle de Aldakonea", "Calle de Ametzagaña", "Calle de Amara",
    "Calle de Andía", "Calle de Antonio María Labaien", "Calle de Arrasate", "Calle de Arostegieta",
    "Calle de Arroka", "Calle de Autonomía", "Calle de Balleneros", "Calle de Bengoetxea",
    "Calle de Bermingham", "Calle de Blas de Lezo", "Calle de Bordatxipi", "Calle de Bengoetxea",
    "Calle de Camino de los Pinos", "Calle de Catalina de Erauso", "Calle de Corta",
    "Calle de Duque de Mandas", "Calle de Easo", "Calle de Egia", "Calle de Eustasio Amilibia",
    "Calle de Fuenterrabía", "Calle de Garibai", "Calle de General Echagüe", "Calle de General Jauregui",
    "Calle de Gloria Fuertes", "Calle de Gran Vía", "Calle de Hernani", "Calle de Igentea",
    "Calle de Iparragirre", "Calle de Isabel II", "Calle de Javier Barkaiztegi", "Calle de José Miguel Barandiaran",
    "Calle de José María Sert", "Calle de Juan de Bilbao", "Calle de Katalina Eleizegi", "Calle de Konkorrenea",
    "Calle de Larramendi", "Calle de Legazpi", "Calle de Loiola", "Calle de Luis Pradera",
    "Calle de Mari", "Calle de Matia", "Calle de Miracruz", "Calle de Moraza", "Calle de Mundaiz",
    "Calle de Narrika", "Calle de Nuestra Señora del Coro", "Calle de Okendo", "Calle de Olarain",
    "Calle de Peñaflorida", "Calle de Pescadería", "Calle de Prim", "Calle de Ramón María Lili",
    "Calle de Ronda", "Calle de San Martín", "Calle de San Juan", "Calle de San Lorenzo", "Calle de San Marcial",
    "Calle de San Roque", "Calle de Secundino Esnaola", "Calle de Serrano Anguita", "Calle de Txofre",
    "Calle de Urbieta", "Calle de Usandizaga", "Calle de Zabaleta", "Calle de Zubieta",
    "Calle de Zumalakarregi", "Calle de Zubiaurre", "Calle de Zarautz", "Calle de Paseo de Aiete",
    "Paseo de Anoeta", "Paseo de Arriola", "Paseo de Bera Bera", "Paseo de Colón", "Paseo de Errotaburu",
    "Paseo de Federico García Lorca", "Paseo de Francia", "Paseo de Herrera", "Paseo de Igeldo",
    "Paseo de Larratxo", "Paseo de Miramón", "Paseo de Mikeletegi", "Paseo de Nuevo de Gros",
    "Paseo de Ondarreta", "Paseo de Salamanca", "Paseo de Ulia", "Paseo de Zorroaga",
    "Camino de Aiete", "Camino de Igara", "Camino de Marbil", "Camino de Mundaiz", "Camino de Polloe",
    "Camino de Zubiaurre", "Plaza de Gipuzkoa", "Plaza de Cataluña", "Plaza de Cervantes", "Plaza de Easo",
    "Plaza de Euskadi", "Plaza de Ferrerias", "Plaza de Irún", "Plaza de Lasala", "Plaza de Okendo",
    "Plaza de Pío XII", "Plaza de Sarriegi", "Plaza de Teresa de Calcuta", "Plaza de Zaragoza",
]

# Formas vascas frecuentes, sin pretender ser una traducción mecánica de cada vía.
STREETS_EU = [
    "Askatasunaren Hiribidea", "Nafarroa Hiribidea", "Zarautz Hiribidea", "Tolosa Hiribidea",
    "Jose Elosegi Alkatearen Hiribidea", "Satrustegi Hiribidea", "Madril Hiribidea", "Carlos I Hiribidea",
    "Aldamar Kalea", "Aldakonea Kalea", "Ametzagaña Kalea", "Andia Kalea", "Arrasate Kalea",
    "Arroka Kalea", "Autonomia Kalea", "Balleneros Kalea", "Bermingham Kalea", "Blas de Lezo Kalea",
    "Bengoetxea Kalea", "Catalina de Erauso Kalea", "Duque de Mandas Kalea", "Easo Kalea",
    "Egia Kalea", "Fuenterrabia Kalea", "Garibai Kalea", "Hernani Kalea", "Igentea Kalea",
    "Iparragirre Kalea", "Isabel II.a Kalea", "Loiola Kalea", "Matia Kalea", "Mirakruz Kalea",
    "Mundaiz Kalea", "Narrika Kalea", "Okendo Kalea", "Peñaflorida Kalea", "Prim Kalea",
    "San Martin Kalea", "San Juan Kalea", "San Marcial Kalea", "Txofre Kalea", "Urbieta Kalea",
    "Usandizaga Kalea", "Zabaleta Kalea", "Zubieta Kalea", "Zumalakarregi Hiribidea",
    "Anoeta Pasealekua", "Bera Bera Pasealekua", "Frantzia Pasealekua", "Herrera Pasealekua",
    "Igeldo Pasealekua", "Miramongo Pasealekua", "Mikeletegi Pasealekua", "Ondarreta Pasealekua",
    "Ulia Pasealekua", "Zorroaga Pasealekua", "Gipuzkoa Plaza", "Katalunia Plaza", "Cervantes Plaza",
    "Easo Plaza", "Euskadi Plaza", "Okendo Plaza", "Pio XII.a Plaza", "Sarriegi Plaza", "Zaragoza Plaza",
]

LANDMARKS = [
    "La Concha", "Ondarreta", "Zurriola", "Playa de la Concha", "Playa de Ondarreta", "Playa de Zurriola",
    "Alderdi Eder", "Boulevard", "Kursaal", "Palacio de Miramar", "Parque Cristina Enea", "Parque de Aiete",
    "Parque de Ametzagaina", "Parque de Ulia", "Urgull", "Monte Igueldo", "Anoeta", "Reale Arena",
    "Polideportivo Paco Yoldi", "Velódromo Antonio Elorza", "Palacio de Hielo Txuri Urdin", "Atano III.a",
    "Pista de Atletismo de Anoeta", "Tabakalera", "Teatro Victoria Eugenia", "Museo San Telmo", "Aquarium",
    "Palacio de Congresos Kursaal", "Estación del Norte", "Estación de Autobuses", "Euskotren Amara",
    "Hospital Universitario Donostia", "Polloe", "Mercado de la Bretxa", "Mercado de San Martín",
    "Mercado de Altza", "Plaza de Gipuzkoa", "Plaza de Okendo", "Plaza Easo", "Plaza Cataluña",
    "Paseo Nuevo", "Paseo de Salamanca", "Puente de María Cristina", "Puente de Santa Catalina",
    "Puente del Kursaal", "Puente de Mundaiz", "Puente de Real Compañía de María", "Tunel de Aiete",
]

DBUS_LINES = [
    "05 Benta Berri", "08 Gros-Intxaurrondo", "09 Egia-Intxaurrondo", "13 Altza", "14 Bidebieta",
    "16 Igeldo", "17 Gros-Amara-Miramon", "18 Seminarioa", "19 Aiete-Bera Bera", "21 Amara-Mutualitateak",
    "23 Errondo-Puio", "24 Altza-Gros-Antiguo-Intxaurrondo", "25 Benta Berri-Añorga", "26 Amara-Martutene",
    "27 Altza-Intxaurrondo-Antiguo-Gros", "28 Amara-Ospitaleak", "29 Intxaurrondo Sur", "31 Intxaurrondo-Ospitaleak-Altza",
    "32 Puio-Errondo", "33 Larratxo-Intxaur-Berio-Igara", "35 Antiguo-Aiete-Ospitaleak", "40 Gros-Antiguo-Igara",
    "41 Gros-Egia-Martutene", "43 Anoeta-Igara", "45 Estaciones-Renfe-Bus-Antiguo-Aiete",
]

BUS_STOPS = [
    "Boulevard", "Okendo", "Gipuzkoa Plaza", "Zurriola", "Gran Vía", "Anoeta", "Sancho el Sabio",
    "Easo", "Morlans", "Matia", "Ondarreta", "Antiguo Berri", "Benta Berri", "Universidad",
    "Aiete", "Bera Bera", "Intxaurrondo", "Larratxo", "Altza", "Bidebieta", "Martutene",
    "Loiola", "Riberas de Loiola", "Miramon", "Hospitales", "Egia", "Tabakalera", "Estación del Norte",
]

PLACES = LANDMARKS + [f"{x} ({b})" for x in LANDMARKS[:18] for b in BARRIOS_ES[:4]]

# ---------------------------------------------------------------------------
# 3) PERFILES DE ESCRITURA
# ---------------------------------------------------------------------------

OPENERS_ES = [
    "Buenos días", "Buenas", "Buenas tardes", "Hola", "Hola, quería comentar una cosa", "A quien corresponda",
]
OPENERS_EU = [
    "Egun on", "Kaixo", "Arratsalde on", "Kaixo, gauza bat komentatu nahi nizueke", "Dagokionari",
]
CLOSERS_ES = [
    "Gracias", "Muchas gracias", "Gracias de antemano", "Un saludo", "Saludos", "Espero que puedan revisarlo",
    "A ver si se puede solucionar", "Quedo a la espera", "Gracias por la atención",
]
CLOSERS_EU = [
    "Eskerrik asko", "Mila esker", "Aldez aurretik eskerrik asko", "Agur", "Ondo izan", "Mesedez, begiratu ahal baduzue",
    "Ea konponbidea aurkitzen den", "Zuen erantzunaren zain geratzen naiz",
]

TIME_ES = [
    "desde ayer", "desde hace unos días", "desde la semana pasada", "lleva así varios días", "desde hace bastante tiempo",
    "esta mañana", "esta tarde", "anoche", "hoy a primera hora", "durante el fin de semana", "últimamente",
    "desde hace semanas", "cada vez que paso por allí", "desde hace meses", "llevo varios días viéndolo",
]
TIME_EU = [
    "atzoz geroztik", "duela egun batzuk", "joan den astetik", "hainbat egun daramatza horrela", "aspalditik",
    "gaur goizean", "gaur arratsaldean", "bart", "gaur goiz-goizetik", "asteburuan", "azkenaldian",
    "duela aste batzuetatik", "handik pasatzen naizen bakoitzean", "duela hilabete batzuetatik",
]

FORMAL_ES = [
    "Les agradecería que comprobaran la situación.", "Solicito, por favor, que se revise el asunto.",
    "Agradecería que me indicaran cómo proceder.", "Si es posible, agradecería una solución.",
]
FORMAL_EU = [
    "Mesedez, egoera egiaztatzea eskertuko nuke.", "Gaia berrikustea eskatzen dut.",
    "Nola jokatu behar dudan adieraztea eskertuko nuke.", "Ahal bada, konponbide bat bilatzea eskertuko nuke.",
]

# ---------------------------------------------------------------------------
# 4) ESCENARIOS: cada subcategoría tiene un núcleo semántico propio.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Spec:
    key: str
    es: Tuple[str, ...]
    eu: Tuple[str, ...]
    subjects_es: Tuple[str, ...]
    subjects_eu: Tuple[str, ...]
    loc: str = "street"
    urgency_bias: str = "normal"


def S(key, es, eu, subjects_es, subjects_eu, loc="street", urgency_bias="normal"):
    return Spec(key, tuple(es), tuple(eu), tuple(subjects_es), tuple(subjects_eu), loc, urgency_bias)

SCENARIOS: Dict[Tuple[str, str], Spec] = {}

# Textos deliberadamente específicos; se combinan con perfiles y localizaciones.
SPECS = [
S("Árboles, plantas y jardines",
 ["hay una rama grande caída", "un árbol tiene varias ramas secas que parecen a punto de caer", "las raíces han levantado el pavimento", "un árbol está muy inclinado", "las ramas están invadiendo la acera", "un parterre está completamente descuidado", "se ha secado parte de la zona ajardinada"],
 ["adar handi bat erorita dago", "zuhaitz batek adar lehorrak ditu eta erortzeko arriskua ematen du", "sustraiek espaloia altxatu dute", "zuhaitza oso makurtuta dago", "adarrek espaloia hartzen dute", "lorategia oso utzita dago", "berdegune zati bat lehortu da"],
 ["Árboles y jardines", "Ramas caídas", "Un árbol en mal estado", "Problema con un árbol"], ["Zuhaitzak eta lorategiak", "Eroritako adarrak", "Egoera txarreko zuhaitza", "Arazoa zuhaitz batekin"], "street", "high"),
S("Aceras y calzadas",
 ["hay un agujero bastante grande en la acera", "varias baldosas están rotas y se mueven", "la calzada tiene un bache muy profundo", "el asfalto está levantado", "hay una zona de la acera hundida", "cuando llueve se forma un charco enorme por el mal estado del firme"],
 ["espaloian zulo handi bat dago", "baldosa batzuk apurtuta eta solte daude", "errepidean zulo sakon bat dago", "asfaltoa altxatuta dago", "espaloi zati bat hondoratuta dago", "euria egiten duenean putzu handi bat sortzen da bidearen egoeragatik"],
 ["Aceras", "Bache en la calzada", "Baldosas rotas", "Estado del pavimento"], ["Espaloiak", "Zuloa errepidean", "Baldosa apurtuak", "Zoladuraren egoera"], "street", "high"),
S("Iluminación",
 ["hay una farola que lleva varios días sin funcionar", "varias luces de la calle están apagadas", "la farola parpadea continuamente", "una luminaria se ha quedado encendida durante el día", "una zona queda completamente a oscuras por la noche"],
 ["farola bat hainbat egun daramatza piztu gabe", "kaleko hainbat argi itzalita daude", "farola etengabe keinuka ari da", "argia egunez ere piztuta geratzen da", "gauez eremu bat erabat ilun geratzen da"],
 ["Farola averiada", "Problema de iluminación", "Luces apagadas", "Alumbrado de la calle"], ["Farola matxuratuta", "Argiztapen arazoa", "Itzalitako argiak", "Kaleko argiteria"], "street", "high"),
S("Parques infantiles",
 ["un columpio está roto", "el suelo de caucho está levantado", "una valla del parque infantil está rota", "hay una pieza suelta en un juego", "varios juegos llevan tiempo sin mantenimiento", "el parque está lleno de cristales"],
 ["kulunka bat apurtuta dago", "kautxuzko zorua altxatuta dago", "haur-parkeetako hesi bat apurtuta dago", "jolas bateko pieza bat solte dago", "jolas batzuk denbora daramate mantentzerik gabe", "parkea kristalez beteta dago"],
 ["Parque infantil", "Juego roto", "Problema en un columpio", "Estado del parque"], ["Haur-parkea", "Jolas apurtua", "Arazoa kulunkan", "Parkearen egoera"], "park", "high"),
S("Playas",
 ["hay mucha suciedad acumulada en la arena", "una ducha de la playa no funciona", "hay restos de algas y residuos en una zona", "varias papeleras están desbordadas", "hay un problema con el acceso a la playa", "la zona de baño presenta una situación que debería revisarse"],
 ["hondarretan zikinkeria asko pilatu da", "hondartzako dutxa batek ez du funtzionatzen", "alga eta hondakin ugari daude eremu batean", "zakarrontzi batzuk gainezka daude", "hondartzara sartzeko arazo bat dago", "bainatzeko eremuak berrikusi beharreko egoera bat du"],
 ["Problema en la playa", "Estado de la playa", "Duchas de la playa", "Limpieza de la playa"], ["Hondartzako arazoa", "Hondartzaren egoera", "Hondartzako dutxak", "Hondartzaren garbiketa"], "beach", "normal"),
S("Ascensores, rampas y escaleras mecánicas",
 ["el ascensor público no funciona", "la rampa está bloqueada", "la escalera mecánica lleva días parada", "el ascensor se queda atascado", "la rampa tiene una parte rota", "hay un problema de acceso en el elevador"],
 ["igogailu publikoa ez dabil", "arrapala blokeatuta dago", "eskailera mekanikoa egun batzuk geldirik dago", "igogailua trabatu egiten da", "arrapalaren zati bat apurtuta dago", "igogailuan sartzeko arazo bat dago"],
 ["Ascensor público", "Rampa averiada", "Escalera mecánica", "Problema de accesibilidad vertical"], ["Igogailu publikoa", "Arrapala matxuratuta", "Eskailera mekanikoa", "Sarbide bertikaleko arazoa"], "landmark", "high"),
S("Tapas, sumideros y arquetas",
 ["hay una tapa de alcantarilla suelta", "una arqueta está hundida", "el sumidero está atascado", "falta una tapa", "la tapa hace mucho ruido cada vez que pasa un coche", "cuando llueve el sumidero no traga el agua"],
 ["estolda tapa bat solte dago", "kutxatila bat hondoratuta dago", "estolda-zuloa buxatuta dago", "tapa bat falta da", "tapa batek zarata handia egiten du autoak pasatzean", "euria egiten duenean estolda-zuloak ez du ura hartzen"],
 ["Tapa de alcantarilla", "Arqueta", "Sumidero atascado", "Tapa suelta"], ["Estolda tapa", "Kutxatila", "Buxatutako estolda-zuloa", "Tapa solte"], "street", "high"),
S("Accesibilidad",
 ["hay un bordillo que impide pasar con silla de ruedas", "el paso accesible está ocupado", "falta un rebaje en el bordillo", "la ruta accesible queda cortada", "una plaza reservada no se puede utilizar", "hay una barrera para personas con movilidad reducida"],
 ["espaloi-ertzak gurpil-aulkiarekin pasatzea eragozten du", "irisgarri den pasabidea okupatuta dago", "espaloi-ertzean beheragunerik ez dago", "ibilbide irisgarria moztuta dago", "erreserbatutako plaza ezin da erabili", "mugikortasun urriko pertsonentzako oztopo bat dago"],
 ["Accesibilidad", "Paso accesible", "Barrera en la acera", "Plaza reservada"], ["Irisgarritasuna", "Pasabide irisgarria", "Espaloiaren oztopoa", "Erreserbatutako plaza"], "street", "high"),
S("Uso del espacio público",
 ["hay mesas ocupando demasiado espacio en la acera", "se ha colocado una estructura en la calle y dificulta el paso", "una actividad está ocupando la vía pública", "hay una ocupación del espacio que obliga a pasar por la calzada", "se ha instalado algo sin dejar espacio suficiente para peatones"],
 ["mahai batzuek espaloian leku gehiegi hartzen dute", "egitura bat jarri dute kalean eta pasatzea zailtzen du", "jarduera batek bide publikoa okupatzen du", "espazioa okupatuta dago eta galtzadatik pasa behar da", "zerbait jarri dute oinezkoentzat nahikoa leku utzi gabe"],
 ["Uso del espacio público", "Ocupación de la acera", "Problema en la vía pública", "Paso peatonal ocupado"], ["Espazio publikoaren erabilera", "Espaloiaren okupazioa", "Bide publikoko arazoa", "Oinezkoen pasabidea okupatuta"], "street", "normal"),
S("Baños públicos y cabinas",
 ["el baño público está cerrado", "una cabina no funciona", "el baño está en muy malas condiciones", "falta papel y no hay jabón", "la puerta del baño no cierra", "hay suciedad acumulada en la cabina"],
 ["komun publikoa itxita dago", "kabina batek ez du funtzionatzen", "komuna oso egoera txarrean dago", "papera falta da eta ez dago xaboirik", "komuneko atea ez da ixten", "kabinan zikinkeria pilatu da"],
 ["Baño público", "Cabina cerrada", "Estado de los baños", "Problema en un baño"], ["Komun publikoa", "Kabina itxita", "Komunen egoera", "Arazoa komun batean"], "landmark", "normal"),
S("Mobiliario urbano",
 ["un banco está roto", "una papelera está arrancada", "una barandilla está suelta", "hay un bolardo caído", "una fuente pública no funciona", "el banco está en muy mal estado"],
 ["banku bat apurtuta dago", "zakarrontzi bat errotik aterata dago", "baranda bat solte dago", "zutoin bat erorita dago", "iturria ez dabil", "bankua oso egoera txarrean dago"],
 ["Banco roto", "Papelera rota", "Barandilla", "Mobiliario urbano"], ["Banku apurtua", "Zakarrontzi apurtua", "Baranda", "Hiriko altzariak"], "street", "normal"),

S("Contenedores", ["el contenedor está desbordado", "la tapa del contenedor está rota", "hay contenedores que no se han vaciado", "el contenedor desprende un olor muy fuerte", "el contenedor está colocado de forma que bloquea el paso", "han desaparecido varios contenedores de la zona"],
 ["edukiontzia gainezka dago", "edukiontziaren tapa apurtuta dago", "edukiontzi batzuk ez dituzte hustu", "edukiontziak usain oso handia du", "edukiontziak pasabidea oztopatzen du", "inguruko hainbat edukiontzi desagertu dira"],
 ["Contenedor lleno", "Contenedor roto", "Problema con contenedores", "Contenedores sin recoger"], ["Edukiontzia beteta", "Edukiontzi apurtua", "Edukiontzien arazoa", "Jaso gabeko edukiontziak"], "street", "normal"),
S("Limpieza viaria", ["la calle está llena de suciedad", "llevan días sin limpiar esta zona", "hay manchas en el suelo que no se quitan", "la acera está llena de hojas y residuos", "hay basura esparcida por toda la calle", "la limpieza de la zona es insuficiente"],
 ["kalea zikinkeriaz beteta dago", "egun batzuk daramatzate eremu hau garbitu gabe", "lurrean orbanak daude eta ez dira kentzen", "espaloia hostoz eta hondakinez beteta dago", "zaborra kale osoan zehar sakabanatuta dago", "eremuaren garbiketa ez da nahikoa"],
 ["Limpieza de la calle", "Calle sucia", "Problema de limpieza", "Suciedad en la acera"], ["Kalearen garbiketa", "Kale zikina", "Garbiketa arazoa", "Zikinkeria espaloian"], "street", "normal"),
S("Recogida de residuos", ["la basura no se ha recogido", "han dejado varias bolsas fuera del contenedor", "la recogida de voluminosos no se ha realizado", "han pasado a recoger pero se han dejado restos", "el servicio no ha recogido los residuos previstos"],
 ["zaborra ez dute jaso", "hainbat poltsa edukiontzitik kanpo utzi dituzte", "tamaina handiko hondakinak ez dituzte jaso", "jasotzera joan dira baina hondarrak utzi dituzte", "zerbitzuak ez ditu aurreikusitako hondakinak jaso"],
 ["Recogida de residuos", "Basura sin recoger", "Problema con la recogida", "Recogida de voluminosos"], ["Hondakinen bilketa", "Jaso gabeko zaborra", "Bilketako arazoa", "Tamaina handiko hondakinen bilketa"], "street", "normal"),
S("Residuos orgánicos / Garbia / Joko", ["el sistema de residuos orgánicos no está funcionando", "no puedo utilizar correctamente el contenedor orgánico", "la tarjeta de acceso al contenedor no funciona", "el punto de recogida orgánica presenta un problema", "tengo dudas sobre dónde depositar los residuos orgánicos"],
 ["hondakin organikoen sistema ez dabil", "ezin dut edukiontzi organikoa behar bezala erabili", "edukiontzira sartzeko txartelak ez du funtzionatzen", "hondakin organikoak biltzeko puntuak arazo bat du", "zalantzak ditut hondakin organikoak non utzi"],
 ["Residuos orgánicos", "Contenedor orgánico", "Garbia", "Joko"], ["Hondakin organikoak", "Edukiontzi organikoa", "Garbia", "Joko"], "street", "normal"),
S("Plagas", ["hay ratas en la zona", "han aparecido cucarachas", "hay muchos insectos alrededor de los contenedores", "se ven roedores con frecuencia", "hay una plaga que está afectando a los vecinos"],
 ["arratoiak daude inguruan", "labezomorroak agertu dira", "intsektu asko daude edukiontzien inguruan", "karraskariak maiz ikusten dira", "izurrite batek auzokideei eragiten die"],
 ["Plaga en la calle", "Ratas", "Cucarachas", "Problema de plagas"], ["Izurritea kalean", "Arratoiak", "Labezomorroak", "Izurrite arazoa"], "street", "high"),
S("Otros residuos", ["han dejado un colchón en la calle", "hay muebles abandonados", "han tirado escombros junto a un contenedor", "hay bolsas de residuos fuera de lugar", "han dejado un electrodoméstico en la vía pública", "hay residuos que llevan varios días abandonados"],
 ["koltxoi bat utzi dute kalean", "altzariak abandonatuta daude", "obra-hondakinak edukiontzi baten ondoan bota dituzte", "hondakin-poltsak leku desegokian daude", "etxetresna elektriko bat bide publikoan utzi dute", "hondakinak hainbat egun daramatzate abandonatuta"],
 ["Residuos abandonados", "Muebles en la calle", "Escombros", "Otros residuos"], ["Abandonatutako hondakinak", "Altzariak kalean", "Obra-hondakinak", "Beste hondakin batzuk"], "street", "normal"),

S("Circulación y tráfico", ["hay coches aparcando en doble fila y dificultando el paso", "se forma un atasco recurrente", "los vehículos circulan demasiado rápido", "hay maniobras peligrosas en este cruce", "los coches invaden una zona peatonal", "la circulación se complica mucho en determinadas horas"],
 ["autoak bigarren ilaran aparkatzen ari dira eta pasabidea oztopatzen dute", "auto-ilarak behin eta berriz sortzen dira", "ibilgailuak azkarregi ibiltzen dira", "gurutzagune honetan maniobra arriskutsuak daude", "autoek oinezkoen eremua hartzen dute", "zirkulazioa oso zaila da ordu jakinetan"],
 ["Problema de tráfico", "Circulación", "Atasco", "Tráfico peligroso"], ["Trafiko arazoa", "Zirkulazioa", "Auto-ilarak", "Trafiko arriskutsua"], "street", "high"),
S("Aparcamientos", ["es imposible encontrar aparcamiento en la zona", "hay plazas ocupadas durante días por vehículos que no se mueven", "se necesita revisar el aparcamiento de la zona", "hay vehículos que ocupan una plaza de forma indebida", "el acceso al aparcamiento está bloqueado"],
 ["ezinezkoa da inguruan aparkaleku bat aurkitzea", "plazak egunetan okupatuta daude mugitzen ez diren ibilgailuekin", "inguruko aparkalekua berrikusi beharko litzateke", "ibilgailu batzuek plaza bat modu desegokian okupatzen dute", "aparkalekurako sarbidea blokeatuta dago"],
 ["Aparcamiento", "Problema de aparcamiento", "Plazas ocupadas", "Acceso al aparcamiento"], ["Aparkalekua", "Aparkaleku arazoa", "Okupatutako plazak", "Aparkalekurako sarbidea"], "street", "normal"),
S("OTA", ["la máquina de OTA no funciona", "no puedo pagar la OTA", "la aplicación no reconoce la zona", "he tenido un problema con el ticket de OTA", "la señalización de la zona OTA no está clara", "la zona de OTA parece estar mal delimitada"],
 ["OTAko makinak ez du funtzionatzen", "ezin dut OTA ordaindu", "aplikazioak ez du eremua ezagutzen", "arazoa izan dut OTAko tiketearekin", "OTA eremuaren seinaleztapena ez dago argi", "OTA eremua gaizki mugatuta dagoela dirudi"],
 ["Problema con la OTA", "Máquina OTA", "Ticket OTA", "Zona OTA"], ["OTAren arazoa", "OTA makina", "OTA txartela", "OTA eremua"], "street", "normal"),
S("Bicicletas", ["hay bicicletas circulando por una zona peatonal", "una bicicleta está abandonada y bloquea el paso", "faltan espacios para aparcar bicicletas", "hay un problema con el estacionamiento de bicicletas", "se ven bicicletas atadas a elementos donde dificultan el paso"],
 ["bizikletak oinezkoen eremuan ibiltzen dira", "bizikleta bat abandonatuta dago eta pasabidea oztopatzen du", "bizikletak uzteko leku falta dago", "bizikletak aparkatzeko arazo bat dago", "bizikletak lotuta daude eta pasabidea oztopatzen dute"],
 ["Bicicletas", "Bicicleta abandonada", "Aparcamiento de bicicletas", "Problema con bicicletas"], ["Bizikletak", "Abandonatutako bizikleta", "Bizikleten aparkalekua", "Bizikleten arazoa"], "street", "normal"),
S("Bidegorris", ["el bidegorri está ocupado por coches", "hay un tramo del carril bici en mal estado", "el carril bici queda cortado", "hay un obstáculo en el bidegorri", "la separación del carril bici no está bien colocada"],
 ["bidegorria autoek okupatzen dute", "bizikleta-bidearen zati bat egoera txarrean dago", "bizikleta-bidea moztuta dago", "oztopo bat dago bidegorrian", "bizikleta-bidearen bereizketa ez dago ondo jarrita"],
 ["Bidegorri", "Carril bici ocupado", "Problema en el carril bici", "Obstáculo en el bidegorri"], ["Bidegorria", "Okupatutako bidegorria", "Bizikleta-bideko arazoa", "Oztopoa bidegorrian"], "street", "normal"),
S("Transporte público", ["el autobús llega con mucho retraso", "la frecuencia es insuficiente", "el servicio se interrumpe con demasiada frecuencia", "el autobús va lleno y deja pasajeros en la parada", "hay un problema con el recorrido de la línea"],
 ["autobusa atzerapen handiarekin iristen da", "maiztasuna ez da nahikoa", "zerbitzua maiz eten egiten da", "autobusa beteta doa eta bidaiariak geltokian uzten ditu", "linearen ibilbidearekin arazo bat dago"],
 ["Transporte público", "Retraso del autobús", "Frecuencia del autobús", "Problema con una línea"], ["Garraio publikoa", "Autobusaren atzerapena", "Autobusaren maiztasuna", "Linearen arazoa"], "bus", "normal"),
S("Taxis", ["hay dificultades para encontrar taxi en esta zona", "un taxi se ha negado a realizar el servicio", "quiero informar de un problema con un taxi", "hay vehículos esperando en un lugar que dificulta la circulación", "necesito información sobre el servicio de taxi"],
 ["zaila da taxi bat aurkitzea eremu honetan", "taxi batek zerbitzua egiteari uko egin dio", "taxi batekin izandako arazo baten berri eman nahi dut", "ibilgailuak leku batean daude eta zirkulazioa oztopatzen dute", "taxi zerbitzuari buruzko informazioa behar dut"],
 ["Servicio de taxi", "Problema con un taxi", "Taxi en la zona", "Información sobre taxis"], ["Taxi zerbitzua", "Taxiarekin arazoa", "Taxia inguruan", "Taxiei buruzko informazioa"], "street", "normal"),
S("Zona de bajas emisiones", ["tengo dudas sobre las restricciones de acceso", "no sé si mi vehículo puede entrar en la zona", "la señalización de la zona de bajas emisiones no se entiende bien", "he recibido un aviso relacionado con el acceso", "quiero información sobre las condiciones de la zona"],
 ["sarbide-murrizketei buruzko zalantzak ditut", "ez dakit nire ibilgailua eremura sar daitekeen", "isurketa txikiko eremuaren seinaleztapena ez da ondo ulertzen", "sarrerarekin lotutako abisu bat jaso dut", "eremuaren baldintzei buruzko informazioa nahi dut"],
 ["Zona de bajas emisiones", "Restricciones de acceso", "Acceso de vehículos", "Dudas sobre ZBE"], ["Isurketa txikiko eremua", "Sarbide-murrizketak", "Ibilgailuen sarbidea", "ZBEri buruzko zalantzak"], "street", "normal"),
S("Señalización de tráfico", ["una señal está caída", "la señal de prohibido está tapada", "hay una señal que se contradice con otra", "la pintura de la calzada está prácticamente borrada", "falta una señal en un cruce", "la señalización resulta confusa"],
 ["seinale bat erorita dago", "debeku-seinalea estalita dago", "seinale batek beste batekin kontraesanean dago", "galtzadako pintura ia ezabatuta dago", "seinale bat falta da gurutzagune batean", "seinaleztapena nahasgarria da"],
 ["Señal de tráfico", "Señal caída", "Señalización confusa", "Pintura vial"], ["Trafiko seinalea", "Eroritako seinalea", "Seinaleztapen nahasgarria", "Bideko pintura"], "street", "high"),

S("Impuestos", ["tengo una duda sobre un impuesto municipal", "no entiendo cómo se calcula el impuesto", "quiero saber cuándo tengo que pagar", "creo que hay un error en el importe del impuesto", "necesito información sobre un impuesto"],
 ["udal-zerga bati buruzko zalantza dut", "ez dut ulertzen nola kalkulatzen den zerga", "noiz ordaindu behar dudan jakin nahi dut", "zerga-zenbatekoan akats bat dagoela uste dut", "zerga bati buruzko informazioa behar dut"],
 ["Consulta sobre impuestos", "Duda sobre un impuesto", "Importe de un impuesto", "Pago de impuestos"], ["Zergei buruzko kontsulta", "Zerga bati buruzko zalantza", "Zergaren zenbatekoa", "Zergen ordainketa"], "none", "normal"),
S("Tasas", ["quiero consultar una tasa municipal", "no sé qué tasa corresponde a este trámite", "no entiendo el importe de la tasa", "me han cobrado una tasa que no esperaba", "necesito saber cómo pagar una tasa"],
 ["udal-tasa bat kontsultatu nahi dut", "ez dakit zein tasa dagokion izapide honi", "ez dut tasaren zenbatekoa ulertzen", "espero ez nuen tasa bat kobratu didate", "tasa bat nola ordaindu jakin nahi dut"],
 ["Consulta de tasas", "Duda sobre una tasa", "Importe de una tasa", "Pago de una tasa"], ["Tasen kontsulta", "Tasa bati buruzko zalantza", "Tasaren zenbatekoa", "Tasa ordaintzea"], "none", "normal"),
S("Domiciliaciones", ["quiero cambiar una domiciliación", "la domiciliación no se ha realizado como esperaba", "necesito saber cómo domiciliar un recibo", "quiero dar de baja una domiciliación", "tengo un problema con una domiciliación bancaria"],
 ["helbideratze bat aldatu nahi dut", "helbideratzea ez da espero bezala egin", "ordainagiri bat nola helbideratu jakin nahi dut", "helbideratze bat baja eman nahi dut", "arazo bat daukat bankuko helbideratzearekin"],
 ["Domiciliación bancaria", "Problema con domiciliación", "Cambiar domiciliación", "Domiciliar un recibo"], ["Banku-helbideratzea", "Helbideratze arazoa", "Helbideratzea aldatu", "Ordainagiria helbideratu"], "none", "normal"),
S("Recibos", ["no me ha llegado un recibo", "quiero consultar un recibo municipal", "el importe del recibo no coincide con lo que esperaba", "me aparece un recibo pendiente", "necesito una copia de un recibo"],
 ["ez zait ordainagiririk iritsi", "udal-ordainagiri bat kontsultatu nahi dut", "ordainagiriaren zenbatekoa ez dator bat espero nuenarekin", "ordaindu gabeko ordainagiri bat agertzen zait", "ordainagiri baten kopia behar dut"],
 ["Recibo municipal", "Recibo pendiente", "Problema con un recibo", "Copia de un recibo"], ["Udal-ordainagiria", "Ordaindu gabeko ordainagiria", "Ordainagiriaren arazoa", "Ordainagiriaren kopia"], "none", "normal"),
S("Certificados", ["necesito un certificado municipal", "quiero saber cómo solicitar un certificado", "no consigo descargar el certificado", "el certificado que he recibido tiene un dato incorrecto", "necesito saber cuánto tarda el certificado"],
 ["udal-ziurtagiri bat behar dut", "ziurtagiri bat nola eskatu jakin nahi dut", "ezin dut ziurtagiria deskargatu", "jaso dudan ziurtagirian datu bat oker dago", "ziurtagiriak zenbat denbora behar duen jakin nahi dut"],
 ["Certificado municipal", "Solicitar certificado", "Problema con un certificado", "Descargar certificado"], ["Udal-ziurtagiria", "Ziurtagiria eskatu", "Ziurtagiriaren arazoa", "Ziurtagiria deskargatu"], "none", "normal"),
S("Pago online", ["no puedo completar un pago por internet", "la plataforma de pago da error", "el pago se queda bloqueado", "me han cobrado pero el trámite sigue pendiente", "no sé dónde realizar el pago online"],
 ["ezin dut ordainketa internet bidez amaitu", "ordainketa-plataformak errorea ematen du", "ordainketa blokeatuta geratzen da", "kobratu didate baina izapidea zain dago", "ez dakit non egin online ordainketa"],
 ["Pago online", "Error en el pago", "Problema con pago municipal", "Pago por internet"], ["Online ordainketa", "Errorea ordainketan", "Udal-ordainketaren arazoa", "Internet bidezko ordainketa"], "none", "normal"),
S("Multas", ["quiero consultar una multa", "no estoy de acuerdo con una multa y quiero información sobre el procedimiento", "necesito saber cómo pagar una multa", "me ha llegado una multa que no esperaba", "quiero consultar el estado de una multa"],
 ["isun bat kontsultatu nahi dut", "ez nago isun batekin ados eta prozedurari buruzko informazioa nahi dut", "isun bat nola ordaindu jakin nahi dut", "espero ez nuen isun bat iritsi zait", "isun baten egoera kontsultatu nahi dut"],
 ["Consulta de multa", "Multa municipal", "Pago de una multa", "Estado de una multa"], ["Isunaren kontsulta", "Udal-isuna", "Isuna ordaintzea", "Isunaren egoera"], "none", "normal"),

S("Comportamientos incívicos", ["dejan basura en la calle continuamente", "hay personas que orinan en el portal", "se producen actos incívicos de forma habitual", "rompen mobiliario durante la noche", "dejan restos y suciedad después de reunirse"],
 ["etengabe zaborra uzten dute kalean", "jendeak atarian pixa egiten du", "portaera zibikoen aurkako ekintzak maiz gertatzen dira", "gauez hiriko altzariak apurtzen dituzte", "bildu ondoren hondarrak eta zikinkeria uzten dituzte"],
 ["Comportamientos incívicos", "Problemas de convivencia", "Actos incívicos", "Molestias en la calle"], ["Jokabide zibikoen aurkakoak", "Bizikidetza arazoak", "Ekintza ez-zibikoak", "Kalean eragozpenak"], "street", "normal"),
S("Conductas sospechosas", ["hay personas que llevan varios días entrando y saliendo de un portal", "he visto movimientos que me parecen extraños", "hay una situación que me preocupa y no sé a quién avisar", "se observa actividad extraña en un local cerrado", "hay personas merodeando por la zona durante la noche"],
 ["pertsona batzuk hainbat egun daramatzate atari batean sartzen eta ateratzen", "mugimendu arraroak ikusi ditut", "kezkatzen nauen egoera bat dago eta ez dakit nori abisatu", "itxita dagoen lokal batean jarduera arraroa ikusten da", "gauez pertsonak inguruan bueltaka ikusten dira"],
 ["Situación sospechosa", "Conducta extraña", "Aviso a la Guardia", "Personas merodeando"], ["Egoera susmagarria", "Jokabide arraroa", "Udaltzaingoari abisua", "Pertsonak inguruan bueltaka"], "street", "high"),
S("Conductas delictivas", ["he presenciado un posible robo", "han forzado una puerta", "hay daños que parecen consecuencia de un acto delictivo", "he visto una pelea en la calle", "se ha producido una agresión", "han intentado entrar en un local"],
 ["balizko lapurreta bat ikusi dut", "ate bat indarrez ireki dute", "kalteak ekintza deliktibo baten ondorio direla dirudi", "kalean borroka bat ikusi dut", "eraso bat gertatu da", "lokal batean sartzen saiatu dira"],
 ["Posible robo", "Agresión", "Daños", "Incidente en la calle"], ["Balizko lapurreta", "Erasoa", "Kalteak", "Kalean gertatutako istilua"], "street", "high"),
S("Ruido / molestias", ["hay ruido constante por las noches", "un local genera molestias hasta altas horas", "los gritos en la calle son frecuentes", "la música se oye dentro de casa", "las molestias se repiten casi todos los fines de semana"],
 ["gauez etengabeko zarata dago", "lokal batek eragozpenak sortzen ditu ordu txikiak arte", "kalean oihuak maiz entzuten dira", "musika etxe barruan entzuten da", "eragozpenak ia asteburu guztietan errepikatzen dira"],
 ["Ruido y molestias", "Molestias nocturnas", "Problema de ruido", "Ruido de un local"], ["Zarata eta eragozpenak", "Gaueko eragozpenak", "Zarata arazoa", "Lokal baten zarata"], "street", "normal"),
S("Animales", ["hay un perro suelto de forma habitual", "se acumulan excrementos de perros", "hay animales que generan molestias", "he encontrado un animal herido", "hay un problema con animales en esta zona"],
 ["txakurra maiz solte ibiltzen da", "txakur-kakak pilatzen dira", "animaliek eragozpenak sortzen dituzte", "zauritutako animalia bat aurkitu dut", "inguru honetan animaliekin arazo bat dago"],
 ["Animales en la vía pública", "Perros sueltos", "Excrementos", "Animal herido"], ["Animaliak bide publikoan", "Txakur solteak", "Gorotzak", "Animalia zauritua"], "street", "normal"),
S("Asentamientos", ["hay personas viviendo de forma continuada en este lugar", "se ha instalado un asentamiento en una zona pública", "hay personas durmiendo habitualmente en la calle", "se han colocado enseres y estructuras en un espacio público", "la situación lleva varias semanas"],
 ["pertsonak etengabe leku honetan bizi dira", "asentamendu bat sortu da eremu publiko batean", "pertsonak kalean lo egiten ari dira maiz", "gauzak eta egiturak jarri dituzte espazio publiko batean", "egoerak hainbat aste daramatza"],
 ["Asentamiento", "Personas viviendo en la calle", "Situación en espacio público", "Asentamiento en la zona"], ["Asentamendua", "Kalean bizi diren pertsonak", "Egoera espazio publikoan", "Inguruko asentamendua"], "street", "normal"),
S("Ocupación indebida del espacio público", ["hay vehículos ocupando una zona reservada", "se ha cerrado una parte de la acera sin dejar paso", "han colocado objetos que impiden utilizar el espacio público", "una terraza ocupa más espacio del que debería", "hay elementos privados instalados en una zona de paso"],
 ["ibilgailuek erreserbatutako eremu bat okupatzen dute", "espaloiaren zati bat itxi dute pasabiderik utzi gabe", "objektuak jarri dituzte eta espazio publikoa erabiltzea eragozten dute", "terraza batek behar baino leku gehiago hartzen du", "elementu pribatuak jarri dituzte pasabidean"],
 ["Ocupación indebida", "Espacio público ocupado", "Acera ocupada", "Zona de paso bloqueada"], ["Bide publikoaren okupazio desegokia", "Okupatutako espazio publikoa", "Okupatutako espaloia", "Blokeatutako pasabidea"], "street", "normal"),

S("Ruido", ["se escucha un ruido continuo procedente de una instalación", "hay maquinaria que genera mucho ruido", "el nivel de ruido parece especialmente alto", "hay ruido nocturno procedente de una actividad", "el ruido afecta a las viviendas cercanas"],
 ["instalazio batetik etengabeko zarata entzuten da", "makineriak zarata handia sortzen du", "zarata maila bereziki handia dela dirudi", "jarduera batek gaueko zarata sortzen du", "zarata inguruko etxebizitzei eragiten die"],
 ["Ruido ambiental", "Nivel de ruido", "Ruido de una instalación", "Molestias acústicas"], ["Ingurumen-zarata", "Zarata-maila", "Instalazio baten zarata", "Zarata-eragozpenak"], "street", "normal"),
S("Malos olores", ["hay un olor muy fuerte en la calle", "desde hace días se nota un olor desagradable", "el olor parece proceder de una instalación", "hay malos olores cerca de los contenedores", "el problema aparece sobre todo por la noche"],
 ["kalean usain oso handia dago", "egun batzuetatik usain desatsegina nabaritzen da", "usaina instalazio batetik datorrela dirudi", "edukiontzien inguruan usain txarrak daude", "arazoa batez ere gauez agertzen da"],
 ["Malos olores", "Olor desagradable", "Problema de olores", "Olor en la calle"], ["Usain txarrak", "Usain desatsegina", "Usainen arazoa", "Usaina kalean"], "street", "normal"),
S("Vertidos", ["han vertido líquido en la vía pública", "hay una mancha que parece un vertido", "se ha detectado un vertido cerca de un río", "hay residuos líquidos en una zona verde", "el vertido desprende un olor fuerte"],
 ["likidoa isuri dute bide publikoan", "isurketa baten itxura duen orban bat dago", "ibai baten ondoan isurketa bat antzeman da", "hondakin likidoak daude berdegune batean", "isurketak usain handia du"],
 ["Vertido", "Vertido en la calle", "Problema ambiental", "Residuos líquidos"], ["Isurketa", "Isurketa kalean", "Ingurumen arazoa", "Hondakin likidoak"], "street", "high"),
S("Calidad del aire", ["hay mucho humo en la zona", "el aire huele a combustible", "se percibe contaminación especialmente a determinadas horas", "hay polvo en suspensión", "me preocupa la calidad del aire cerca de viviendas"],
 ["inguruan ke asko dago", "aireak erregai usaina du", "kutsadura nabari da batez ere ordu jakinetan", "hauts esekia dago", "etxebizitzen inguruko airearen kalitateak kezkatzen nau"],
 ["Calidad del aire", "Humo", "Contaminación del aire", "Problema de aire"], ["Airearen kalitatea", "Kea", "Airearen kutsadura", "Aire arazoa"], "street", "normal"),
S("Agua / saneamiento", ["hay agua saliendo de la calzada", "una alcantarilla rebosa cuando llueve", "hay una fuga de agua", "el agua se acumula continuamente", "hay un problema de saneamiento en la zona"],
 ["ura galtzadatik ateratzen da", "estolda gainezka egiten du euria egiten duenean", "ur-ihes bat dago", "ura etengabe pilatzen da", "saneamendu arazo bat dago inguruan"],
 ["Problema de agua", "Fuga de agua", "Saneamiento", "Alcantarillado"], ["Uraren arazoa", "Ur-ihesa", "Saneamendua", "Estolderia"], "street", "high"),

S("Obras en viviendas", ["se están realizando obras en una vivienda y tengo dudas sobre su legalidad", "una reforma está generando molestias", "han abierto un hueco en una fachada", "se están haciendo obras que afectan a elementos comunes", "quiero información sobre obras en una vivienda"],
 ["etxebizitza batean obrak egiten ari dira eta legezkotasunari buruzko zalantzak ditut", "eraberritze batek eragozpenak sortzen ditu", "fatxadan zulo bat ireki dute", "obra batzuek elementu komunetan eragiten dute", "etxebizitza bateko obrei buruzko informazioa nahi dut"],
 ["Obras en vivienda", "Reforma de vivienda", "Obras en una casa", "Problema con una reforma"], ["Etxebizitzako obrak", "Etxebizitza eraberritzea", "Etxe bateko obrak", "Eraberritzearen arazoa"], "street", "normal"),
S("Obras en edificios", ["se están haciendo obras en el edificio", "hay andamios que ocupan parte de la vía pública", "la fachada del edificio está siendo modificada", "las obras generan molestias", "quiero consultar una actuación en un edificio"],
 ["eraikinean obrak egiten ari dira", "aldamioek bide publikoaren zati bat okupatzen dute", "eraikinaren fatxada aldatzen ari dira", "obrek eragozpenak sortzen dituzte", "eraikin bateko jarduera bati buruzko kontsulta egin nahi dut"],
 ["Obras en edificio", "Andamios", "Obra en fachada", "Reforma de edificio"], ["Eraikineko obrak", "Aldamioak", "Fatxadako obra", "Eraikinaren eraberritzea"], "street", "normal"),
S("Licencias", ["quiero saber qué licencia necesito", "he presentado una solicitud y no sé en qué estado está", "necesito información sobre una licencia de obra", "tengo dudas sobre la documentación necesaria", "quiero consultar el estado de una licencia"],
 ["zein lizentzia behar dudan jakin nahi dut", "eskaera aurkeztu dut eta ez dakit zein egoeratan dagoen", "obra-lizentzia bati buruzko informazioa behar dut", "behar den dokumentazioari buruzko zalantzak ditut", "lizentzia baten egoera kontsultatu nahi dut"],
 ["Licencia municipal", "Solicitud de licencia", "Estado de una licencia", "Documentación para una licencia"], ["Udal-lizentzia", "Lizentzia-eskaera", "Lizentziaren egoera", "Lizentziarako dokumentazioa"], "none", "normal"),
S("Actividades comerciales", ["quiero consultar los requisitos para abrir un negocio", "tengo dudas sobre una actividad comercial", "un establecimiento ha iniciado una actividad y quiero información", "necesito saber qué autorización corresponde", "quiero información sobre los trámites para una actividad"],
 ["negozio bat irekitzeko baldintzak kontsultatu nahi ditut", "merkataritza-jarduera bati buruzko zalantzak ditut", "establezimendu batek jarduera hasi du eta informazioa nahi dut", "zein baimen dagokion jakin nahi dut", "jarduera baterako izapideei buruzko informazioa nahi dut"],
 ["Actividad comercial", "Abrir un negocio", "Autorización de actividad", "Trámites para un negocio"], ["Merkataritza-jarduera", "Negozio bat ireki", "Jardueraren baimena", "Negozio baterako izapideak"], "none", "normal"),
S("Locales", ["hay un local vacío en muy malas condiciones", "un local parece estar generando problemas en el edificio", "quiero consultar la situación de un local", "un establecimiento permanece cerrado y presenta desperfectos", "hay un local cuyo uso me genera dudas"],
 ["lokal huts bat oso egoera txarrean dago", "lokal batek eraikinean arazoak sortzen dituela dirudi", "lokal baten egoera kontsultatu nahi dut", "establezimendu bat itxita dago eta kalteak ditu", "lokal baten erabilerari buruzko zalantzak ditut"],
 ["Situación de un local", "Local vacío", "Problema en un local", "Estado de un establecimiento"], ["Lokal baten egoera", "Lokal hutsa", "Lokal bateko arazoa", "Establezimenduaren egoera"], "street", "normal"),
S("Disciplina urbanística", ["hay una obra que parece no tener autorización", "se ha cerrado una terraza de una forma que me parece irregular", "se ha construido un elemento que no parece permitido", "una obra no respeta aparentemente las condiciones", "quiero comunicar una posible infracción urbanística"],
 ["baimenik gabeko obra bat dagoela dirudi", "terrazari itxitura bat jarri diote eta irregularra dirudi", "baimenduta ez dagoela dirudien elementu bat eraiki dute", "obra batek baldintzak ez dituela betetzen dirudi", "hirigintza arau-hauste posible baten berri eman nahi dut"],
 ["Posible infracción urbanística", "Obra sin autorización", "Disciplina urbanística", "Construcción irregular"], ["Balizko hirigintza-haustea", "Baimenik gabeko obra", "Hirigintza-diziplina", "Eraikuntza irregularra"], "street", "normal"),
S("Vivienda", ["quiero información sobre vivienda municipal", "necesito saber cómo acceder a una vivienda protegida", "quiero consultar una ayuda relacionada con vivienda", "tengo dudas sobre un trámite de vivienda", "necesito información sobre el parque de vivienda"],
 ["udal-etxebizitzari buruzko informazioa nahi dut", "babestutako etxebizitza batera nola iritsi jakin nahi dut", "etxebizitzarekin lotutako laguntza bat kontsultatu nahi dut", "etxebizitza-izapide bati buruzko zalantzak ditut", "etxebizitza-parke bati buruzko informazioa behar dut"],
 ["Información de vivienda", "Vivienda municipal", "Vivienda protegida", "Trámite de vivienda"], ["Etxebizitzari buruzko informazioa", "Udal-etxebizitza", "Babestutako etxebizitza", "Etxebizitza-izapidea"], "none", "normal"),

S("Obras municipales", ["hay una obra municipal que parece parada", "las obras están generando mucho ruido", "quiero información sobre una obra que se está realizando", "la obra ha dejado restos en la zona", "el acceso se ha visto afectado por las obras"],
 ["udal obra bat geldirik dagoela dirudi", "obrek zarata handia sortzen dute", "egiten ari diren obra bati buruzko informazioa nahi dut", "obrak hondarrak utzi ditu inguruan", "obren ondorioz sarbidea aldatu da"],
 ["Obra municipal", "Estado de una obra", "Molestias por obras", "Obra parada"], ["Udal-obra", "Obra baten egoera", "Obren eragozpenak", "Obra geldirik"], "street", "normal"),
S("Obras en vía pública", ["han cortado la calle por unas obras", "hay vallas que dificultan el paso", "las obras han dejado un tramo de acera inutilizable", "se ha abierto una zanja en la calzada", "la señalización de las obras no está clara"],
 ["obra batzuengatik kalea moztu dute", "hesiek pasatzea zailtzen dute", "obren ondorioz espaloi zati bat ezin da erabili", "zanga bat ireki dute galtzadan", "obren seinaleztapena ez dago argi"],
 ["Obras en la calle", "Calle cortada", "Vallas de obra", "Zanja en la calzada"], ["Kalean obrak", "Kalea moztuta", "Obrako hesiak", "Zanga galtzadan"], "street", "high"),
S("Proyectos urbanos", ["quiero información sobre un proyecto urbanístico de la zona", "me gustaría saber en qué fase está el proyecto", "el proyecto previsto afecta a esta calle", "quiero consultar los planes para esta zona", "tengo dudas sobre una actuación urbana prevista"],
 ["inguruko hiri-proiektu bati buruzko informazioa nahi dut", "proiektua zein fasetan dagoen jakin nahi nuke", "aurreikusitako proiektuak kale honi eragiten dio", "eremu honetarako planak kontsultatu nahi ditut", "aurreikusitako hiri-jarduerari buruzko zalantzak ditut"],
 ["Proyecto urbano", "Actuación prevista", "Plan para la zona", "Proyecto de la ciudad"], ["Hiri-proiektua", "Aurreikusitako jarduera", "Eremurako plana", "Hiriko proiektua"], "landmark", "normal"),
S("Infraestructuras", ["hay un problema con una infraestructura pública", "una estructura presenta daños", "un paso elevado necesita revisión", "hay un elemento de infraestructura deteriorado", "quiero comunicar un problema en una infraestructura"],
 ["azpiegitura publiko batekin arazo bat dago", "egitura batek kalteak ditu", "pasabide batek berrikuspena behar du", "azpiegitura-elementu bat hondatuta dago", "azpiegitura batean arazo baten berri eman nahi dut"],
 ["Infraestructura pública", "Estructura deteriorada", "Problema en infraestructura", "Revisión de infraestructura"], ["Azpiegitura publikoa", "Hondatutako egitura", "Azpiegitura arazoa", "Azpiegitura berrikustea"], "landmark", "high"),

S("Ayudas sociales", ["quiero información sobre una ayuda social", "necesito saber qué ayudas puedo solicitar", "quiero consultar los requisitos de una ayuda", "he solicitado una ayuda y quiero saber su estado", "necesito orientación para solicitar una ayuda"],
 ["gizarte-laguntza bati buruzko informazioa nahi dut", "zein laguntza eska ditzakedan jakin nahi dut", "laguntza baten baldintzak kontsultatu nahi ditut", "laguntza bat eskatu dut eta egoera jakin nahi dut", "laguntza bat eskatzeko orientazioa behar dut"],
 ["Ayuda social", "Solicitud de ayuda", "Requisitos de una ayuda", "Estado de una ayuda"], ["Gizarte-laguntza", "Laguntza-eskaera", "Laguntzaren baldintzak", "Laguntzaren egoera"], "none", "normal"),
S("Atención social", ["necesito hablar con servicios sociales", "quiero pedir una cita de atención social", "no sé dónde acudir para una situación familiar", "necesito orientación sobre un problema social", "quiero información sobre atención social"],
 ["gizarte-zerbitzuekin hitz egin behar dut", "gizarte-arretarako hitzordua eskatu nahi dut", "ez dakit nora jo familia-egoera baten aurrean", "gizarte arazo bati buruzko orientazioa behar dut", "gizarte-arretari buruzko informazioa nahi dut"],
 ["Atención social", "Cita con servicios sociales", "Orientación social", "Consulta social"], ["Gizarte-arreta", "Gizarte-zerbitzuetako hitzordua", "Gizarte-orientazioa", "Gizarte-kontsulta"], "none", "normal"),
S("Personas mayores", ["quiero información sobre recursos para personas mayores", "necesito ayuda para una persona mayor", "quiero consultar un servicio para mayores", "una persona mayor necesita orientación", "quiero saber qué actividades hay para personas mayores"],
 ["adinekoentzako baliabideei buruzko informazioa nahi dut", "adineko pertsona batentzat laguntza behar dut", "adinekoentzako zerbitzu bat kontsultatu nahi dut", "adineko pertsona batek orientazioa behar du", "adinekoentzako zer jarduera dauden jakin nahi dut"],
 ["Personas mayores", "Ayuda para una persona mayor", "Servicios para mayores", "Recursos para mayores"], ["Adineko pertsonak", "Adineko pertsona batentzako laguntza", "Adinekoentzako zerbitzuak", "Adinekoentzako baliabideak"], "none", "normal"),
S("Personas en situación de vulnerabilidad", ["necesito ayuda por una situación económica complicada", "una familia necesita apoyo", "no puedo hacer frente a algunos gastos básicos", "necesito saber qué recursos existen para una situación de vulnerabilidad", "quiero pedir orientación porque mi situación ha empeorado"],
 ["egoera ekonomiko zaila dela eta laguntza behar dut", "familia batek laguntza behar du", "ezin ditut oinarrizko gastu batzuk ordaindu", "zaurgarritasun egoerarako zein baliabide dauden jakin nahi dut", "egoerak okerrera egin duelako orientazioa eskatu nahi dut"],
 ["Situación de vulnerabilidad", "Necesidad de apoyo", "Ayuda para una familia", "Recursos sociales"], ["Zaurgarritasun egoera", "Laguntza beharra", "Familia batentzako laguntza", "Gizarte-baliabideak"], "none", "high"),
S("Servicios sociales", ["quiero saber qué servicios sociales ofrece el Ayuntamiento", "no sé qué recurso corresponde a mi situación", "quiero información sobre los servicios disponibles", "necesito saber dónde acudir", "quiero consultar un servicio social municipal"],
 ["Udalak zer gizarte-zerbitzu eskaintzen dituen jakin nahi dut", "ez dakit zein baliabide dagokion nire egoerari", "eskuragarri dauden zerbitzuei buruzko informazioa nahi dut", "nora jo behar dudan jakin behar dut", "udaleko gizarte-zerbitzu bat kontsultatu nahi dut"],
 ["Servicios sociales", "Recursos sociales", "Información social", "Servicio municipal"], ["Gizarte-zerbitzuak", "Gizarte-baliabideak", "Gizarte-informazioa", "Udal-zerbitzua"], "none", "normal"),

S("Centros educativos", ["hay un problema en un centro educativo", "quiero comunicar una incidencia en un colegio", "el acceso al centro presenta problemas", "hay una deficiencia en las instalaciones del centro", "quiero información sobre un centro educativo municipal"],
 ["hezkuntza-zentro batean arazo bat dago", "ikastetxe batean gertakari baten berri eman nahi dut", "zentroko sarbideak arazoak ditu", "zentroko instalazioetan gabezia bat dago", "udaleko hezkuntza-zentro bati buruzko informazioa nahi dut"],
 ["Centro educativo", "Problema en un colegio", "Incidencia en un centro", "Instalaciones educativas"], ["Hezkuntza-zentroa", "Ikastetxeko arazoa", "Zentroko gertakaria", "Hezkuntza-instalazioak"], "landmark", "normal"),
S("Actividades educativas", ["quiero información sobre actividades educativas", "hay una actividad escolar que me interesa", "quiero saber cómo apuntar a un menor a una actividad", "no encuentro información sobre una actividad educativa", "quiero consultar horarios de una actividad"],
 ["hezkuntza-jarduerei buruzko informazioa nahi dut", "interesatzen zaidan eskola-jarduera bat dago", "adingabe bat jarduera batean nola apuntatu jakin nahi dut", "ez dut hezkuntza-jarduera bati buruzko informaziorik aurkitzen", "jarduera baten ordutegiak kontsultatu nahi ditut"],
 ["Actividad educativa", "Actividades para menores", "Información educativa", "Inscripción a una actividad"], ["Hezkuntza-jarduera", "Adingabeentzako jarduerak", "Hezkuntza-informazioa", "Jardueran izena ematea"], "none", "normal"),
S("Programas educativos", ["quiero información sobre un programa educativo municipal", "no sé cuándo empieza el programa", "quiero saber quién puede participar", "necesito información sobre la inscripción", "me gustaría conocer los programas disponibles"],
 ["udaleko hezkuntza-programa bati buruzko informazioa nahi dut", "ez dakit programa noiz hasten den", "nork parte har dezakeen jakin nahi dut", "izena emateari buruzko informazioa behar dut", "eskuragarri dauden programak ezagutu nahi ditut"],
 ["Programa educativo", "Programa municipal", "Inscripción a un programa", "Información de programas"], ["Hezkuntza-programa", "Udal-programa", "Programan izena ematea", "Programei buruzko informazioa"], "none", "normal"),

S("Instalaciones deportivas", ["hay un problema en una instalación deportiva", "una instalación no está funcionando correctamente", "quiero consultar el horario de una instalación", "el acceso a una instalación deportiva está cerrado", "hay un problema de mantenimiento en la instalación"],
 ["kirol-instalazio batean arazo bat dago", "instalazio batek ez du behar bezala funtzionatzen", "instalazio baten ordutegia kontsultatu nahi dut", "kirol-instalaziorako sarbidea itxita dago", "instalazioak mantentze-arazo bat du"],
 ["Instalación deportiva", "Problema en una instalación", "Horario deportivo", "Acceso a instalación"], ["Kirol-instalazioa", "Instalazioko arazoa", "Kirol-ordutegia", "Instalaziorako sarbidea"], "landmark", "normal"),
S("Equipamientos deportivos", ["una pista deportiva está en mal estado", "hay material deportivo deteriorado", "falta equipamiento en una instalación", "una canasta está rota", "las duchas del polideportivo no funcionan"],
 ["kirol-pista bat egoera txarrean dago", "kirol-materiala hondatuta dago", "instalazio batean ekipamendua falta da", "saskibaloiko saskia apurtuta dago", "kiroldegiko dutxek ez dute funtzionatzen"],
 ["Equipamiento deportivo", "Pista deportiva", "Material deportivo", "Duchas del polideportivo"], ["Kirol-ekipamendua", "Kirol-pista", "Kirol-materiala", "Kiroldegiko dutxak"], "landmark", "normal"),
S("Actividades deportivas", ["quiero información sobre actividades deportivas", "quiero apuntarme a una actividad", "no encuentro los horarios de una actividad", "una actividad ha cambiado de horario", "quiero saber qué actividades hay para adultos"],
 ["kirol-jarduerei buruzko informazioa nahi dut", "jarduera batean izena eman nahi dut", "ez ditut jarduera baten ordutegiak aurkitzen", "jarduera batek ordutegia aldatu du", "helduentzako zer jarduera dauden jakin nahi dut"],
 ["Actividad deportiva", "Inscripción deportiva", "Horarios deportivos", "Actividades para adultos"], ["Kirol-jarduera", "Kirol-izenematea", "Kirol-ordutegiak", "Helduentzako jarduerak"], "none", "normal"),
S("Cursos deportivos", ["quiero información sobre un curso deportivo", "no sé cómo inscribirme en el curso", "quiero consultar las plazas disponibles", "el curso que me interesa aparece completo", "necesito saber cuándo comienza el curso"],
 ["kirol-ikastaro bati buruzko informazioa nahi dut", "ez dakit ikastaroan nola eman izena", "eskuragarri dauden plazak kontsultatu nahi ditut", "interesatzen zaidan ikastaroa beteta dago", "ikastaroa noiz hasten den jakin behar dut"],
 ["Curso deportivo", "Inscripción a curso", "Plazas de un curso", "Inicio del curso"], ["Kirol-ikastaroa", "Ikastaroan izena ematea", "Ikastaroaren plazak", "Ikastaroaren hasiera"], "none", "normal"),

S("Actividades culturales", ["quiero información sobre una actividad cultural", "no encuentro cómo reservar para una actividad", "quiero saber qué actividades hay este mes", "una actividad ha cambiado de horario", "necesito información sobre una actividad cultural municipal"],
 ["kultura-jarduera bati buruzko informazioa nahi dut", "ez dut aurkitzen jarduera baterako erreserba nola egin", "hil honetan zer jarduera dauden jakin nahi dut", "jarduera batek ordutegia aldatu du", "udaleko kultura-jarduera bati buruzko informazioa behar dut"],
 ["Actividad cultural", "Reserva cultural", "Agenda cultural", "Actividad municipal"], ["Kultura-jarduera", "Kultura-erreserba", "Kultura-agenda", "Udal-jarduera"], "landmark", "normal"),
S("Equipamientos culturales", ["hay un problema en un equipamiento cultural", "quiero consultar el horario de un centro cultural", "el acceso al equipamiento está cerrado", "hay una incidencia en las instalaciones", "necesito información sobre un espacio cultural"],
 ["kultura-ekipamendu batean arazo bat dago", "kultura-zentro baten ordutegia kontsultatu nahi dut", "ekipamendurako sarbidea itxita dago", "instalazioetan gertakari bat dago", "kultura-espazio bati buruzko informazioa behar dut"],
 ["Equipamiento cultural", "Centro cultural", "Horario cultural", "Incidencia en instalaciones"], ["Kultura-ekipamendua", "Kultura-zentroa", "Kultura-ordutegia", "Instalazioetako gertakaria"], "landmark", "normal"),
S("San Telmo", ["quiero información sobre el Museo San Telmo", "tengo una duda sobre una actividad de San Telmo", "quiero consultar horarios y entradas de San Telmo", "hay un problema con la visita", "quiero saber qué exposiciones hay"],
 ["San Telmo Museoari buruzko informazioa nahi dut", "San Telmoko jarduera bati buruzko zalantza dut", "San Telmoko ordutegiak eta sarrerak kontsultatu nahi ditut", "bisitarekin arazo bat dago", "zer erakusketa dauden jakin nahi dut"],
 ["San Telmo", "Museo San Telmo", "Actividad en San Telmo", "Visita a San Telmo"], ["San Telmo", "San Telmo Museoa", "San Telmoko jarduera", "San Telmora bisita"], "landmark", "normal"),
S("Victoria Eugenia", ["quiero información sobre una función en el Victoria Eugenia", "tengo una duda sobre las entradas", "quiero consultar la programación", "hay un problema con mi reserva", "quiero saber el horario de una función"],
 ["Victoria Eugenian emanaldi bati buruzko informazioa nahi dut", "sarrerei buruzko zalantza dut", "programazioa kontsultatu nahi dut", "arazo bat dago nire erreserbarekin", "emanaldi baten ordutegia jakin nahi dut"],
 ["Victoria Eugenia", "Función en el teatro", "Entradas", "Programación"], ["Victoria Eugenia", "Antzokiko emanaldia", "Sarrerak", "Programazioa"], "landmark", "normal"),

S("Euskera en servicios municipales", ["quiero ser atendido en euskera", "en una oficina municipal no me han podido atender en euskera", "una comunicación municipal me ha llegado solo en castellano", "quiero saber si este servicio está disponible en euskera", "necesito realizar un trámite en euskera"],
 ["euskaraz artatua izan nahi dut", "udal-bulego batean ezin izan didate euskaraz artatu", "udaleko komunikazio bat gaztelaniaz bakarrik iritsi zait", "zerbitzu hau euskaraz erabilgarri dagoen jakin nahi dut", "izapide bat euskaraz egin behar dut"],
 ["Atención en euskera", "Servicio municipal en euskera", "Trámite en euskera", "Uso del euskera"], ["Euskarazko arreta", "Udal-zerbitzua euskaraz", "Euskarazko izapidea", "Euskararen erabilera"], "none", "normal"),
S("Política lingüística", ["quiero consultar una cuestión relacionada con la política lingüística", "tengo una duda sobre el uso de las lenguas en el Ayuntamiento", "quiero información sobre las medidas de euskera", "quiero saber qué normativa lingüística se aplica", "me gustaría consultar el plan de euskera"],
 ["hizkuntza-politikari lotutako gai bat kontsultatu nahi dut", "Udalean hizkuntzen erabilerari buruzko zalantza dut", "euskararen neurriei buruzko informazioa nahi dut", "zein hizkuntza-araudi aplikatzen den jakin nahi dut", "euskararen plana kontsultatu nahi nuke"],
 ["Política lingüística", "Uso de las lenguas", "Medidas de euskera", "Normativa lingüística"], ["Hizkuntza-politika", "Hizkuntzen erabilera", "Euskararen neurriak", "Hizkuntza-araudia"], "none", "normal"),
S("Traducciones / atención lingüística", ["necesito una traducción de un documento municipal", "hay información que no está disponible en euskera", "quiero solicitar atención lingüística", "una traducción contiene un error", "necesito ayuda para entender una comunicación municipal"],
 ["udal-dokumentu baten itzulpena behar dut", "informazioa ez dago euskaraz eskuragarri", "hizkuntza-arreta eskatu nahi dut", "itzulpen batek akats bat du", "udal-komunikazio bat ulertzeko laguntza behar dut"],
 ["Traducción", "Atención lingüística", "Documento en euskera", "Error de traducción"], ["Itzulpena", "Hizkuntza-arreta", "Euskarazko dokumentua", "Itzulpen-akatsa"], "none", "normal"),

S("Información turística", ["necesito información para visitar la ciudad", "quiero saber dónde está la oficina de turismo", "busco un plano de la ciudad", "quiero recomendaciones de lugares que visitar", "necesito información turística de Donostia"],
 ["hiria bisitatzeko informazioa behar dut", "turismo bulegoa non dagoen jakin nahi dut", "hiriko mapa baten bila nabil", "bisitatzeko lekuen gomendioak nahi ditut", "Donostiari buruzko turismo-informazioa behar dut"],
 ["Información turística", "Oficina de turismo", "Mapa de la ciudad", "Visitar Donostia"], ["Turismo-informazioa", "Turismo bulegoa", "Hiriko mapa", "Donostia bisitatzea"], "landmark", "normal"),
S("Turismo en la ciudad", ["quiero información sobre zonas turísticas", "me gustaría saber cómo llegar a los principales puntos de interés", "quiero conocer la oferta turística de la ciudad", "necesito información para organizar una visita", "busco información sobre los barrios y lugares de interés"],
 ["turismo-eremuei buruzko informazioa nahi dut", "interesgune nagusietara nola iritsi jakin nahi dut", "hiriko turismo-eskaintza ezagutu nahi dut", "bisita bat antolatzeko informazioa behar dut", "auzoei eta interesguneei buruzko informazioa bilatzen dut"],
 ["Turismo en Donostia", "Lugares de interés", "Oferta turística", "Visita a la ciudad"], ["Donostiako turismoa", "Interesguneak", "Turismo-eskaintza", "Hirira bisita"], "landmark", "normal"),
S("Actividades turísticas", ["quiero información sobre visitas guiadas", "me gustaría apuntarme a una actividad turística", "quiero saber qué actividades hay esta semana", "busco una visita relacionada con la gastronomía", "quiero consultar horarios de una actividad turística"],
 ["bisita gidatuei buruzko informazioa nahi dut", "turismo-jarduera batean izena eman nahi dut", "aste honetan zer jarduera dauden jakin nahi dut", "gastronomiarekin lotutako bisita baten bila nabil", "turismo-jarduera baten ordutegiak kontsultatu nahi ditut"],
 ["Actividad turística", "Visita guiada", "Actividad gastronómica", "Agenda turística"], ["Turismo-jarduera", "Bisita gidatua", "Jarduera gastronomikoa", "Turismo-agenda"], "landmark", "normal"),

S("Autobuses urbanos", ["la línea de autobús no está funcionando como debería", "el autobús pasa con retraso", "quiero información sobre una línea", "el recorrido de la línea ha cambiado y no lo entiendo", "hay demasiada gente y no cabemos en el autobús", "el autobús no ha pasado"],
 ["autobus-lineak ez du behar bezala funtzionatzen", "autobusa atzerapenarekin pasatzen da", "linea bati buruzko informazioa nahi dut", "linearen ibilbidea aldatu da eta ez dut ulertzen", "jende gehiegi dago eta ez gara autobusean sartzen", "autobusa ez da pasa"],
 ["Autobús urbano", "Problema con una línea", "Autobús con retraso", "Recorrido de autobús"], ["Hiri-autobusa", "Linearen arazoa", "Autobusaren atzerapena", "Autobusaren ibilbidea"], "bus", "normal"),
S("Paradas de autobús", ["la marquesina está rota", "en la parada no aparece correctamente la información", "la parada está ocupada por vehículos", "la pantalla de información no funciona", "la parada no está bien señalizada", "han movido la parada y no encuentro información"],
 ["markesina apurtuta dago", "geltokian informazioa ez da behar bezala agertzen", "geltokia ibilgailuek okupatzen dute", "informazio-pantailak ez du funtzionatzen", "geltokia ez dago behar bezala seinaleztatuta", "geltokia aldatu dute eta ez dut informaziorik aurkitzen"],
 ["Parada de autobús", "Marquesina rota", "Información de la parada", "Pantalla de la parada"], ["Autobus-geltokia", "Markesina apurtua", "Geltokiko informazioa", "Geltokiko pantaila"], "bus", "normal"),
]

for spec in SPECS:
    # A continuación se asignan por nombre dentro de cada categoría;
    # "Plagas" aparece en dos categorías y necesita dos ground truths distintos.
    pass

# Verificación fuerte de cobertura.
ALL_SUBCATS = [sub for group in TAXONOMY.values() for sub in group]
# Para subcategorías repetidas en la taxonomía, se reutiliza el núcleo semántico
# pero se mantiene la clave completa categoría/subcategoría.
for group, subs in TAXONOMY.items():
    for subcat in subs:
        candidates = [x for x in SPECS if x.key == subcat]
        if not candidates:
            raise RuntimeError(f"Falta escenario para {group} / {subcat}")
        SCENARIOS[(group, subcat)] = candidates[0]

missing = [(g, s) for g, subs in TAXONOMY.items() for s in subs if (g, s) not in SCENARIOS]
if missing:
    raise RuntimeError(f"Cobertura de taxonomía incorrecta. Faltan={missing}")

# ---------------------------------------------------------------------------
# 5) GENERACIÓN DE CONTEXTO
# ---------------------------------------------------------------------------

@dataclass
class Context:
    lang: str
    barrio_es: str
    barrio: str
    street: str
    place: str
    number: int
    time: str
    line: str
    stop: str
    location_text: str
    vague_location: bool


def pick(rng, xs):
    return xs[rng.randrange(len(xs))]


def make_context(spec: Spec, lang: str, rng: random.Random) -> Context:
    barrio_es = pick(rng, BARRIOS_ES)
    barrio = barrio_es if lang == "es" else BARRIOS_EU[barrio_es]
    street = pick(rng, STREETS_ES if lang == "es" else STREETS_EU)
    place = pick(rng, PLACES)
    number = rng.randint(2, 128)
    time = pick(rng, TIME_ES if lang == "es" else TIME_EU)
    line = pick(rng, DBUS_LINES)
    stop = pick(rng, BUS_STOPS)

    if spec.loc == "none":
        loc_kind = rng.choices(["none", "barrio", "vague"], weights=[45,45,10], k=1)[0]
    elif spec.loc == "bus":
        loc_kind = rng.choices(["stop", "line", "street_stop", "none", "vague"], weights=[30,20,20,20,10], k=1)[0]
    elif spec.loc == "beach":
        loc_kind = rng.choices(["beach", "landmark", "barrio", "vague"], weights=[40,20,30,10], k=1)[0]
    elif spec.loc == "park":
        loc_kind = rng.choices(["park", "barrio", "street", "vague"], weights=[40,30,20,10], k=1)[0]
    elif spec.loc == "landmark":
        loc_kind = rng.choices(["landmark", "street", "barrio", "vague"], weights=[35,25,30,10], k=1)[0]
    else:
        loc_kind = rng.choices(["street", "street_number", "street_barrio", "barrio", "landmark", "none", "vague"], weights=[25,15,20,20,10,5,5], k=1)[0]

    if lang == "es":
        if loc_kind == "street": location_text = f"en {street}"
        elif loc_kind == "street_number": location_text = f"a la altura del número {number} de {street}"
        elif loc_kind == "street_barrio": location_text = f"en {street}, en {barrio_es}"
        elif loc_kind == "barrio": location_text = f"por {barrio_es}"
        elif loc_kind == "landmark": location_text = f"cerca de {place}"
        elif loc_kind == "park": location_text = f"en {place}"
        elif loc_kind == "beach": location_text = f"en {pick(rng, ['la Concha','Ondarreta','Zurriola'])}"
        elif loc_kind == "stop": location_text = f"en la parada de {stop}"
        elif loc_kind == "line": location_text = f"en la línea {line}"
        elif loc_kind == "street_stop": location_text = f"en la parada de {stop}, en {street}"
        elif loc_kind == "vague": location_text = pick(rng, ["por la zona", "cerca de aquí", "en mi barrio", "por esa zona", "en la zona indicada"])
        else: location_text = ""
    else:
        if loc_kind == "street": location_text = f"{street}(n)"
        elif loc_kind == "street_number": location_text = f"{street}(n), {number}. zenbakian"
        elif loc_kind == "street_barrio": location_text = f"{street}(n), {barrio}n"
        elif loc_kind == "barrio": location_text = f"{barrio} inguruan"
        elif loc_kind == "landmark": location_text = f"{place}ren ondoan"
        elif loc_kind == "park": location_text = f"{place}(e)n"
        elif loc_kind == "beach": location_text = f"{pick(rng, ['Kontxan','Ondarreta hondartzan','Zurriolan'])}"
        elif loc_kind == "stop": location_text = f"{stop} geltokian"
        elif loc_kind == "line": location_text = f"{line} linean"
        elif loc_kind == "street_stop": location_text = f"{stop} geltokian, {street}(n)"
        elif loc_kind == "vague": location_text = pick(rng, ["inguru honetan", "nire auzoan", "eremu horretan", "zonaldean", "hemen inguruan"])
        else: location_text = ""

    return Context(lang, barrio_es, barrio, street, place, number, time, line, stop, location_text, loc_kind == "vague")

# ---------------------------------------------------------------------------
# 6) PLANTILLAS DE REDACCIÓN: NO concatenan simplemente frases; reconstruyen
#    un correo según perfil y contexto.
# ---------------------------------------------------------------------------

PROFILES = [
    ("formal", .10), ("normal", .34), ("breve", .12), ("informal", .10),
    ("molesto", .09), ("verbose", .10), ("typo", .06), ("desordenado", .05),
    ("vago", .04),
]


def weighted_choice(rng, pairs):
    total = sum(w for _, w in pairs)
    x = rng.random() * total
    acc = 0
    for item, w in pairs:
        acc += w
        if x <= acc:
            return item
    return pairs[-1][0]


def inject_location(text: str, ctx: Context, rng: random.Random, lang: str) -> str:
    if not ctx.location_text:
        return text
    # No se mete siempre en el mismo punto.
    if lang == "es":
        forms = [
            f" {ctx.location_text}",
            f"; es {ctx.location_text}",
            f". La zona es {ctx.location_text}",
            f". Ocurre {ctx.location_text}",
        ]
    else:
        forms = [
            f" {ctx.location_text}",
            f"; {ctx.location_text} da", 
            f". Eremua: {ctx.location_text}",
            f". Han gertatzen da: {ctx.location_text}",
        ]
    # Con cierta probabilidad no se explicita la ubicación, incluso si existe.
    if rng.random() < .08:
        return text
    return text + pick(rng, forms)


def naturalize(text: str, lang: str, profile: str, rng: random.Random, informational: bool = False) -> str:
    # Variación de puntuación / formato, sin destruir el contenido semántico.
    text = re.sub(r"\s+", " ", text).strip()
    if profile == "brief":
        pass
    if profile == "typo":
        if lang == "es":
            swaps = [("porque", "porq"), ("también", "tmb"), ("que", "q"), ("por favor", "porfavor")]
        else:
            swaps = [("mesedez", "mesedez"), ("badago", "badago"), ("eta", "ta")]
        if rng.random() < .65:
            a, b = pick(rng, swaps)
            text = text.replace(a, b, 1)
        if rng.random() < .25:
            text = text.lower()
    elif profile == "informal":
        text = text.replace("Buenos días", "Hola").replace("Buenas tardes", "Hola")
        text = text.replace("Les agradecería", "A ver si podéis").replace("Gracias de antemano", "Gracias")
    elif profile == "molesto":
        if informational:
            if lang == "es":
                prefixes = ["Llevo un rato intentando encontrar esta información. ", "No consigo aclararlo por otra vía. "]
            else:
                prefixes = ["Denbora daramat informazio hau aurkitu nahian. ", "Ezin dut beste bide batetik argitu. "]
        else:
            if lang == "es":
                prefixes = ["Llevo días avisando de esto. ", "Ya no sé a quién avisar. ", "La situación empieza a ser bastante molesta. "]
            else:
                prefixes = ["Egunak daramatzat honen berri ematen. ", "Ez dakit nori gehiago esan. ", "Egoera nahiko gogaikarria izaten ari da. "]
        text = pick(rng, prefixes) + text
    elif profile == "desordenado":
        parts = re.split(r"(?<=[.!?])\s+", text)
        if len(parts) >= 3:
            rng.shuffle(parts)
            text = " ".join(parts)
    elif profile == "vago":
        # Mantener un mínimo de señal semántica.
        if lang == "es":
            text += pick(rng, [" No sé si esto corresponde aquí.", " No tengo más datos ahora mismo."])
        else:
            text += pick(rng, [" Ez dakit hemen dagokion.", " Oraingoz ez daukat datu gehiagorik."])
    elif profile == "verbose":
        if informational:
            if lang == "es":
                text += pick(rng, [" Si necesitan algún dato más, puedo facilitarlo.", "Lo pregunto porque no encuentro una respuesta clara en la información disponible."])
            else:
                text += pick(rng, ["Beste daturen bat behar baduzue, eman dezaket.", "Hala galdetzen dut, ez dudalako informazio argirik aurkitzen."])
        else:
            if lang == "es":
                text += pick(rng, [" Lo comento porque es una zona por la que paso a diario y cada vez lo veo peor.", "Lo he visto en varias ocasiones y por eso prefiero avisar antes de que vaya a más."])
            else:
                text += pick(rng, ["Egunero pasatzen naiz handik eta gero eta okerrago ikusten dut.", "Hainbat aldiz ikusi dut eta horregatik abisatzea nahiago dut."])
    text = re.sub(r"([.!?])(?=[A-ZÁÉÍÓÚÜÑ]|[¿¡])", r"\1 ", text)
    text = re.sub(r"(?<=[a-záéíóúüñçàèìòùäëïöü])(?=[A-ZÁÉÍÓÚÜÑ])", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


GENERIC_SUBJECTS_ES = [
    "Hola", "Consulta", "Problema", "Incidencia", "Aviso", "Una consulta",
    "Información", "Ayuda", "Pregunta", "Solicitud", "Buenas",
]
GENERIC_SUBJECTS_EU = [
    "Kaixo", "Kontsulta", "Arazoa", "Abisua", "Informazioa", "Laguntza",
    "Galdera", "Eskaera", "Mesedez",
]

def choose_subject(spec: Spec, lang: str, rng: random.Random) -> str:
    """Realistic subject distribution: 60% absent, 15% generic, 15% normal, 10% specific."""
    r = rng.random()
    if r < 0.60:
        return ""
    if r < 0.75:
        pool = GENERIC_SUBJECTS_ES if lang == "es" else GENERIC_SUBJECTS_EU
        return pick(rng, pool)
    # Existing scenario subjects contain the domain-specific but still natural variants.
    pool = spec.subjects_es if lang == "es" else spec.subjects_eu
    return pick(rng, pool)

def make_email(spec: Spec, rng: random.Random) -> Tuple[str, str, Dict[str, object]]:
    lang = "es" if rng.random() < .50 else "eu"
    ctx = make_context(spec, lang, rng)
    profile = weighted_choice(rng, PROFILES)

    if lang == "es":
        issue = pick(rng, spec.es)
        subject = choose_subject(spec, "es", rng)
        opener = pick(rng, OPENERS_ES)
        closer = pick(rng, CLOSERS_ES)
        formal = pick(rng, FORMAL_ES)
        time = ctx.time
        informational = bool(re.search(r"\b(quiero|necesito|tengo una duda|me gustaría|busco|no sé|consultar|información)\b", issue, re.I))
        loc = ctx.location_text
        if informational:
            variants = [
                f"{opener}: {issue}{(' ' + loc) if loc else ''}.",
                f"{opener}. {issue.capitalize()}{(' ' + loc) if loc else ''}. ¿Podrían indicarme cómo proceder?",
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. No encuentro información clara y agradecería que me orientaran.",
                f"{issue.capitalize()}{(' ' + loc) if loc else ''}. {pick(rng, ['¿Podrían decirme dónde tengo que hacer la gestión?', '¿Me pueden indicar dónde consultarlo?', 'Agradecería que me informaran sobre los pasos a seguir.'])}",
                f"{opener}. {issue.capitalize()}{(' ' + loc) if loc else ''}. {formal}",
            ]
        else:
            variants = [
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. Lo he visto {time}.",
                f"{opener}. Quería avisar de que {issue}{(' ' + loc) if loc else ''}. {pick(rng, ['¿Podrían revisarlo?', '¿Podéis echarle un vistazo?', 'A ver si se puede solucionar.'])}",
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. No sé desde cuándo está así, pero {pick(rng, ['cada vez se nota más', 'está dificultando bastante el paso', 'me preocupa que vaya a más'])}.",
                f"{issue.capitalize()}{(' ' + loc) if loc else ''}. {pick(rng, ['Lo comento porque pasa bastante gente por ahí.', 'Aviso porque lo veo todos los días.', 'Creo que convendría revisarlo antes de que provoque un accidente.'])}",
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. {formal}",
            ]
        body = pick(rng, variants)
        if profile == "formal": body += " " + formal
        elif profile == "brief":
            prefix = f"{subject}. " if subject else ""
            body = f"{prefix}{issue.capitalize()}{(' ' + loc) if loc else ''}."
        else: body += " " + closer
    else:
        issue = pick(rng, spec.eu)
        subject = choose_subject(spec, "eu", rng)
        opener = pick(rng, OPENERS_EU)
        closer = pick(rng, CLOSERS_EU)
        formal = pick(rng, FORMAL_EU)
        time = ctx.time
        informational = bool(re.search(r"\b(nahi dut|nahi nuke|behar dut|zalantza dut|kontsultatu|informazioa|jakin nahi|ez dakit)\b", issue, re.I))
        loc = ctx.location_text
        if informational:
            variants = [
                f"{opener}: {issue}{(' ' + loc) if loc else ''}.",
                f"{opener}. {issue.capitalize()}{(' ' + loc) if loc else ''}. Nola egin behar dudan adieraziko didazue?",
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. Ez dut informazio argirik aurkitzen eta orientazioa eskertuko nuke.",
                f"{issue.capitalize()}{(' ' + loc) if loc else ''}. {pick(rng, ['Non egin behar dudan izapidea adieraziko didazue?', 'Non kontsulta dezakedan esango didazue?', 'Jarraitu beharreko pausoak adieraztea eskertuko nuke.'])}",
                f"{opener}. {issue.capitalize()}{(' ' + loc) if loc else ''}. {formal}",
            ]
        else:
            variants = [
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. {pick(rng, ['Ikusi dut', 'Topatu dut', 'Gertatzen ari da'])} {time}.",
                f"{opener}. Jakinarazi nahi dizuet {issue}{(' ' + loc) if loc else ''}. {pick(rng, ['Berrikusi ahal duzue?', 'Begiratu ahal badiozue?', 'Ea konpontzen den.'])}",
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. Ez dakit noiztik dagoen horrela, baina {pick(rng, ['gero eta nabarmenagoa da', 'pasabidea asko zailtzen du', 'kezkatzen nau okerrera egiteak'])}.",
                f"{issue.capitalize()}{(' ' + loc) if loc else ''}. {pick(rng, ['Horren berri ematen dut, jende asko pasatzen delako handik.', 'Abisatzen dut, egunero ikusten dudalako.', 'Berrikustea komeni dela uste dut, istripuren bat eragin baitezake.'])}",
                f"{opener}: {issue}{(' ' + loc) if loc else ''}. {formal}",
            ]
        body = pick(rng, variants)
        if profile == "formal": body += " " + formal
        elif profile == "brief":
            prefix = f"{subject}. " if subject else ""
            body = f"{prefix}{issue.capitalize()}{(' ' + loc) if loc else ''}."
        else: body += " " + closer

    body = naturalize(body, lang, profile, rng, informational)
    if rng.random() < .12:
        subject = subject.lower()

    text = f"Asunto: {subject}\n\n{body}" if subject else body
    ambiguous = profile in {"vago", "desordenado"} or ctx.vague_location or rng.random() < .03
    multi = rng.random() < .03
    if multi:
        if lang == "es":
            text += " Además, hay otra cosa en la misma zona que también convendría revisar."
        else:
            text += " Gainera, beste gauza bat ere badago inguru berean eta berrikustea komeniko litzateke."
        ambiguous = True

    # La zona solo se etiqueta cuando el barrio aparece explícitamente en el correo.
    zone = ctx.barrio if any(k in (ctx.location_text or "") for k in [ctx.barrio, ctx.barrio_es]) and not ctx.vague_location else "Desconocida"

    return text, subject, {
        "idioma": "castellano" if lang == "es" else "euskera",
        "perfil_escritura": profile,
        "es_ambiguo": bool(ambiguous),
        "tiene_multiples_incidencias": bool(multi),
        "zona_generada": zone,
        "barrio_referenciado": ctx.barrio if zone != "Desconocida" else "",
        "familia_escenario": spec.key,
    }

# ---------------------------------------------------------------------------
# 7) METADATOS Y SPLIT
# ---------------------------------------------------------------------------

def stable_int(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:16], 16)


def split_for(subcat: str, scenario_variant: int) -> str:
    # Cada subcategoría aparece en train/val/test, pero algunas familias de
    # escenario quedan reservadas para evaluar generalización estructural.
    r = scenario_variant % 6
    return "train" if r in (0,1,2,3) else ("validation" if r == 4 else "test")


def make_record(i: int, rng: random.Random) -> Dict[str, object]:
    group = pick(rng, list(TAXONOMY))
    subcat = pick(rng, list(TAXONOMY[group]))
    spec = SCENARIOS[(group, subcat)]
    text, subject, aux = make_email(spec, rng)
    # variant family is independent of exact generated wording.
    variant = stable_int(f"{subcat}|{aux['perfil_escritura']}|{i % 6}") % 6
    gestor = TAXONOMY[group][subcat]
    zona = aux["zona_generada"]
    # El texto no contiene estos labels como metadata estructurada.
    # Para que el JOIN por texto sea inequívoco, las subcategorías que aparecen
    # bajo más de una categoría reciben un nombre contextual en la salida.
    # Internamente se mantiene la taxonomía original para no alterar la generación.
    subcat_salida = subcat
    if subcat == "Plagas":
        contexto = "Limpieza y residuos" if group == "LIMPIEZA Y RESIDUOS" else "Medio ambiente"
        subcat_salida = f"Plagas - {contexto}"

    return {
        "email_id": f"donostia_{i:07d}",
        "texto": text,
        "asunto": subject,
        "cuerpo": text.split("\n\n", 1)[1] if "\n\n" in text else text,
        "categoria": group,
        "subcategoria": subcat_salida,
        "gestor_principal": gestor.split(" / ")[0],
        "gestor_secundario": " / ".join(gestor.split(" / ")[1:]) or "",
        "zona": zona,
        "idioma": aux["idioma"],
        "perfil_escritura": aux["perfil_escritura"],
        "es_ambiguo": aux["es_ambiguo"],
        "tiene_multiples_incidencias": aux["tiene_multiples_incidencias"],
        "familia_escenario": aux["familia_escenario"],
        "split": split_for(subcat, variant),
    }


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"[^\wáéíóúüñçàèìòùäëïöü\s#]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def generate(n: int, seed: int = 20260925) -> List[Dict[str, object]]:
    rng = random.Random(seed)
    records: List[Dict[str, object]] = []
    fingerprints = set()
    attempts = 0
    max_attempts = max(n * 4, 1000)
    while len(records) < n and attempts < max_attempts:
        attempts += 1
        rec = make_record(len(records), rng)
        fp = normalize(rec["texto"])
        if fp in fingerprints:
            continue
        fingerprints.add(fp)
        records.append(rec)
    if len(records) < n:
        raise RuntimeError(f"Solo se pudieron generar {len(records)} de {n} registros.")
    return records


def write_outputs(records: List[Dict[str, object]], outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fields = list(records[0].keys())
    with (outdir / "dataset.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # CSV principal: una fila física por email y SIN duplicar el correo.
    # `texto` ya contiene asunto + cuerpo, por lo que `asunto` y `cuerpo` no
    # se incluyen aquí. Se conservan en dataset.jsonl para QA.
    table_fields = [
        "email_id", "texto", "subcategoria",
        "gestor_principal", "gestor_secundario", "zona", "idioma",
        "perfil_escritura", "es_ambiguo", "tiene_multiples_incidencias",
        "familia_escenario", "split"
    ]
    with (outdir / "dataset.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=table_fields, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in records:
            rr = {k: r[k] for k in table_fields}
            for k, v in rr.items():
                if isinstance(v, str):
                    rr[k] = re.sub(r"\s*\n\s*", " ", v).strip()
            w.writerow(rr)

    # Tabla auxiliar para el JOIN del proyecto: cada subcategoría de salida
    # identifica una única categoría. No se usan IDs artificiales.
    auxiliary = {}
    for group, subs in TAXONOMY.items():
        for subcat in subs:
            subcat_salida = subcat
            if subcat == "Plagas":
                contexto = "Limpieza y residuos" if group == "LIMPIEZA Y RESIDUOS" else "Medio ambiente"
                subcat_salida = f"Plagas - {contexto}"
            if subcat_salida in auxiliary and auxiliary[subcat_salida] != group:
                raise RuntimeError(f"Subcategoría ambigua en la tabla auxiliar: {subcat_salida}")
            auxiliary[subcat_salida] = group

    with (outdir / "categorias_auxiliar.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["categoria", "subcategoria"], quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for subcat_salida, group in sorted(auxiliary.items(), key=lambda x: (x[1], x[0])):
            w.writerow({"categoria": group, "subcategoria": subcat_salida})

    # Versión de entrenamiento: SOLO texto + labels. No idioma, no perfil, no ID.
    train_fields = ["texto", "subcategoria", "gestor_principal", "gestor_secundario", "zona"]
    with (outdir / "dataset_modelo.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({k:r[k] for k in train_fields}, ensure_ascii=False) + "\n")

    # CSV de entrenamiento: una casilla por campo y una fila por email.
    # Es el archivo recomendado para abrir como tabla y entrenar/inspeccionar.
    with (outdir / "dataset_modelo.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=train_fields, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in records:
            rr = {k: re.sub(r"\s*\n\s*", " ", str(r[k])).strip() if isinstance(r[k], str) else r[k] for k in train_fields}
            w.writerow(rr)

    # Split físicamente separado para evitar mezclar train/validation/test.
    for split in ("train", "validation", "test"):
        with (outdir / f"{split}.jsonl").open("w", encoding="utf-8") as f:
            for r in records:
                if r["split"] == split:
                    f.write(json.dumps({k:r[k] for k in train_fields}, ensure_ascii=False) + "\n")

    summary = {
        "n": len(records),
        "categorias": Counter(r["categoria"] for r in records),
        "subcategorias": Counter(r["subcategoria"] for r in records),
        "idioma": Counter(r["idioma"] for r in records),
        "split": Counter(r["split"] for r in records),
        "ambiguedad": Counter(r["es_ambiguo"] for r in records),
        "multiples_incidencias": Counter(r["tiene_multiples_incidencias"] for r in records),
    }
    with (outdir / "resumen_qa.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=dict)

    # Muestra reproducible para auditoría humana.
    rng = random.Random(12345)
    sample = rng.sample(records, min(100, len(records)))
    with (outdir / "muestra_qa_100.json").open("w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)


def validate(records: List[Dict[str, object]]) -> Dict[str, object]:
    norm = [normalize(r["texto"]) for r in records]
    dup = len(norm) - len(set(norm))
    def output_subcategory(group: str, subcat: str) -> str:
        if subcat == "Plagas":
            contexto = "Limpieza y residuos" if group == "LIMPIEZA Y RESIDUOS" else "Medio ambiente"
            return f"Plagas - {contexto}"
        return subcat

    expected = {(g, output_subcategory(g, s)) for g, subs in TAXONOMY.items() for s in subs}
    observed = {(r["categoria"], r["subcategoria"]) for r in records}
    missing = sorted(expected - observed)
    bad_text_labels = 0
    # Solo buscamos fugas de etiquetas de categoría administrativa completas.
    # Palabras como "ruido", "contenedor" o "licencia" son vocabulario natural
    # y NO deben considerarse leakage.
    leakage_terms = set(TAXONOMY)
    for r in records:
        t = r["texto"].lower()
        if any(re.search(r"\b" + re.escape(term.lower()) + r"\b", t) for term in leakage_terms):
            bad_text_labels += 1
    subcat_to_categories = defaultdict(set)
    for group, subs in TAXONOMY.items():
        for subcat in subs:
            subcat_salida = subcat
            if subcat == "Plagas":
                contexto = "Limpieza y residuos" if group == "LIMPIEZA Y RESIDUOS" else "Medio ambiente"
                subcat_salida = f"Plagas - {contexto}"
            subcat_to_categories[subcat_salida].add(group)
    ambiguous_auxiliary = {k: sorted(v) for k, v in subcat_to_categories.items() if len(v) > 1}

    return {
        "duplicados_normalizados": dup,
        "pares_categoria_subcategoria_observados": len(observed),
        "pares_categoria_subcategoria_totales": len(expected),
        "pares_categoria_subcategoria_faltantes": missing,
        "subcategorias_auxiliar": len(subcat_to_categories),
        "subcategorias_auxiliar_ambiguas": ambiguous_auxiliary,
        "posibles_fugas_de_etiqueta": bad_text_labels,
        "idioma_castellano": sum(r["idioma"] == "castellano" for r in records),
        "idioma_euskera": sum(r["idioma"] == "euskera" for r in records),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=10000)
    p.add_argument("--seed", type=int, default=20260925)
    p.add_argument("--out", type=Path, default=Path("dataset_donostia_v3"))
    args = p.parse_args()
    if args.n <= 0:
        raise SystemExit("--n debe ser > 0")

    records = generate(args.n, args.seed)
    qa = validate(records)
    write_outputs(records, args.out)
    with (args.out / "qa_global.json").open("w", encoding="utf-8") as f:
        json.dump(qa, f, ensure_ascii=False, indent=2)

    print(f"Generados: {len(records):,}")
    print(f"Pares categoría/subcategoría cubiertos: {qa['pares_categoria_subcategoria_observados']}/{qa['pares_categoria_subcategoria_totales']}")
    print(f"Duplicados normalizados: {qa['duplicados_normalizados']}")
    print(f"Posibles fugas de etiqueta: {qa['posibles_fugas_de_etiqueta']}")
    print(f"Castellano: {qa['idioma_castellano']:,} | Euskera: {qa['idioma_euskera']:,}")
    print(f"Salida: {args.out.resolve()}")


if __name__ == "__main__":
    main()
