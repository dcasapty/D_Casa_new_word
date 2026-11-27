"""Sacar el punto (latitud, longitud) de un enlace de Google Maps, Waze o Apple Maps (docs/UBICACION.md, contrato §4).

Lo usa Brian (``poner_ubicacion_de_entrega``); el Worker de Juan tiene su propia copia en TypeScript con las mismas
reglas. Un enlace sin coordenadas (una búsqueda por nombre: «maps.google.com/?q=Super 99») **no se adivina**.

Los enlaces cortos (``maps.app.goo.gl/…``, ``goo.gl/maps/…``) se siguen a mano, solo hacia hosts de Google, como mucho
3 saltos y 5 s, sin leer el cuerpo: así nadie usa esto para que el servidor visite otra cosa.
"""
import re
import time
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from . import geo

HOSTS_GOOGLE = {'maps.app.goo.gl', 'goo.gl', 'maps.google.com', 'www.google.com', 'google.com', 'maps.google.com.pa',
                'www.google.com.pa', 'google.com.pa'}
HOSTS_CORTOS = {'maps.app.goo.gl', 'goo.gl'}
HOSTS_WAZE = {'waze.com', 'www.waze.com', 'ul.waze.com'}
HOSTS_APPLE = {'maps.apple.com'}
MAX_SALTOS = 3
ESPERA_TOTAL_S = 5
MAX_ENLACE = 2000

_PAR = r'(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)'
_ARROBA = re.compile(r'@' + _PAR)
_BANG = re.compile(r'!3d(-?\d{1,3}(?:\.\d+)?)!4d(-?\d{1,3}(?:\.\d+)?)')
_SOLO_PAR = re.compile(r'^\s*' + _PAR + r'\s*$')
_ENLACE_EN_TEXTO = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)


def _par(lat, lon):
    try:
        return geo.punto(float(lat), float(lon))
    except (TypeError, ValueError):
        return None


def _de_parametros(consulta, claves):
    parametros = parse_qs(consulta, keep_blank_values=False)
    for clave in claves:
        for valor in parametros.get(clave, []):
            encontrado = _SOLO_PAR.match(unquote(valor))
            if encontrado:
                punto = _par(*encontrado.groups())
                if punto:
                    return punto
    return None


def coordenadas_sin_red(enlace):
    """El punto de un enlace largo (sin seguir redirecciones), o ``None``."""
    if not isinstance(enlace, str) or len(enlace) > MAX_ENLACE:
        return None
    partes = urlsplit(enlace.strip())
    host = (partes.hostname or '').lower()
    if partes.scheme not in ('http', 'https'):
        return None
    if host in HOSTS_WAZE:
        return _de_parametros(partes.query, ('ll', 'latlng', 'q'))
    if host in HOSTS_APPLE:
        return _de_parametros(partes.query, ('ll', 'q', 'sll', 'daddr'))
    if host in HOSTS_GOOGLE and (host.startswith('maps.') or partes.path.startswith('/maps')):
        camino = unquote(partes.path)
        # «!3d…!4d…» es el lugar exacto; «@lat,lon» es el centro de la vista (va después, como respaldo).
        for patron in (_BANG, _ARROBA):
            encontrado = patron.search(camino)
            if encontrado:
                punto = _par(*encontrado.groups())
                if punto:
                    return punto
        punto = _de_parametros(partes.query, ('q', 'query', 'll', 'destination', 'daddr', 'center'))
        if punto:
            return punto
        return _de_parametros('q=' + camino.rsplit('/', 1)[-1], ('q',)) if '/place/' in camino or '/search/' in camino \
            else None
    return None


def _es_corto(enlace):
    partes = urlsplit(enlace)
    host = (partes.hostname or '').lower()
    return host in HOSTS_CORTOS and (host == 'maps.app.goo.gl' or partes.path.startswith('/maps'))


def _segura(url, hosts):
    """La URL en https si es de uno de ``hosts`` sin trucos, o ``None``. La revisa el MISMO analizador que usa
    ``requests`` (urllib3) y debe coincidir con ``urlsplit``: con «http://127.0.0.1:9999\\@maps.app.goo.gl/x» uno veía
    Google y el otro se conectaba a la máquina (auditoría 1). Sin usuario, sin puerto raro, sin «\\» ni espacios
    (la «@» sí, en el camino: «/@8.9,-79.8,17z» es de Google)."""
    from urllib3.exceptions import LocationParseError
    from urllib3.util import parse_url

    if not isinstance(url, str) or len(url) > MAX_ENLACE or any(c in url for c in '\\ \t\r\n'):
        return None
    try:
        partes = parse_url(url)
    except LocationParseError:
        return None
    host = (partes.host or '').lower()
    if partes.scheme not in ('https', 'http') or partes.auth or partes.port not in (None, 443) or host not in hosts:
        return None
    if (urlsplit(url).hostname or '').lower() != host:
        return None
    return 'https://' + url.split('://', 1)[1] if partes.scheme == 'http' else url


def resolver(enlace, pedir=None):
    """Sigue un enlace corto de Google hasta el largo (solo hosts de Google, 3 saltos, 5 s). ``pedir(url, espera)``
    devuelve la cabecera ``Location`` o ``None`` (se inyecta en las pruebas). Devuelve el enlace largo o ``None``."""
    if pedir is None:
        pedir = _pedir_location
    actual, inicio = _segura(enlace, HOSTS_CORTOS), time.monotonic()
    if not actual:
        return None
    for _ in range(MAX_SALTOS):
        restante = ESPERA_TOTAL_S - (time.monotonic() - inicio)
        if restante <= 0:
            return None
        siguiente = pedir(actual, restante)
        if not siguiente:
            return None
        siguiente = urljoin(actual, siguiente)
        if not siguiente.startswith('https://') or not _segura(siguiente, HOSTS_GOOGLE):
            return None
        if coordenadas_sin_red(siguiente):
            return siguiente
        actual = siguiente
    return None


def _pedir_location(url, espera):
    import requests  # aquí, para que el motor se pruebe sin la red

    try:
        respuesta = requests.get(url, allow_redirects=False, timeout=min(espera, ESPERA_TOTAL_S), stream=True)
        respuesta.close()
    except requests.RequestException:
        return None
    if respuesta.status_code not in (301, 302, 303, 307, 308):
        return None
    return respuesta.headers.get('Location')


def coordenadas(texto, resolver_cortos=False, pedir=None):
    """El primer punto que traiga un enlace de mapa dentro de ``texto`` (o el texto mismo si es un enlace), o
    ``None``. Con ``resolver_cortos`` sigue los enlaces cortos de Google (``resolver``)."""
    if not isinstance(texto, str):
        return None
    for crudo in _ENLACE_EN_TEXTO.findall(texto[:4000])[:5]:
        enlace = crudo.rstrip('.,;)')
        punto = coordenadas_sin_red(enlace)
        if punto:
            return punto
        if resolver_cortos and _es_corto(enlace):
            largo = resolver(enlace, pedir)
            if largo:
                return coordenadas_sin_red(largo)
    return None
