"""Conversions API de Meta: normalización, hash y envío. Sin ORM: cada función se prueba sola.

Reglas que no se negocian (docs/META_EVENTOS.md):

* El correo y el celular viajan SOLO como SHA-256 (una sola vez, hexadecimal en minúsculas). Nunca en claro.
* El token (``META_CAPI_TOKEN``) se lee del entorno en el momento del envío, va en el CUERPO del POST (nunca en
  la URL) y ningún texto de error lo guarda ni lo registra: todo pasa por ``limpiar_error``.
* En el log nunca quedan los datos del evento, los hashes ni el token: solo el código HTTP y el texto limpio.
"""
import hashlib
import ipaddress
import json
import os
import re

import requests

from odoo.addons.dcasa_contactos.models import claves

VARIABLE_TOKEN = 'META_CAPI_TOKEN'
VERSION_GRAPH = 'v26.0'  # la misma que usa Juan (juan/src/canales/graph.ts); se cambia en Ajustes › Meta
URL_EVENTOS = 'https://graph.facebook.com/{version}/{pixel}/events'
TIEMPO_ESPERA = (5, 20)  # (conectar, leer) en segundos
LARGO_ERROR = 500

RE_PIXEL = re.compile(r'^\d{5,20}$')
RE_VERSION = re.compile(r'^v\d{1,3}\.\d{1,2}$')
RE_CODIGO_PRUEBA = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
# _fbp = fb.<subdominio>.<creación en ms>.<aleatorio>; _fbc = fb.<subdominio>.<creación en ms>.<fbclid>. Meta pide
# no tocarlos (ni pasarlos a minúsculas): solo se comprueba la forma para no guardar basura de una cookie ajena.
RE_FBP = re.compile(r'^fb\.\d\.\d{9,14}\.[\w.-]{1,120}$')
RE_FBC = re.compile(r'^fb\.\d\.\d{9,14}\.[\w.-]{1,600}$')

# Resultado de un envío.
OK = 'ok'
REINTENTAR = 'reintentar'   # 5xx, 429, límite de Meta, red o tiempo agotado: se espera y se vuelve a intentar
TOKEN = 'token'             # el token no sirve (o no tiene permiso): todo queda pendiente y se avisa en Ajustes
INVALIDO = 'invalido'       # otro 4xx: algo del evento está mal

# Códigos de error de la Graph API (sin verificar uno por uno con Meta; ver docs/META_EVENTOS.md, «Sin verificar»).
CODIGOS_TOKEN = frozenset({102, 190, 10, 200})       # sesión o token inválido, sin permiso
CODIGOS_LIMITE = frozenset({4, 17, 32, 613, 80004})  # demasiadas llamadas


def sha256(texto):
    """SHA-256 en hexadecimal (minúsculas) de un texto YA normalizado. Se llama una sola vez por dato."""
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def correo_normal(texto):
    """``'ana@x.com'`` (minúsculas, sin nombre ni espacios) o ``None``: la misma llave de Contactos."""
    return claves.llave_correo(texto)


def telefono_normal(texto):
    """Dígitos con código de país: Panamá → ``'507' + 8 dígitos``; otro país, sus dígitos completos; o ``None``.

    Sale de la misma llave de Contactos (``llave_telefono``): ``6026-1919``, ``+507 6026 1919`` y ``00507 6026 1919``
    son la misma persona. Sin ``+`` ni ceros de salida internacional, como pide Meta.
    """
    llave = claves.llave_telefono(texto)
    if not llave:
        return None
    tipo, _, digitos = llave.partition(':')
    return f'507{digitos}' if tipo == 'pa' else digitos


def hash_correo(texto):
    normal = correo_normal(texto)
    return sha256(normal) if normal else None


def hash_telefono(texto):
    normal = telefono_normal(texto)
    return sha256(normal) if normal else None


def hash_id_externo(partner_id):
    """El id de la ficha comercial, con prefijo para que no se confunda con otros números."""
    return sha256(f'dcasa-{int(partner_id)}')


def hash_pais(codigo):
    """Solo Panamá (``'pa'``): de otros países no se manda nada (sin verificar con Meta, ver la documentación)."""
    codigo = (codigo or '').strip().lower()
    return sha256(codigo) if codigo == 'pa' else None


def fbp_valida(valor):
    valor = (valor or '').strip()
    return valor if RE_FBP.match(valor) else None


def fbc_valida(valor):
    valor = (valor or '').strip()
    return valor if RE_FBC.match(valor) else None


def token():
    """El token de la Conversions API, leído del entorno EN EL MOMENTO (no se guarda en la base ni en memoria)."""
    return (os.environ.get(VARIABLE_TOKEN) or '').strip()


def es_produccion():
    """Solo en producción salen eventos reales y se dibuja el píxel; en cualquier otro entorno (staging, local,
    pruebas) la Conversions API solo manda con el código de prueba y el píxel no se dibuja."""
    return (os.environ.get('DCASA_ENTORNO') or '').strip().lower() == 'produccion'


_RE_ACCESS_TOKEN = re.compile(r'(access_token["\']?\s*[=:]\s*["\']?)[^&\s"\',}]+', re.IGNORECASE)
_RE_HASH = re.compile(r'\b[0-9a-fA-F]{64}\b')
_RE_CORREO = re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+')
_RE_COOKIE_META = re.compile(r'\bfb\.\d\.\d{9,14}\.[\w.-]+')
_RE_IPV4 = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
_RE_IPV6_CANDIDATA = re.compile(r'[0-9A-Fa-f.]*:[0-9A-Fa-f:.]*')


def _sin_ipv6(texto):
    def cambiar(encontrado):
        candidata = encontrado.group(0)
        try:
            ipaddress.IPv6Address(candidata)
        except ValueError:
            return candidata  # una hora (21:15:08) u otra cosa con «:»: se deja
        return '<ip>'
    return _RE_IPV6_CANDIDATA.sub(cambiar, texto)


def limpiar_error(texto, secreto=None):
    """Texto de error apto para guardar o registrar: sin el token, hashes, correos, IP ni cookies de Meta, en una
    línea y con ≤ 500 caracteres (Meta puede repetir en su error un dato del evento)."""
    texto = str(texto or '')
    secreto = token() if secreto is None else secreto
    if secreto:
        texto = texto.replace(secreto, '***')
    texto = _RE_ACCESS_TOKEN.sub(r'\1***', texto)
    texto = _RE_HASH.sub('<hash>', texto)
    texto = _RE_CORREO.sub('<correo>', texto)
    texto = _RE_COOKIE_META.sub('<cookie>', texto)
    texto = _RE_IPV4.sub('<ip>', texto)
    texto = _sin_ipv6(texto)
    return ' '.join(texto.split())[:LARGO_ERROR]


def clasificar(status, cuerpo):
    """``(tipo, error)`` de una respuesta de la Graph API. ``error`` es el dict ``error`` de Meta (o vacío)."""
    error = cuerpo.get('error') if isinstance(cuerpo, dict) and isinstance(cuerpo.get('error'), dict) else {}
    codigo = error.get('code')
    if 200 <= status < 300 and not error:
        return OK, error
    if status in (401, 403) or codigo in CODIGOS_TOKEN:
        return TOKEN, error
    if status == 429 or status >= 500 or codigo in CODIGOS_LIMITE or error.get('is_transient'):
        return REINTENTAR, error
    return INVALIDO, error


def enviar(eventos, pixel_id, version, secreto, codigo_prueba=None):
    """POST de un lote a ``/{version}/{pixel}/events``. No lanza: devuelve un dict con

    ``tipo`` (OK, REINTENTAR, TOKEN, INVALIDO), ``status`` (0 = no hubo respuesta), ``recibidos``,
    ``fbtrace_id`` y ``mensaje`` (limpio: sin token, hashes ni correos).

    El token va en el cuerpo (``data=``), nunca en la URL ni en una cabecera que alguien pueda registrar.
    """
    if not RE_PIXEL.match(pixel_id or '') or not RE_VERSION.match(version or ''):
        return {'tipo': INVALIDO, 'status': 0, 'recibidos': 0, 'fbtrace_id': '',
                'mensaje': 'El ID del píxel o la versión de la API no son válidos.'}
    if not secreto:
        return {'tipo': TOKEN, 'status': 0, 'recibidos': 0, 'fbtrace_id': '', 'mensaje': 'Falta el token de Meta.'}
    cuerpo_post = {'data': json.dumps(eventos, separators=(',', ':')), 'access_token': secreto}
    if codigo_prueba:
        cuerpo_post['test_event_code'] = codigo_prueba
    try:
        respuesta = requests.post(URL_EVENTOS.format(version=version, pixel=pixel_id), data=cuerpo_post,
                                  timeout=TIEMPO_ESPERA)
    except requests.RequestException as error:
        return {'tipo': REINTENTAR, 'status': 0, 'recibidos': 0, 'fbtrace_id': '',
                'mensaje': limpiar_error(f'{type(error).__name__}: {error}', secreto)}
    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    tipo, error = clasificar(respuesta.status_code, cuerpo)
    fbtrace = limpiar_error(error.get('fbtrace_id') or cuerpo.get('fbtrace_id') or '', secreto)[:64]
    if tipo == OK:
        mensaje = ''
    elif error:
        mensaje = limpiar_error(
            f"HTTP {respuesta.status_code} · código {error.get('code')} · {error.get('error_user_msg') or ''} "
            f"{error.get('message') or ''}", secreto)
    else:
        mensaje = limpiar_error(f'HTTP {respuesta.status_code} · {(respuesta.text or "")[:300]}', secreto)
    recibidos = cuerpo.get('events_received', 0)
    return {'tipo': tipo, 'status': respuesta.status_code, 'recibidos': recibidos if isinstance(recibidos, int) else 0,
            'fbtrace_id': fbtrace, 'mensaje': mensaje}
