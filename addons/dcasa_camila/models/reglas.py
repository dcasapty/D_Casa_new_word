"""Las reglas fijas de Camila (funciones puras, sin base de datos: se prueban sin Odoo).

* **La revisión de marca** (``problemas``): lo que escribe la IA (y lo que edita una persona) no lleva cifras ni
  precios (los pone Odoo), ni números en letras («dos por uno», «seis personas»), ni «remate», ni «¡¡», ni gritos en
  mayúsculas, ni el trato de usted, ni descuentos, ofertas, beneficios o prisas que nadie aprobó («sin costo», «te
  regalamos», «cuotas sin intereses», «garantía de por vida», «últimos días»), ni superlativos («el mejor de
  Panamá»), ni letras de otro alfabeto (una «e» cirílica en «remate»), ni llaves o etiquetas (Resend lee ``{{{…}}}``
  como un dato del contacto). ``limpiar`` QUITA los caracteres invisibles antes de revisar: un espacio de ancho cero
  dentro de «remate» no lo convierte en «re mate».
* **Los textos fijos**: lo que queda si la IA falla o escribe algo que no pasa la revisión. El equipo los edita.
* **La marca de la campaña** en el enlace de WhatsApp («Ref. DCN-0007»): así Odoo sabe que ese chat vino del correo.
* **El permiso que dio a Sofía**: solo cuenta si el mensaje que de verdad se le mandó tenía la frase de la plantilla
  («te avisamos de promociones», sin negar) y le pedía el correo.
"""
import json
import re
import unicodedata
from datetime import timedelta

# Decisión de la dueña (2026-11-06, etapa 2): a un mismo cliente (por correo) le llega como mucho UN correo de campaña
# cada 15 días. Puede haber varias campañas para grupos distintos; el tope es por cliente y lo pone el servidor.
DIAS_ENTRE_CAMPANAS = 15
PRODUCTOS_POR_CAMPANA = 6
MAX_PRODUCTOS = 8
MAX_ASUNTO = 70
MAX_ENTRADA = 300
MAX_LINEA = 140
MAX_IDEA = 400

GRUPOS = [
    ('nuevo', 'Lo nuevo'),
    ('vendido', 'De lo más vendido'),
    ('quieto', 'Lo que no se mueve'),
    ('stock', 'De lo que más hay'),
    ('movimiento', 'De lo que más se mueve'),
    ('tienda', 'En tienda'),
    ('elegido', 'Lo eligió una persona'),
]

# De dónde sale una campaña nueva («Nueva campaña» y el tablero de Marketing).
TEMAS = [
    ('mezcla', 'Lo nuevo, lo más vendido y lo quieto'),
    ('idea', 'Desde una idea'),
    ('nuevo', 'Lo nuevo'),
    ('vendidos', 'Los más vendidos'),
    ('quietos', 'Los más quietos'),
    ('stock', 'Lo que más hay en stock'),
    ('movimiento', 'Lo de mayor movimiento'),
    ('blanco', 'En blanco'),
]
GRUPO_DEL_TEMA = {'nuevo': 'nuevo', 'vendidos': 'vendido', 'quietos': 'quieto', 'stock': 'stock',
                  'movimiento': 'movimiento'}
# A quién va (etapa 2): se combinan (cualquiera de los elegidos) y siempre se cruzan con el permiso, la baja y el tope
# por cliente. «todos» son todos los que tienen permiso.
CHIPS = [
    ('todos', 'Todos con permiso'),
    ('compraron', 'Compraron en los últimos 90 días'),
    ('volver', 'Compraron hace más de 6 meses'),
    ('cotizaron', 'Cotizaron o preguntaron y no compraron'),
    ('tibios', 'Tibios del CRM'),
    ('calientes', 'Calientes del CRM'),
    ('nuevos', 'Recién agregados (30 días)'),
    ('antiguos', 'Clientes de hace más de un año'),
]
CHIPS_VALIDOS = frozenset(clave for clave, _nombre in CHIPS)


def leer_chips(valor):
    """La lista de chips válidos (en el orden de ``CHIPS``) de un texto «a,b» o una lista; vacío = «todos»."""
    if isinstance(valor, str):
        partes = valor.split(',')
    elif isinstance(valor, (list, tuple)):
        partes = [p for p in valor if isinstance(p, str)]
    else:
        partes = []
    elegidos = {p.strip() for p in partes if p.strip() in CHIPS_VALIDOS}
    return [clave for clave, _nombre in CHIPS if clave in elegidos] or ['todos']

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
    """Un texto de una línea o párrafo: sin caracteres de control, sin llaves ni etiquetas y con un solo espacio.

    Primero NFKC (las letras «anchas» y los superíndices pasan a las de siempre: «²» es un «2»). Los espacios y saltos
    de línea quedan como un espacio; cualquier otro carácter invisible o de control (ancho cero, guion suave, marcas de
    dirección) se QUITA sin dejar espacio: «re\\u200bmate» queda «remate» y la revisión lo ve."""
    texto = unicodedata.normalize('NFKC', str(texto or ''))
    texto = ''.join(' ' if c.isspace() else c for c in texto
                    if c.isspace() or not unicodedata.category(c).startswith('C'))
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
# Números en letras (sin «un», «uno» ni «una», que están en cualquier frase; «quincena» no es «quince»).
_NUMEROS = re.compile(
    r'\b(cero|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieci\w+|veinte|'
    r'veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|cientos?|doscient\w+|trescient\w+|'
    r'cuatrocient\w+|quinient\w+|seiscient\w+|setecient\w+|ochocient\w+|novecient\w+|mil|miles|millon\w*|'
    r'docenas?|mitad|medio precio)\b')
# Beneficios, facilidades y prisas que ninguna campaña trae aprobados (la IA tiende a inventarlos).
_BENEFICIOS = re.compile(
    r'\b(sin costos?|sin cargos?|sin recargos?|te regal\w*|regal(o|os|amos|an)|obsequi\w*|de cortesia|cuotas?|'
    r'sin intereses?|intereses?|financ\w*|creditos?|a plazos|pagos? (comodos?|faciles?|mensuales?)|garantias?|'
    r'de por vida|envios? (gratis|incluidos?)|instalacion (gratis|incluida)|precios? de fabrica|mas barat\w*|'
    r'baratisim\w*|ahorr\w*|liquidacion\w*|promocion\w*|aprovech\w*|ultim[oa]s (dias|unidades|piezas|horas)|'
    r'por tiempo limitado|solo (hoy|por hoy|esta semana)|hasta agotar\w*|se acab\w*)\b')
_SUPERLATIVOS = re.compile(
    r'\b(el mejor|la mejor|los mejores|las mejores|numero uno|n[o°º]\.? ?1|mas vendid[oa]s? de|unic[oa]s? en panama|'
    r'garantizad[oa]s?)\b')
_PROHIBIDO_LITERAL = ('{', '}', '<', '>')
# Lo que se busca en el texto en minúsculas y sin tildes, con lo que se le dice a la persona.
_REVISION_SIMPLE = (
    (_CIFRAS, 'Sin cifras ni precios: los precios los pone Odoo, del día.'),
    (_NUMEROS, 'Sin números en letras («dos por uno», «seis personas», «mitad de precio»).'),
    (_REMATE, 'Sin «remate».'),
    (_USTED, 'De tú, no de usted.'),
    (_OFERTAS, 'Sin descuentos, ofertas ni «gratis»: esta campaña no trae ninguno aprobado.'),
    (_BENEFICIOS, 'Sin beneficios ni prisas que nadie aprobó (sin costo, regalos, cuotas, garantías, «últimos días»).'),
    (_SUPERLATIVOS, 'Sin «el mejor» ni promesas que no se pueden comprobar.'),
)


def _letra_no_latina(c):
    return c.isalpha() and not unicodedata.name(c, '').startswith('LATIN')


def _invisible(c):
    return unicodedata.category(c).startswith('C') and not c.isspace()


def problemas(texto, maximo=None):
    """Lo que no pasa la revisión de marca, en palabras sencillas (lista vacía si todo está bien)."""
    texto = unicodedata.normalize('NFKC', str(texto or ''))
    if not texto.strip():
        return ['Está vacío.']
    simple = normal(texto)
    salida = [mensaje for patron, mensaje in _REVISION_SIMPLE if patron.search(simple)]
    if any(_letra_no_latina(c) for c in texto):
        salida.append('Solo letras del español: hay letras de otro alfabeto.')
    if any(_invisible(c) for c in texto):
        salida.append('Tiene caracteres invisibles.')
    if _EXCLAMACIONES.search(texto):
        salida.append('Sin «¡¡» ni signos repetidos.')
    if _GRITO.search(texto.replace("D'CASA", '').replace('D’CASA', '')):
        salida.append('Sin palabras en mayúsculas (se lee como un grito).')
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
    """El mensaje que llega escrito al WhatsApp de la tienda cuando el cliente toca el botón del correo: que suene a
    persona (decisión de la dueña, etapa 2), con la marca entre paréntesis para que Odoo sepa de qué campaña vino."""
    return f"Hola, vi el correo de novedades de D'CASA y me interesa ({marca(campana_id)})"


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

# La frase de la plantilla de Sofía (``dcasa_sofia/data/plantillas.xml``): «… ¿me regalas tu correo? Así te avisamos de
# promociones, …». Sin ella (o negada) el mensaje no dice para qué es el correo.
_FRASE_PROMOCIONES = re.compile(r'(?<!\bno )(?<!\bnunca )\bte avisamos de promociones\b')
_PIDE_CORREO = re.compile(r'\btu correo\b')


def pide_correo_para_promociones(texto):
    """¿El mensaje que se le mandó le pedía el correo Y decía, con la frase de la plantilla, que era para avisarle de
    promociones? Gerencia puede cambiar el texto de Sofía y la vendedora editarlo: solo cuenta si el que salió de verdad
    lo decía. «No es para promociones» o una promoción en otro mensaje no cuentan."""
    simple = normal(texto)
    return bool(_FRASE_PROMOCIONES.search(simple) and _PIDE_CORREO.search(simple))
