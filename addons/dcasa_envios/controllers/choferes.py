"""El enlace para choferes: la calculadora de envíos reducida, sin usuario de Odoo (pedido de la dueña, 2026-11-09).

``GET /envios/choferes/<enlace>`` es la página; ``POST …/buscar`` ({"texto"}) y ``POST …/cerca`` ({"lat", "lon"}) son
lo que la página pide. Es la única ruta pública de envíos, así que va estricta:

* **El enlace es la llave.** Un solo secreto para todos los choferes (192 bits al azar, ``secrets.token_urlsafe``) que
  Gerencia enciende, copia y cambia en Envíos › Tarifa. Apagado o con otro secreto, las tres rutas responden el mismo
  404 de texto plano (no dicen por qué). Se compara en tiempo constante (``hmac.compare_digest``).
* **Sin CSRF porque el secreto autentica**: no hay sesión ni cookie (``save_session=False``) que alguien pueda usar
  desde otra página. La página pide con ``credentials: 'same-origin'`` (no ``'omit'``): las pruebas en el navegador
  necesitan su cookie, y da igual quién esté conectado en ese teléfono porque todo se lee con ``sudo()`` tras validar
  el enlace (la página misma, al abrirse, ya manda las cookies del sitio).
* **Cuerpo de a lo sumo 2 KB** (``max_content_length``): más grande, 413 antes de leerlo entero.
* **Solo lo que ve el chofer**: nombre, zona, precio (o el aviso) y la ruta en Google Maps; nunca ids, km, desglose ni
  la tabla. Lo arma ``motor/choferes.py``; aquí solo se valida y se responde. Los lugares se leen con ``sudo()`` por
  los métodos privados del modelo (``_choferes_buscar``, ``_choferes_cerca``) DESPUÉS de comprobar el enlace; el ACL de
  los usuarios públicos y del portal no cambia.
* **Límites** (en la memoria del proceso, como el de Brian; se reinician si el servidor se reinicia): 60 peticiones por
  minuto por IP entre las tres rutas (una IPv6 cuenta por su red /64: cambiar de dirección dentro de ella no da más
  turnos), 300 por minuto entre todas las IP, y a lo sumo 2 búsquedas a la vez (la tercera recibe «ocupado» en vez de
  esperar: así nadie con el enlace frena el resto de Odoo). Por día, el enlace da hasta ``MAX_POR_DIA`` búsquedas; al
  llegar, responde 429 hasta el día siguiente (hora de Panamá) y deja una nota en la tarifa para Gerencia: un enlace
  que se filtró o alguien copiando la lista se nota y se corta con «Crear un enlace nuevo».
* **El texto, corto**: hasta ``MAX_TEXTO`` letras y ``MAX_PALABRAS`` palabras (un nombre de lugar cabe de sobra; un
  texto largo armado a propósito costaría segundos de CPU).
* **Nada se guarda ni se indexa**: ``Cache-Control: no-store``, ``X-Robots-Tag: noindex, nofollow``,
  ``Referrer-Policy: no-referrer`` (Google Maps no se entera del enlace) y una CSP con nonce. La ubicación del chofer
  solo se usa para buscar el lugar más cercano: ni se guarda ni se escribe en el registro.
"""
import ipaddress
import json
import logging
import secrets
import threading
import time
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import http
from odoo.http import request

from ..motor import choferes
from ..motor.tarjeta import ATRIBUCION

_logger = logging.getLogger(__name__)

RUTA = '/envios/choferes/<string:token>'
MAX_POR_MINUTO = 60
MAX_TODOS_POR_MINUTO = 300    # entre todas las IP
MAX_A_LA_VEZ = 2              # búsquedas corriendo al mismo tiempo
MAX_POR_DIA = 1500            # búsquedas (por nombre o por ubicación) por día con el enlace
MAX_IPS = 10_000              # con más IP distintas en memoria, se vacía (no crece sin límite)
MAX_CUERPO = 2048
MAX_TEXTO = 60
MAX_PALABRAS = 6
ESPERA_S = 60
ESPERA_OCUPADO_S = 5
TODOS = '*'                   # la llave del límite entre todas las IP
ZONA = ZoneInfo('America/Panama')

CABECERAS = {
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
}

_candado = threading.Lock()
_ventanas = {}                # IP (o su red /64, o TODOS) → deque de instantes (time.monotonic) del último minuto
_ocupado = threading.BoundedSemaphore(MAX_A_LA_VEZ)
_dia = {'llave': None, 'busquedas': 0, 'avisado': False}     # llave = (fecha, enlace): un enlace nuevo empieza en 0


def llave_ip(ip):
    """La llave del límite: la IPv4 entera; de una IPv6, su red /64 (lo que recibe un solo cliente)."""
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return ip or '-'
    if direccion.version == 6:
        if direccion.ipv4_mapped:
            return str(direccion.ipv4_mapped)
        return str(ipaddress.ip_network(f'{direccion}/64', strict=False))
    return str(direccion)


def excede(ip, ahora=None, maximo=MAX_POR_MINUTO, ventana=ESPERA_S):
    """¿Esa llave ya hizo ``maximo`` peticiones en el último minuto? Si no, cuenta esta."""
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


def hoy():
    return datetime.now(ZONA).date()


def contar_busqueda(enlace, fecha=None, maximo=None):
    """Cuenta una búsqueda de hoy con ese enlace. Devuelve ``(permitida, avisar)``: ``avisar`` es verdadero una sola
    vez por día, la primera vez que se llega al tope (para dejarle la nota a Gerencia). Un enlace nuevo empieza de 0."""
    llave, maximo = (fecha or hoy(), enlace), MAX_POR_DIA if maximo is None else maximo
    with _candado:
        if _dia['llave'] != llave:
            _dia.update(llave=llave, busquedas=0, avisado=False)
        if _dia['busquedas'] >= maximo:
            avisar = not _dia['avisado']
            _dia['avisado'] = True
            return False, avisar
        _dia['busquedas'] += 1
        return True, False


def busquedas_de_hoy(enlace):
    """Cuántas búsquedas lleva hoy ese enlace (en la memoria de este proceso)."""
    with _candado:
        return _dia['busquedas'] if _dia['llave'] == (hoy(), enlace) else 0


def reiniciar_limite():
    """Para las pruebas: olvida lo contado."""
    with _candado:
        _ventanas.clear()
        _dia.update(llave=None, busquedas=0, avisado=False)


def _cabeceras(**extra):
    return list(dict(CABECERAS, **extra).items())


def _no_existe():
    """El mismo 404 para «apagado» y «otro secreto»."""
    return request.make_response('Not Found', headers=_cabeceras(**{'Content-Type': 'text/plain; charset=utf-8'}),
                                 status=404)


def _json(datos, status=200):
    return request.make_json_response(datos, headers=_cabeceras(), status=status)


def _demasiado(texto, espera_s, en_json=True):
    if en_json:
        respuesta = request.make_json_response({'error': texto}, headers=_cabeceras(), status=429)
    else:
        respuesta = request.make_response(
            texto, headers=_cabeceras(**{'Content-Type': 'text/plain; charset=utf-8'}), status=429)
    respuesta.headers['Retry-After'] = str(espera_s)
    return respuesta


class EnlaceChoferes(http.Controller):

    def _entrada(self, token, en_json):
        """Los límites por minuto y el enlace. Devuelve la respuesta de rechazo, o ``None`` si se sigue."""
        seguidas = 'Muchas búsquedas seguidas: espera un minuto y vuelve a intentar.'
        if excede(llave_ip(request.httprequest.remote_addr)):
            return _demasiado(seguidas, ESPERA_S, en_json)
        if not request.env['dcasa.envio.tarifa'].sudo()._choferes_enlace_vale(token):
            return _no_existe()
        # El límite entre todas las IP cuenta solo a quien tiene el enlace: sin él nadie se lo gasta a los choferes.
        if excede(TODOS, maximo=MAX_TODOS_POR_MINUTO):
            return _demasiado(seguidas, ESPERA_S, en_json)
        return None

    def _del_dia(self, token):
        """El tope diario del enlace: ``None`` si la búsqueda cabe; si no, el 429 (y la nota a Gerencia, una vez)."""
        permitida, avisar = contar_busqueda(token)
        if permitida:
            return None
        if avisar:
            _logger.warning('Enlace para choferes: llegó a %s búsquedas hoy; responde 429 hasta mañana.', MAX_POR_DIA)
            request.env['dcasa.envio.tarifa'].sudo()._choferes_aviso_de_tope(MAX_POR_DIA)
        return _demasiado('El enlace llegó a su límite de hoy: confirma el precio con la tienda.', 3600)

    def _cuerpo(self):
        """El JSON que manda la página (un objeto pequeño), o ``None``."""
        if (request.httprequest.content_length or 0) > MAX_CUERPO:
            return None
        crudo = request.httprequest.get_data()
        if len(crudo) > MAX_CUERPO:
            return None
        try:
            cuerpo = json.loads(crudo.decode('utf-8') or 'null')
        except (ValueError, UnicodeDecodeError, RecursionError):
            return None     # (RecursionError: miles de «[» anidados en 2 KB)
        return cuerpo if isinstance(cuerpo, dict) else None

    def _con_turno(self, buscar):
        """Corre ``buscar()`` si hay turno (a lo sumo ``MAX_A_LA_VEZ`` a la vez); si no, «ocupado» sin esperar."""
        if not _ocupado.acquire(blocking=False):
            return _demasiado('La calculadora está ocupada: intenta otra vez en unos segundos.', ESPERA_OCUPADO_S)
        try:
            return _json(buscar())
        finally:
            _ocupado.release()

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
            'con_ubicacion': request.env['dcasa.envio.tarifa'].sudo()._choferes_con_ubicacion(),
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

    @http.route(RUTA + '/buscar', type='http', auth='public', methods=['POST'], csrf=False, save_session=False,
                max_content_length=MAX_CUERPO)
    def buscar(self, token, **_parametros):
        rechazo = self._entrada(token, en_json=True)
        if rechazo:
            return rechazo
        cuerpo = self._cuerpo()
        texto = cuerpo.get('texto') if cuerpo else None
        if not isinstance(texto, str) or len(texto) > MAX_TEXTO or len(texto.split()) > MAX_PALABRAS:
            return _json({'error': f'Escribe solo el nombre del lugar (hasta {MAX_TEXTO} letras).'}, status=400)
        rechazo = self._del_dia(token)
        if rechazo:
            return rechazo
        return self._con_turno(lambda: request.env['dcasa.envio.lugar'].sudo()._choferes_buscar(texto))

    @http.route(RUTA + '/cerca', type='http', auth='public', methods=['POST'], csrf=False, save_session=False,
                max_content_length=MAX_CUERPO)
    def cerca(self, token, **_parametros):
        rechazo = self._entrada(token, en_json=True)
        if rechazo:
            return rechazo
        if not request.env['dcasa.envio.tarifa'].sudo()._choferes_con_ubicacion():
            return _no_existe()     # «Usar mi ubicación» apagado (de fábrica): como si no existiera
        cuerpo = self._cuerpo()
        ubicacion = choferes.ubicacion_valida(cuerpo.get('lat'), cuerpo.get('lon')) if cuerpo else None
        if not ubicacion:
            return _json({'error': 'No pudimos leer tu ubicación: busca el lugar por nombre.'}, status=400)
        rechazo = self._del_dia(token)
        if rechazo:
            return rechazo
        return self._con_turno(lambda: request.env['dcasa.envio.lugar'].sudo()._choferes_cerca(*ubicacion))
