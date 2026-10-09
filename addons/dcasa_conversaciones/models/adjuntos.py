"""Adjuntos de los mensajes: validar lo que manda el Worker y traer el archivo con seguridad.

El Worker manda cada adjunto como ``{tipo, url, nombre, mime}`` (o, opcional, ``base64`` en vez de
``url``). Odoo guarda el archivo en ``ir.attachment`` (que ``dcasa_adjuntos_r2`` lleva a R2).

Defensas:

* Solo ``http``/``https`` en los puertos 80 y 443, y **nunca** hacia direcciones internas: la URL se
  resuelve y si alguna dirección es privada, de loopback, de enlace local, multicast o reservada,
  no se descarga (SSRF: el contenedor de Odoo vive en una red con otras cosas).
* Sin redirecciones (una redirección podría saltar la comprobación anterior).
* Tamaño máximo por archivo y tiempo máximo de descarga; se lee por trozos y se corta al pasar el tope.
* Los tipos y nombres se limpian: lo que llega es dato de un tercero.
"""
import base64
import binascii
import ipaddress
import logging
import re
import socket
from urllib.parse import urlsplit

import requests

_logger = logging.getLogger(__name__)

TIPOS = ('imagen', 'audio', 'documento', 'video')
MAX_ADJUNTOS = 5
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = (3.05, 15)
PUERTOS = (None, 80, 443)
_MIME = re.compile(r'^[a-z0-9][a-z0-9!#$&^_.+-]{0,60}/[a-z0-9][a-z0-9!#$&^_.+-]{0,100}$')
_NOMBRE_MALO = re.compile(r'[\x00-\x1f\\/:*?"<>|]+')

TIPO_POR_MIME = (('image/', 'imagen'), ('audio/', 'audio'), ('video/', 'video'))


class AdjuntoInvalido(ValueError):
    """El adjunto que mandó el Worker no cumple el contrato (se responde 400)."""


def tipo_de_mime(mime):
    mime = (mime or '').lower()
    for prefijo, tipo in TIPO_POR_MIME:
        if mime.startswith(prefijo):
            return tipo
    return 'documento'


def nombre_seguro(nombre, por_defecto='adjunto'):
    limpio = _NOMBRE_MALO.sub('_', str(nombre or '')).strip(' .')[:120]
    return limpio or por_defecto


def mime_seguro(mime):
    mime = str(mime or '').strip().lower()
    return mime if _MIME.match(mime) else ''


def validar(adjunto):
    """Normaliza un adjunto del contrato o lanza ``AdjuntoInvalido``.

    Devuelve ``{tipo, nombre, mime, url, base64, sensible}`` (url y base64 son excluyentes).
    """
    if not isinstance(adjunto, dict):
        raise AdjuntoInvalido('Cada adjunto debe ser un objeto.')
    tipo = str(adjunto.get('tipo') or '').strip().lower()
    if tipo not in TIPOS:
        raise AdjuntoInvalido(f'El tipo de adjunto debe ser uno de: {", ".join(TIPOS)}.')
    url = adjunto.get('url')
    contenido = adjunto.get('base64')
    if bool(url) == bool(contenido):
        raise AdjuntoInvalido('Cada adjunto lleva «url» o «base64» (uno de los dos).')
    if url is not None and (not isinstance(url, str) or len(url) > 2048):
        raise AdjuntoInvalido('La «url» del adjunto no es válida.')
    if contenido is not None and not isinstance(contenido, str):
        raise AdjuntoInvalido('El «base64» del adjunto no es válido.')
    mime = mime_seguro(adjunto.get('mime'))
    return {
        'tipo': tipo,
        'nombre': nombre_seguro(adjunto.get('nombre')),
        'mime': mime,
        'url': url or None,
        'base64': contenido or None,
        'sensible': bool(adjunto.get('sensible')),
    }


def validar_lista(adjuntos):
    if adjuntos is None:
        return []
    if not isinstance(adjuntos, list):
        raise AdjuntoInvalido('«adjuntos» debe ser una lista.')
    if len(adjuntos) > MAX_ADJUNTOS:
        raise AdjuntoInvalido(f'Como máximo {MAX_ADJUNTOS} adjuntos por mensaje.')
    return [validar(a) for a in adjuntos]


# ---------------------------------------------------------------------------
# Descarga segura
# ---------------------------------------------------------------------------

def direccion_publica(ip):
    """¿Es una dirección de internet de verdad (ni privada, ni loopback, ni reservada…)?"""
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(direccion, 'ipv4_mapped', None):
        direccion = direccion.ipv4_mapped
    return direccion.is_global and not direccion.is_multicast


def url_permitida(url):
    """Esquema http(s), puerto 80/443 y TODAS las direcciones del host son públicas."""
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        return False
    if partes.scheme not in ('http', 'https') or not partes.hostname or puerto not in PUERTOS or partes.username:
        return False
    try:
        resueltas = socket.getaddrinfo(partes.hostname, puerto or (443 if partes.scheme == 'https' else 80),
                                       type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    direcciones = {r[4][0] for r in resueltas}
    return bool(direcciones) and all(direccion_publica(d) for d in direcciones)


def decodificar_base64(texto, max_bytes=MAX_BYTES):
    """Bytes del ``base64`` (con o sin el prefijo ``data:…;base64,``); ``None`` si no es válido o es muy grande."""
    if texto.startswith('data:'):
        _, _, texto = texto.partition(',')
    if len(texto) > (max_bytes * 4) // 3 + 8:
        return None
    try:
        datos = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        return None
    return datos if 0 < len(datos) <= max_bytes else None


def descargar(url, max_bytes=MAX_BYTES):
    """Bytes de la URL o ``None`` (sin lanzar): descarga acotada y sin redirecciones."""
    if not url_permitida(url):
        _logger.warning('Juan: URL de adjunto rechazada (esquema, puerto o dirección no permitidos).')
        return None
    try:
        with requests.get(url, stream=True, timeout=TIMEOUT, allow_redirects=False) as respuesta:
            if respuesta.status_code != 200:
                _logger.warning('Juan: la descarga de un adjunto respondió %s.', respuesta.status_code)
                return None
            declarado = respuesta.headers.get('Content-Length')
            if declarado and declarado.isdigit() and int(declarado) > max_bytes:
                return None
            trozos, total = [], 0
            for trozo in respuesta.iter_content(64 * 1024):
                total += len(trozo)
                if total > max_bytes:
                    return None
                trozos.append(trozo)
    except requests.RequestException as error:
        _logger.warning('Juan: no se pudo descargar un adjunto (%s).', type(error).__name__)
        return None
    datos = b''.join(trozos)
    return datos or None


def obtener_contenido(adjunto):
    """Bytes de un adjunto ya validado (``url`` o ``base64``), o ``None`` si no se pudo."""
    if adjunto.get('base64'):
        return decodificar_base64(adjunto['base64'])
    return descargar(adjunto['url'])
