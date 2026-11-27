"""La ubicación de entrega, en puro Python (sin Odoo): qué punto vale, de dónde salió, qué zona es y los dos botones
del motorizado. Lo usan los modelos, las páginas públicas y Juan; se prueba sin base de datos (tests/test_geo.py).

La zona (barriada, corregimiento, distrito, provincia) sale de la **tabla de lugares de la calculadora de envíos**, la
misma que pone el precio: así la dirección que ve la clienta y el precio del envío no se contradicen. Google (si hay
clave) solo aporta la calle, como ayuda.
"""
import hashlib
import secrets
from urllib.parse import quote

from odoo.addons.dcasa_envios.motor import buscador, choferes

# De dónde salió el punto. El orden es el de la confianza (de más a menos).
ORIGENES = [
    ('gps', 'Ubicación del teléfono'),
    ('pin', 'Marcada en el mapa'),
    ('whatsapp', 'Compartida por el chat'),
    ('enlace', 'De un enlace de Google Maps o Waze'),
    ('busqueda', 'Buscada en el mapa'),
    ('escrita', 'Escrita a mano'),
]
ETIQUETAS = dict(ORIGENES)
CONFIABLES = ('gps', 'pin', 'whatsapp', 'enlace')
PRECISION_MAX_M = 100           # GPS con más error que esto: se le pide mover el mapa hasta su puerta
RADIO_PRECIO_M = choferes.RADIO_CERCA_M     # el lugar que pone el precio: el más cercano a no más de 3 km (como Juan)
RADIO_BARRIADA_M = 1500         # la barriada: el barrio o urbanización más cercano a no más de 1,5 km
RADIO_PANAMA_M = 25_000         # con la tabla cargada, un punto a más de 25 km de cualquier lugar no se acepta
MAX_REFERENCIA = 200
MAX_TEXTO = 200


def punto(lat, lon):
    """``(lat, lon)`` redondeados a 7 decimales (≈ 1 cm) si son números de Panamá (con su mar e islas); si no,
    ``None``. Un texto, un booleano, ``NaN`` o un número gigante no son coordenadas."""
    valido = choferes.ubicacion_valida(lat, lon)
    if not valido:
        return None
    return round(valido[0], 7), round(valido[1], 7)


def precision_m(valor):
    """La precisión que da el GPS del teléfono, en metros enteros (0 a 100 000), o ``None``."""
    numero = choferes.coordenada(valor)
    if numero is None or numero < 0 or numero > 100_000:
        return None
    return int(round(numero))


def es_confiable(origen, precision=None):
    """¿Se puede mandar al motorizado sin llamar antes? GPS solo si el error es de 100 m o menos."""
    if origen not in CONFIABLES:
        return False
    return not (origen == 'gps' and precision is not None and precision > PRECISION_MAX_M)


def etiqueta(origen, precision=None):
    """«Ubicación del teléfono (±12 m)», «Marcada en el mapa», «Escrita a mano»…"""
    texto = ETIQUETAS.get(origen, '')
    if origen == 'gps' and precision is not None:
        texto += f' (±{precision} m)'
    return texto


def texto_corto(valor, maximo=MAX_TEXTO):
    """Un texto de una línea, sin espacios de más, recortado (o ``''``)."""
    if not isinstance(valor, str):
        return ''
    return ' '.join(valor.split())[:maximo]


def enlaces(lat, lon):
    """Los dos botones del motorizado: navegar con Waze o con Google Maps hasta el punto."""
    coordenadas = quote(f'{lat:.7f},{lon:.7f}', safe='')
    return {
        'waze': f'https://waze.com/ul?ll={coordenadas}&navigate=yes',
        'google': f'https://www.google.com/maps/dir/?api=1&destination={coordenadas}',
    }


def deducir_zona(lugares, lat, lon):
    """La zona del punto con la tabla de lugares (la lista del motor de envíos, con ``lat``/``lon``).

    Devuelve ``{'precio': pos|None, 'precio_m', 'barriada', 'corregimiento', 'distrito', 'provincia', 'cerca_m'}``:
    ``precio`` es la posición del lugar más cercano a no más de 3 km (el que pone el precio, como Juan y «Usar mi
    ubicación»); la barriada es el barrio más cercano a no más de 1,5 km; el corregimiento, el distrito y la provincia,
    los del lugar más cercano que los tenga. ``cerca_m`` es la distancia al lugar más cercano a no más de unos 30 km
    (``None`` si no hay ninguno tan cerca) y ``tabla`` dice si la tabla tiene algún lugar con coordenadas: con tabla y
    sin nada a 25 km, el punto no se acepta (mar, Costa Rica o Colombia)."""
    mas_cercano = barrio = con_corr = None
    tabla = False
    for posicion, lugar in enumerate(lugares):
        la, lo = lugar.get('lat'), lugar.get('lon')
        if la is None or lo is None:
            continue
        tabla = True
        if abs(la - lat) > 0.3 or abs(lo - lon) > 0.3:      # ≈ 33 km: descarta sin medir (la tabla tiene 11 000)
            continue
        metros = choferes.distancia_m(lat, lon, la, lo)
        if mas_cercano is None or metros < mas_cercano[1]:
            mas_cercano = (posicion, metros)
        if lugar.get('tipo') == 'barrio' and metros <= RADIO_BARRIADA_M and (barrio is None or metros < barrio[1]):
            barrio = (posicion, metros)
        if lugar.get('corr') and (con_corr is None or metros < con_corr[1]):
            con_corr = (posicion, metros)
    zona = {'precio': None, 'precio_m': None, 'barriada': '', 'corregimiento': '', 'distrito': '', 'provincia': '',
            'cerca_m': None, 'tabla': tabla}
    if mas_cercano is None:
        return zona
    zona['cerca_m'] = mas_cercano[1]
    if mas_cercano[1] <= RADIO_PRECIO_M:
        zona['precio'], zona['precio_m'] = mas_cercano
    if barrio:
        zona['barriada'] = lugares[barrio[0]].get('nombre') or ''
    fuente = lugares[con_corr[0]] if con_corr and con_corr[1] <= RADIO_PRECIO_M else lugares[mas_cercano[0]]
    if fuente.get('tipo') == 'corregimiento' and not fuente.get('corr'):
        zona['corregimiento'] = fuente.get('nombre') or ''
    else:
        zona['corregimiento'] = fuente.get('corr') or ''
    zona['distrito'] = fuente.get('dist') or ''
    zona['provincia'] = fuente.get('prov') or ''
    return zona


def en_cobertura(zona):
    """¿El punto es de Panamá según la tabla? Sin tabla cargada (instalación nueva) no se puede saber: vale el
    recuadro de ``punto``. Con tabla, tiene que haber algún lugar a no más de 25 km."""
    if not zona.get('tabla'):
        return True
    return zona.get('cerca_m') is not None and zona['cerca_m'] <= RADIO_PANAMA_M


def zona_texto(zona):
    """«Brisas del Golf · Rufina Alfaro · San Miguelito · Panamá» (sin repetir ni dejar huecos)."""
    partes = []
    for clave in ('barriada', 'corregimiento', 'distrito', 'provincia'):
        valor = (zona.get(clave) or '').strip()
        if valor and valor.lower() not in (p.lower() for p in partes):
            partes.append(valor)
    return ' · '.join(partes)


def _normalizado(texto):
    return ' ' + ' '.join(buscador.tokens(texto or '')) + ' '


def distritos_mencionados(texto, distritos):
    """Los distritos de la lista cuyo nombre aparece entero en ``texto`` (sin tildes ni mayúsculas)."""
    escrito = _normalizado(texto)
    return [d for d in distritos if d and _normalizado(d).strip() and _normalizado(d) in escrito]


def aviso_de_cruce(texto_escrito, zona, distritos, con_mapa=True):
    """Si lo que escribió la clienta nombra otro distrito que el del punto, el aviso para que diga cuál es; si no,
    ``''``. Solo compara distritos (los nombres de barriadas se repiten en todo el país). Sin mapa (``con_mapa``
    falso: sin clave o no cargó) no hay mapa que mover: que busque la barriada (auditoría 2)."""
    del_punto = (zona.get('distrito') or '').strip()
    if not del_punto or not texto_escrito:
        return ''
    nombrados = distritos_mencionados(texto_escrito, distritos)
    if not nombrados or any(_normalizado(d) == _normalizado(del_punto) for d in nombrados):
        return ''
    arreglo = 'Mueva el mapa o corrija la dirección.' if con_mapa else 'Busque la barriada o corrija la dirección.'
    return (f'Su punto en el mapa está en {del_punto} y en la dirección escribió {nombrados[0]}. '
            f'¿Cuál es el correcto? {arreglo}')


def token_nuevo(bytes_azar=16):
    """Un secreto para un enlace (128 bits al azar por defecto), apto para URL."""
    return secrets.token_urlsafe(bytes_azar)


def huella(token):
    """La huella (SHA-256) que se guarda en vez del secreto."""
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()
