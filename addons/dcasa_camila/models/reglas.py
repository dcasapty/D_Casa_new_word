"""Las reglas fijas de Camila (funciones puras, sin base de datos: se prueban sin Odoo).

* **La revisión de marca** (``problemas``): lo que escribe la IA (y lo que edita una persona) no lleva cifras ni
  precios (los pone Odoo), ni «remate», ni «¡¡», ni gritos en mayúsculas, ni el trato de usted, ni descuentos u
  ofertas que nadie aprobó, ni superlativos («el mejor de Panamá»), ni llaves o etiquetas (Resend lee
  ``{{{…}}}`` como un dato del contacto).
* **Los textos fijos**: lo que queda si la IA falla o escribe algo que no pasa la revisión. El equipo los edita.
* **La marca de la campaña** en el enlace de WhatsApp («Ref. DCN-0007»): así Odoo sabe que ese chat vino del correo.
* **El permiso que dio a Sofía**: solo cuenta si el mensaje que de verdad se le mandó decía para qué era (promociones).
"""
import json
import re
import unicodedata
from datetime import timedelta

# Decisión de la dueña (2026-11-06): una campaña cada 15 días como mucho. El tope lo pone el servidor.
DIAS_ENTRE_CAMPANAS = 15
PRODUCTOS_POR_CAMPANA = 6
MAX_PRODUCTOS = 8
MAX_ASUNTO = 70
MAX_ENTRADA = 300
MAX_LINEA = 140

GRUPOS = [
    ('nuevo', 'Lo nuevo'),
    ('vendido', 'De lo más vendido'),
    ('quieto', 'Lo que no se mueve'),
    ('tienda', 'En tienda'),
    ('elegido', 'Lo eligió una persona'),
]

PREFIJO_MARCA = 'DCN'
_MARCA = re.compile(r'\bDCN[\s-]?0*(\d{1,7})\b', re.IGNORECASE)

# Lo que se queda si la IA no responde o no pasa la revisión. Con la voz de la marca, sin cifras.
ASUNTO_FIJO = "Lo que hay en D'CASA esta quincena"
ENTRADA_FIJA = ('Te contamos lo que tenemos en la tienda estos días. Si algo te gusta, escríbenos por WhatsApp y te '
                'ayudamos con medidas, colores y la entrega.')
LINEAS_FIJAS = {
    'nuevo': 'Recién llegado a la tienda.',
    'vendido': 'De lo que más se están llevando.',
    'quieto': 'Disponible en tienda, listo para tu casa.',
    'tienda': 'Disponible en tienda.',
    'elegido': 'Disponible en tienda.',
}


def sin_tildes(texto):
    descompuesto = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in descompuesto if not unicodedata.combining(c))


def normal(texto):
    """Minúsculas, sin tildes y con un solo espacio (para comparar)."""
    return ' '.join(sin_tildes(texto).lower().split())


def limpiar(texto, maximo=None):
    """Un texto de una línea o párrafo: sin caracteres de control, sin llaves ni etiquetas y con un solo espacio."""
    texto = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in str(texto or ''))
    texto = texto.replace('{', '(').replace('}', ')').replace('<', '').replace('>', '')
    texto = ' '.join(texto.split()).strip()
    return texto[:maximo].rstrip() if maximo else texto


# ----------------------------------------------------------------------
# La revisión de marca
# ----------------------------------------------------------------------

_CIFRAS = re.compile(r'\d|%|\$|\bb/\.|\bpor ciento\b|\bdolares?\b|\bbalboas?\b')
_REMATE = re.compile(r'\bremat')
_EXCLAMACIONES = re.compile(r'¡¡|!!|¿¿|\?\?')
_GRITO = re.compile(r"\b[A-ZÁÉÍÓÚÜÑ]{4,}\b")
_USTED = re.compile(
    r'\b(usted|ustedes|visitenos|escribanos|contactenos|llamenos|aproveche|descubra|conozca|venga|disfrute|'
    r'adquiera|compre|renueve|le esperamos|los esperamos|les esperamos|lo esperamos|la esperamos|su hogar|su casa|'
    r'sus espacios)\b')
_OFERTAS = re.compile(r'\b(descuentos?|rebajas?|rebajad[oa]s?|ofertas?|gratis|liquidacion|2x1|precio especial)\b')
_SUPERLATIVOS = re.compile(
    r'\b(el mejor|la mejor|los mejores|las mejores|numero uno|n[o°º]\.? ?1|mas vendid[oa]s? de|unic[oa]s? en panama|'
    r'garantizad[oa]s?)\b')
_PROHIBIDO_LITERAL = ('{', '}', '<', '>')


def problemas(texto, maximo=None):
    """Lo que no pasa la revisión de marca, en palabras sencillas (lista vacía si todo está bien)."""
    texto = str(texto or '')
    if not texto.strip():
        return ['Está vacío.']
    salida = []
    simple = normal(texto)
    if _CIFRAS.search(simple):
        salida.append('Sin cifras ni precios: los precios los pone Odoo, del día.')
    if _REMATE.search(simple):
        salida.append('Sin «remate».')
    if _EXCLAMACIONES.search(texto):
        salida.append('Sin «¡¡» ni signos repetidos.')
    if _GRITO.search(texto.replace("D'CASA", '').replace('D’CASA', '')):
        salida.append('Sin palabras en mayúsculas (se lee como un grito).')
    if _USTED.search(simple):
        salida.append('De tú, no de usted.')
    if _OFERTAS.search(simple):
        salida.append('Sin descuentos, ofertas ni «gratis»: esta campaña no trae ninguno aprobado.')
    if _SUPERLATIVOS.search(simple):
        salida.append('Sin «el mejor» ni promesas que no se pueden comprobar.')
    if any(c in texto for c in _PROHIBIDO_LITERAL):
        salida.append('Sin llaves { } ni etiquetas < >.')
    if maximo and len(texto) > maximo:
        salida.append(f'Muy largo: máximo {maximo} letras.')
    return salida


# ----------------------------------------------------------------------
# Textos fijos y lo que contesta la IA
# ----------------------------------------------------------------------

def linea_fija(grupo):
    return LINEAS_FIJAS.get(grupo) or LINEAS_FIJAS['tienda']


def leer_json(texto):
    """El primer objeto JSON del texto que devolvió la IA (puede venir con ```json … ``` alrededor), o ``{}``."""
    texto = str(texto or '')
    inicio, fin = texto.find('{'), texto.rfind('}')
    if inicio < 0 or fin <= inicio:
        return {}
    try:
        datos = json.loads(texto[inicio:fin + 1])
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def elegir_texto(propuesto, fijo, maximo):
    """``(texto, de_la_ia)``: lo que propuso la IA si pasa la revisión; si no, el fijo."""
    candidato = limpiar(propuesto, None) if isinstance(propuesto, str) else ''
    if candidato and not problemas(candidato, maximo):
        return candidato, True
    return fijo, False


# ----------------------------------------------------------------------
# La marca de la campaña (para saber qué chats vinieron del correo)
# ----------------------------------------------------------------------

def marca(campana_id):
    return f'{PREFIJO_MARCA}-{int(campana_id):04d}'


def campana_de_la_marca(texto):
    """El número de campaña de la primera marca «DCN-0007» del texto, o ``None``."""
    encontrada = _MARCA.search(texto or '')
    return int(encontrada.group(1)) if encontrada else None


def texto_whatsapp(campana_id):
    """El mensaje que llega escrito al WhatsApp de la tienda cuando el cliente toca el botón del correo."""
    return f"Hola D'CASA, vi el correo de novedades y me interesa. (Ref. {marca(campana_id)})"


# ----------------------------------------------------------------------
# El tope de 15 días (en días de Panamá)
# ----------------------------------------------------------------------

def proxima_fecha(ultima_fecha):
    """El primer día (de Panamá) en que puede salir otra campaña, o ``None`` si nunca salió ninguna."""
    return ultima_fecha + timedelta(days=DIAS_ENTRE_CAMPANAS) if ultima_fecha else None


def puede_salir_hoy(hoy, ultima_fecha):
    proxima = proxima_fecha(ultima_fecha)
    return proxima is None or hoy >= proxima


# ----------------------------------------------------------------------
# El permiso que dio a Sofía
# ----------------------------------------------------------------------

def menciona_promociones(texto):
    """¿El mensaje que se le mandó decía que su correo era para avisarle de promociones? (Gerencia puede cambiar el
    texto de Sofía: solo cuenta si el que salió de verdad lo decía)."""
    return 'promocion' in normal(texto)
