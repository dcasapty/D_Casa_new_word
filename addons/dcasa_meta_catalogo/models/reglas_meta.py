"""Reglas puras del catálogo para Meta: sin ORM ni base de datos, cada una se prueba sola.

El contrato con dcasa_meta_eventos (el píxel y la Conversions API) está en docs/META_CATALOGO.md:
el ``id`` de una fila es ``str(product.product.id)`` y nada más. Aquí solo vive cómo se escribe cada
celda: etiquetas en ASCII, franjas de precio, nivel de existencias, textos y precios.
"""
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from lxml import etree, html

LARGO_ETIQUETA = 100      # Meta: custom_label_0..4 hasta 100 caracteres
LARGO_TITULO = 150        # diseño: title hasta 150 caracteres (Meta acepta 200 y recomienda menos)
LARGO_DESCRIPCION = 5000  # diseño: description hasta 5,000 caracteres

# Los mismos cortes que los filtros «Hasta $100», «$100 a $300», «$300 a $600» y «Más de $600» de
# Productos (dcasa_catalogo/views/backend_views.xml, sobre el precio sin ITBMS): una prueba compara los dos.
CORTES_PRECIO = ((100, 'hasta_100'), (300, '100_a_300'), (600, '300_a_600'))
MAS_DE_600 = 'mas_de_600'

# «Pocas» = 5 unidades o menos: el mismo umbral de Juan y del Escáner (dcasa_barras/models/barras.py,
# decisión 4 de PRIORIDADES del 2026-10-16).
UMBRAL_POCAS = 5.0
DISPONIBLE, POCAS, AGOTADO = 'disponible', 'pocas', 'agotado'

MODOS_DISPONIBILIDAD = ('web', 'existencias')
EN_EXISTENCIA, SIN_EXISTENCIA = 'in stock', 'out of stock'  # Meta: con espacio (Google usa in_stock)

_NO_ALFANUMERICO = re.compile(r'[^a-z0-9]+')
_ENLACE = re.compile(r'(?:https?://|www\.)\S+', re.IGNORECASE)
_PARECE_HTML = re.compile(r'<\s*[a-zA-Z!/]')
_FIN_DE_FRASE = re.compile(r'([.!?¡¿]\s+)(\w)')
_BLOQUES = ('p', 'div', 'li', 'ul', 'ol', 'br', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'section', 'article', 'blockquote')


def etiqueta_ascii(texto, largo=LARGO_ETIQUETA):
    """«Habitación de Niños» → ``habitacion_de_ninos``: minúsculas, sin tildes ni eñes, solo ``[a-z0-9_]``.

    Los filtros de los conjuntos de productos de Meta no admiten letras fuera del inglés.
    """
    if not texto:
        return ''
    plano = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii').lower()
    return _NO_ALFANUMERICO.sub('_', plano).strip('_')[:largo].rstrip('_')


def banda_precio(monto):
    """Franja de precio (el número de la página, sin ITBMS) para armar conjuntos de productos en Meta."""
    for tope, etiqueta in CORTES_PRECIO:
        if monto <= tope:
            return etiqueta
    return MAS_DE_600


def nivel_existencias(cantidad):
    """``disponible`` (más de 5), ``pocas`` (1 a 5) o ``agotado`` (0 o menos).

    ``cantidad`` None = el producto no controla inventario (un combo, un servicio): no se puede agotar, y como en
    el Escáner y en Juan se dice ``disponible``.
    """
    if cantidad is None:
        return DISPONIBLE
    if cantidad <= 0:
        return AGOTADO
    if cantidad <= UMBRAL_POCAS:
        return POCAS
    return DISPONIBLE


def disponibilidad(modo, cantidad):
    """La columna ``availability`` de Meta (con espacio: ``in stock`` / ``out of stock``).

    * ``web``: como la tienda en línea, que vende sin existencias confirmadas y no muestra «agotado»: todo lo
      publicado sale ``in stock``.
    * ``existencias``: ``out of stock`` si no queda ninguna unidad; lo que no controla inventario (``cantidad``
      None) sigue ``in stock``.
    """
    if modo not in MODOS_DISPONIBILIDAD:
        raise ValueError(f'Modo de disponibilidad desconocido: {modo!r}')
    if modo == 'existencias' and cantidad is not None and cantidad <= 0:
        return SIN_EXISTENCIA
    return EN_EXISTENCIA


def _cortar(texto, largo):
    """Corta en el último espacio antes de ``largo`` (si no hay ninguno, corta seco)."""
    if len(texto) <= largo:
        return texto
    trozo = texto[:largo + 1]
    corte = trozo.rsplit(' ', 1)[0] if ' ' in trozo else texto[:largo]
    return corte[:largo].rstrip(' ,;:-')


def _tipo_oracion(texto):
    """«CAMA KING. CON CAJONES» → «Cama king. Con cajones»."""
    texto = _FIN_DE_FRASE.sub(lambda m: m.group(1) + m.group(2).upper(), texto.lower())
    for i, letra in enumerate(texto):
        if letra.isalpha():
            return texto[:i] + letra.upper() + texto[i + 1:]
    return texto


def _sin_html(texto):
    try:
        raiz = html.fragment_fromstring(texto, create_parent='div')
    except (etree.ParserError, ValueError):
        return re.sub(r'<[^>]*>', ' ', texto)
    for nodo in raiz.xpath('//script|//style'):
        nodo.drop_tree()
    for nodo in raiz.iter(*_BLOQUES):
        # Un bloque termina una palabra: «<p>uno</p><p>dos</p>» no debe quedar «unodos».
        nodo.tail = ' ' + (nodo.tail or '')
        if nodo.tag != 'br':
            nodo.text = ' ' + (nodo.text or '')
    return raiz.text_content()


def texto_plano(texto, largo=LARGO_DESCRIPCION):
    """Descripción para Meta: sin HTML ni enlaces, espacios juntos, tipo oración si todo viene en mayúsculas, y a lo
    sumo ``largo`` caracteres (cortada en una palabra)."""
    if not texto:
        return ''
    texto = str(texto)
    if _PARECE_HTML.search(texto):
        texto = _sin_html(texto)
    texto = ' '.join(_ENLACE.sub(' ', texto).split())
    if any(c.isalpha() for c in texto) and not any(c.islower() for c in texto):
        texto = _tipo_oracion(texto)
    return _cortar(texto, largo)


def titulo(texto, largo=LARGO_TITULO):
    """Título para Meta: una sola línea de a lo sumo ``largo`` caracteres, cortado en una palabra."""
    return _cortar(' '.join(str(texto or '').split()), largo)


def formato_precio(monto, moneda, decimales=2):
    """``399.00 USD``: siempre con los decimales de la moneda (redondeo comercial, como Odoo).

    No se usa ``gmc_format_price`` de Odoo: escribe ``40.0 USD``.
    """
    valor = Decimal(repr(float(monto))).quantize(Decimal(1).scaleb(-int(decimales)), rounding=ROUND_HALF_UP)
    return f'{valor} {moneda}'
