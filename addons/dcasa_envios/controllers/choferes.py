"""El enlace para choferes: la calculadora de envíos reducida, sin usuario de Odoo (pedido de la dueña, 2026-11-09).

``GET /envios/choferes/<enlace>`` es la página; ``POST …/buscar`` ({"texto"}) y ``POST …/cerca`` ({"lat", "lon"}) son
lo que la página pide. Es la única ruta pública de envíos, así que va estricta:

* **El enlace es la llave.** Un solo secreto para todos los choferes (192 bits al azar, ``secrets.token_urlsafe``) que
  Gerencia enciende, copia y cambia en Envíos › Tarifa. Apagado o con otro secreto, las tres rutas responden el mismo
  404 de texto plano (no dicen por qué). Se compara en tiempo constante (``hmac.compare_digest``).
* **Sin CSRF porque el secreto autentica**: no hay sesión ni cookie (``save_session=False``) que alguien pueda usar
  desde otra página.
* **Solo lo que ve el chofer**: nombre, zona, precio (o el aviso) y la ruta en Google Maps; nunca ids, km, desglose ni
  la tabla. Lo arma ``motor/choferes.py``; aquí solo se valida y se responde. Los lugares se leen con ``sudo()`` por
  los métodos privados del modelo (``_choferes_buscar``, ``_choferes_cerca``) DESPUÉS de comprobar el enlace; el ACL de
  los usuarios públicos y del portal no cambia.
* **Límite por IP** (en la memoria de cada proceso, como el de Brian): 60 peticiones por minuto entre las tres rutas;
  después, 429 por un minuto.
* **Nada se guarda ni se indexa**: ``Cache-Control: no-store``, ``X-Robots-Tag: noindex, nofollow``,
  ``Referrer-Policy: no-referrer`` (Google Maps no se entera del enlace) y una CSP con nonce. La ubicación del chofer
  solo se usa para buscar el lugar más cercano: ni se guarda ni se escribe en el registro.
"""
import json
import secrets
import threading
import time
from collections import deque

from odoo import http
from odoo.http import request

from ..motor import choferes
from ..motor.tarjeta import ATRIBUCION

RUTA = '/envios/choferes/<string:token>'
MAX_POR_MINUTO = 60
MAX_IPS = 10_000              # con más IP distintas en memoria, se vacía (no crece sin límite)
MAX_CUERPO = 2048
MAX_TEXTO = 120
ESPERA_S = 60

CABECERAS = {
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
}

_candado = threading.Lock()
_ventanas = {}                # IP → deque de instantes (time.monotonic) del último minuto


def excede(ip, ahora=None, maximo=MAX_POR_MINUTO, ventana=ESPERA_S):
    """¿Esa IP ya hizo ``maximo`` peticiones en el último minuto? Si no, cuenta esta."""
    ahora = time.monotonic() if ahora is None else ahora
    with _candado:
        cola = _ventanas.get(ip)
        if cola is None:
            if len(_ventanas) >= MAX_IPS:
                _ventanas.clear()
            cola = _ventanas[ip] = deque()
        while cola and cola[0] <= ahora - ventana:
            cola.popleft()
        if len(cola) >= maximo:
            return True
        cola.append(ahora)
        return False


def reiniciar_limite():
    """Para las pruebas: olvida lo contado."""
    with _candado:
        _ventanas.clear()


def _cabeceras(**extra):
    return list(dict(CABECERAS, **extra).items())


def _no_existe():
    """El mismo 404 para «apagado» y «otro secreto»."""
    return request.make_response('Not Found', headers=_cabeceras(**{'Content-Type': 'text/plain; charset=utf-8'}),
                                 status=404)


def _json(datos, status=200):
    return request.make_json_response(datos, headers=_cabeceras(), status=status)


class EnlaceChoferes(http.Controller):

    def _entrada(self, token, en_json):
        """El límite por IP y el enlace. Devuelve la respuesta de rechazo, o ``None`` si se sigue."""
        if excede(request.httprequest.remote_addr or '-'):
            texto = 'Muchas búsquedas seguidas: espera un minuto y vuelve a intentar.'
            if en_json:
                respuesta = request.make_json_response({'error': texto}, headers=_cabeceras(), status=429)
            else:
                respuesta = request.make_response(
                    texto, headers=_cabeceras(**{'Content-Type': 'text/plain; charset=utf-8'}), status=429)
            respuesta.headers['Retry-After'] = str(ESPERA_S)
            return respuesta
        if not request.env['dcasa.envio.tarifa'].sudo()._choferes_enlace_vale(token):
            return _no_existe()
        return None

    def _cuerpo(self):
        """El JSON que manda la página (un objeto pequeño), o ``None``."""
        if (request.httprequest.content_length or 0) > MAX_CUERPO:
            return None
        crudo = request.httprequest.get_data()
        if len(crudo) > MAX_CUERPO:
            return None
        try:
            cuerpo = json.loads(crudo.decode('utf-8') or 'null')
        except (ValueError, UnicodeDecodeError):
            return None
        return cuerpo if isinstance(cuerpo, dict) else None

    @http.route(RUTA, type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def pagina(self, token, **_parametros):
        rechazo = self._entrada(token, en_json=False)
        if rechazo:
            return rechazo
        estado = request.env['dcasa.envio.tarifa'].sudo()._estado_publico()
        nonce = secrets.token_urlsafe(16)
        base = RUTA.replace('<string:token>', token)
        html = request.env['ir.qweb']._render('dcasa_envios.choferes_pagina', {
            'nonce': nonce,
            'ruta_buscar': base + '/buscar',
            'ruta_cerca': base + '/cerca',
            'aviso_tarifa': '' if estado['aprobada'] else choferes.EN_REVISION,
            'atribucion': ATRIBUCION,
            'max_texto': MAX_TEXTO,
        })
        csp = ("default-src 'none'; "
               f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
               "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
               "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        return request.make_response(html, headers=_cabeceras(**{
            'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': csp,
            'Permissions-Policy': 'geolocation=(self), camera=(), microphone=()'}))

    @http.route(RUTA + '/buscar', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def buscar(self, token, **_parametros):
        rechazo = self._entrada(token, en_json=True)
        if rechazo:
            return rechazo
        cuerpo = self._cuerpo()
        texto = cuerpo.get('texto') if cuerpo else None
        if not isinstance(texto, str) or len(texto) > MAX_TEXTO:
            return _json({'error': f'Escribe el lugar (hasta {MAX_TEXTO} letras).'}, status=400)
        return _json(request.env['dcasa.envio.lugar'].sudo()._choferes_buscar(texto))

    @http.route(RUTA + '/cerca', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def cerca(self, token, **_parametros):
        rechazo = self._entrada(token, en_json=True)
        if rechazo:
            return rechazo
        cuerpo = self._cuerpo()
        ubicacion = choferes.ubicacion_valida(cuerpo.get('lat'), cuerpo.get('lon')) if cuerpo else None
        if not ubicacion:
            return _json({'error': 'No pudimos leer tu ubicación: busca el lugar por nombre.'}, status=400)
        return _json(request.env['dcasa.envio.lugar'].sudo()._choferes_cerca(*ubicacion))
