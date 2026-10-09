"""API de Juan para el Worker: ``/dcasa/juan/v1/*`` (contrato: docs/JUAN.md, «Worker → Odoo»).

* ``POST /mensaje``            — registrar un mensaje (idempotente por ``id_mensaje``).
* ``GET  /estado``             — ¿puede contestar el bot ahora? (el Worker lo pregunta justo antes de enviar).
* ``GET  /config``             — la configuración que edita la dueña.
* ``GET  /herramientas``       — definición de las herramientas (fuente única).
* ``POST /herramienta``        — ejecutar una herramienta como el usuario técnico ``juan``.
* ``POST /seguimiento/hecho``  — el Worker confirma que envió (o descartó) un seguimiento.

Seguridad
---------
* ``Authorization: Bearer <JUAN_ODOO_TOKEN>``, comparado en tiempo constante (se comparan los SHA-256, de
  largo fijo). El token vive en la variable de entorno (o en un parámetro del sistema) y **nunca** se
  escribe en un registro, un mensaje de error ni el repositorio.
* Sin token configurado (o de menos de 32 caracteres) TODAS las rutas responden **503**.
* Los intentos fallidos se frenan (429). Las rutas están bloqueadas desde internet por el borde
  (``edge/src/routing.ts``) y solo se alcanzan por el service binding del Worker ``dcasa``.
* Límites de tamaño, validación estricta de cada campo y errores JSON ``{ok: false, error}`` con el código HTTP
  correcto. Nada de lo que escribe el cliente se interpreta como instrucción: es dato.
"""
import hashlib
import hmac
import json
import logging
import re
import threading
import time
from collections import defaultdict, deque

from odoo import SUPERUSER_ID, fields, http
from odoo.exceptions import ConcurrencyError
from odoo.http import request
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY

from ..models import adjuntos as A
from ..models import horario as H
from ..models.ajustes import CANALES

_logger = logging.getLogger(__name__)

RAIZ = '/dcasa/juan/v1'
MAX_CUERPO = 256 * 1024
MAX_CUERPO_MENSAJE = 14 * 1024 * 1024   # un mensaje con adjuntos en base64
MAX_TEXTO = 10000
MAX_FALLOS_POR_MINUTO = 30
PREFIJO_HERRAMIENTA = 'juan_'
CANALES_VALIDOS = {canal for canal, _nombre in CANALES}
DIRECCIONES = {'entrante': {'cliente'}, 'saliente': {'bot', 'vendedora'}}
RE_ID_EXTERNO = re.compile(r'^[A-Za-z0-9_.:@+\-]{1,128}$')
RE_ID_MENSAJE = re.compile(r'^[\x21-\x7e]{1,255}$')
TOLERANCIA_RELOJ = 600   # segundos hacia el futuro que se aceptan en «ts»

_candado = threading.Lock()
_fallos = defaultdict(deque)


class _Error(Exception):
    def __init__(self, estado, mensaje, encabezados=None):
        super().__init__(mensaje)
        self.estado, self.mensaje, self.encabezados = estado, mensaje, encabezados or {}


def _respuesta(datos, estado=200, encabezados=None):
    cabeceras = [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store'),
                 ('X-Content-Type-Options', 'nosniff')] + list((encabezados or {}).items())
    return request.make_response(json.dumps(datos, ensure_ascii=False, separators=(',', ':'), default=str),
                                 headers=cabeceras, status=estado)


def _fallos_recientes(ip, ahora):
    with _candado:
        cola = _fallos[ip]
        while cola and cola[0] < ahora - 60:
            cola.popleft()
        return len(cola)


def _anotar_fallo(ip, ahora):
    with _candado:
        _fallos[ip].append(ahora)


def _huella(texto):
    return hashlib.sha256(texto.encode('utf-8')).digest()


def _texto_opcional(valor, maximo, nombre):
    if valor is None:
        return None
    if not isinstance(valor, str) or len(valor) > maximo:
        raise _Error(400, f'«{nombre}» debe ser un texto de hasta {maximo} caracteres.')
    return valor


def _id_externo(valor, canal):
    if isinstance(valor, int) and not isinstance(valor, bool):
        valor = str(valor)
    if not isinstance(valor, str) or not RE_ID_EXTERNO.match(valor):
        raise _Error(400, '«id_externo» es obligatorio: celular (WhatsApp), chat_id (Telegram) o PSID/IGSID.')
    if canal in ('whatsapp_qr', 'whatsapp_cloud') and not re.fullmatch(r'\d{6,20}', valor):
        raise _Error(400, 'En WhatsApp «id_externo» es el celular en formato E.164 sin «+», p. ej. 50760261919.')
    return valor


def _canal(valor):
    if valor not in CANALES_VALIDOS:
        raise _Error(400, f'«canal» debe ser uno de: {", ".join(sorted(CANALES_VALIDOS))}.')
    return valor


class JuanAPI(http.Controller):

    # ------------------------------------------------------------------
    # Entrada común: autenticación, lectura del cuerpo y manejo de errores
    # ------------------------------------------------------------------

    def _autenticar(self):
        entorno = request.env(user=SUPERUSER_ID)
        esperado = entorno['dcasa.juan.ajustes'].token_odoo()
        if not esperado:
            raise _Error(503, 'Juan no está configurado en Odoo: falta JUAN_ODOO_TOKEN (32 caracteres o más).')
        ip = request.httprequest.remote_addr or '-'
        ahora = time.monotonic()
        if _fallos_recientes(ip, ahora) >= MAX_FALLOS_POR_MINUTO:
            raise _Error(429, 'Demasiados intentos fallidos: espera un minuto.', {'Retry-After': '60'})
        esquema, _, token = (request.httprequest.headers.get('Authorization') or '').partition(' ')
        if esquema.lower() != 'bearer' or not hmac.compare_digest(_huella(token.strip()), _huella(esperado)):
            _anotar_fallo(ip, ahora)
            _logger.info('Juan/API: petición rechazada por token inválido (desde %s).', ip)
            raise _Error(401, 'Token inválido o ausente.', {'WWW-Authenticate': 'Bearer realm="juan"'})
        usuario = entorno.ref('dcasa_conversaciones.user_juan')
        request.update_env(user=usuario.id)
        return request.env

    def _cuerpo(self, maximo=MAX_CUERPO):
        largo = request.httprequest.content_length
        if largo and largo > maximo:
            raise _Error(413, f'El cuerpo es demasiado grande (máximo {maximo // 1024} KB).')
        # Con caché: si Odoo repite la petición por un choque entre transacciones (ver ``_servir``), se vuelve a leer.
        crudo = request.httprequest.get_data()
        if len(crudo) > maximo:
            raise _Error(413, f'El cuerpo es demasiado grande (máximo {maximo // 1024} KB).')
        try:
            cuerpo = json.loads(crudo.decode('utf-8') or 'null')
        except (ValueError, UnicodeDecodeError):
            raise _Error(400, 'El cuerpo no es un JSON válido (UTF-8).') from None
        if not isinstance(cuerpo, dict):
            raise _Error(400, 'El cuerpo debe ser un objeto JSON.')
        return cuerpo

    def _servir(self, funcion):
        """Autentica, ejecuta y convierte cualquier fallo en JSON. Un error inesperado deshace la transacción."""
        try:
            entorno = self._autenticar()
            return funcion(entorno)
        except _Error as error:
            return _respuesta({'ok': False, 'error': error.mensaje}, error.estado, error.encabezados)
        except (ConcurrencyError, *PG_CONCURRENCY_EXCEPTIONS_TO_RETRY):
            # Dos transacciones tocaron la misma fila a la vez (Postgres: «could not serialize access»). No es un error
            # del Worker ni de este mensaje: si sube, Odoo repite TODA la petición con una espera (hasta 5 veces).
            # Si lo convirtiéramos en un 500, el mensaje o la herramienta fallarían al azar.
            raise
        except Exception:   # noqa: BLE001 — la API siempre contesta JSON
            _logger.exception('Juan/API: error inesperado')
            request.env.cr.rollback()
            return _respuesta({'ok': False, 'error': 'Error interno de Odoo; quedó en el registro del servidor.'}, 500)

    # ------------------------------------------------------------------
    # POST /mensaje
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/mensaje', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def mensaje(self, **_kw):
        return self._servir(self._registrar_mensaje)

    def _registrar_mensaje(self, entorno):
        cuerpo = self._cuerpo(MAX_CUERPO_MENSAJE)
        canal = _canal(cuerpo.get('canal'))
        id_mensaje = cuerpo.get('id_mensaje')
        if not isinstance(id_mensaje, str) or not RE_ID_MENSAJE.match(id_mensaje):
            raise _Error(400, '«id_mensaje» es obligatorio (texto sin espacios, hasta 255 caracteres).')
        direccion, autor = cuerpo.get('direccion'), cuerpo.get('autor')
        if direccion not in DIRECCIONES:
            raise _Error(400, '«direccion» debe ser «entrante» o «saliente».')
        if autor not in DIRECCIONES[direccion]:
            raise _Error(400, 'Un mensaje entrante es del «cliente»; uno saliente, del «bot» o de la «vendedora».')
        texto = _texto_opcional(cuerpo.get('texto'), MAX_TEXTO, 'texto')
        try:
            adjuntos = A.validar_lista(cuerpo.get('adjuntos'))
        except A.AdjuntoInvalido as error:
            raise _Error(400, str(error)) from None
        if not (texto or '').strip() and not adjuntos:
            raise _Error(400, 'El mensaje necesita «texto» o «adjuntos».')
        ahora = fields.Datetime.now()
        ts = ahora
        if cuerpo.get('ts') is not None:
            try:
                ts = H.de_iso(cuerpo['ts'])
            except (ValueError, TypeError):
                raise _Error(400, '«ts» debe ser una fecha ISO 8601, p. ej. 2026-10-09T14:03:00Z.') from None
            if (ts - ahora).total_seconds() > TOLERANCIA_RELOJ:
                ts = ahora   # reloj adelantado: no se acepta un mensaje «del futuro»
        datos = {
            'canal': canal, 'id_externo': _id_externo(cuerpo.get('id_externo'), canal), 'id_mensaje': id_mensaje,
            'direccion': direccion, 'autor': autor, 'texto': (texto or '').strip() or None, 'ts': ts,
            'nombre': (_texto_opcional(cuerpo.get('nombre'), 200, 'nombre') or '').strip() or None,
            'celular': (_texto_opcional(cuerpo.get('celular'), 40, 'celular') or '').strip() or None,
            'adjuntos': adjuntos,
        }
        conversacion, mensaje, _creado = entorno['dcasa.conversacion']._registrar_mensaje(datos)
        estado = conversacion._estado_para_worker()
        respuesta = {'ok': True, 'conversacion_id': conversacion.id, 'partner_id': conversacion.partner_id.id,
                     'estado': estado['estado'], 'bot_activo': estado['bot_activo'],
                     'pausada_hasta': estado['pausada_hasta'], 'dentro_de_horario': estado['dentro_de_horario'],
                     'nota_para_el_bot': estado['nota_para_el_bot']}
        if adjuntos:
            respuesta['adjuntos'] = [
                {'id': a.id, 'nombre': a.name, 'sensible': bool(a.dcasa_sensible)} for a in mensaje.adjunto_ids.sudo()]
        return _respuesta(respuesta)

    # ------------------------------------------------------------------
    # GET /estado
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/estado', type='http', auth='none', methods=['GET'], csrf=False, save_session=False,
                readonly=False)
    def estado(self, canal=None, id_externo=None, **_kw):
        return self._servir(lambda entorno: self._estado(entorno, canal, id_externo))

    def _estado(self, entorno, canal, id_externo):
        canal = _canal(canal)
        id_externo = _id_externo(id_externo, canal)
        Conversacion = entorno['dcasa.conversacion'].sudo()
        conversacion = Conversacion.search([('canal', '=', canal), ('id_externo', '=', id_externo)], limit=1)
        if conversacion:
            conversacion._normalizar_pausa()
            datos = conversacion._estado_para_worker()
        else:
            datos = Conversacion._estado_sin_conversacion(canal)
        return _respuesta({'ok': True, **datos})

    # ------------------------------------------------------------------
    # GET /config
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/config', type='http', auth='none', methods=['GET'], csrf=False, save_session=False,
                readonly=False)
    def config(self, **_kw):
        return self._servir(lambda entorno: _respuesta(
            {'ok': True, **entorno['dcasa.juan.ajustes'].obtener().como_json()}))

    # ------------------------------------------------------------------
    # GET /herramientas  y  POST /herramienta
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/herramientas', type='http', auth='none', methods=['GET'], csrf=False, save_session=False,
                readonly=False)
    def herramientas(self, **_kw):
        return self._servir(lambda entorno: _respuesta({'ok': True, 'herramientas': self._catalogo(entorno)}))

    @staticmethod
    def _catalogo(entorno):
        """Las herramientas del usuario ``juan`` con el nombre público (sin el prefijo ``juan_``).

        Cada una lleva los nombres del contrato (``nombre``, ``descripcion``, ``parametros``) y los del formato de
        herramientas de Anthropic (``name``, ``description``, ``input_schema``); el Worker toma los que use.
        """
        herramientas = []
        for esquema in entorno['brian.herramientas'].catalogo():
            if not esquema['name'].startswith(PREFIJO_HERRAMIENTA):
                continue
            publico = esquema['name'][len(PREFIJO_HERRAMIENTA):]
            herramientas.append({
                'nombre': publico, 'descripcion': esquema['description'], 'parametros': esquema['input_schema'],
                'name': publico, 'description': esquema['description'], 'input_schema': esquema['input_schema'],
            })
        return herramientas

    @http.route(f'{RAIZ}/herramienta', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def herramienta(self, **_kw):
        return self._servir(self._ejecutar_herramienta)

    def _ejecutar_herramienta(self, entorno):
        cuerpo = self._cuerpo()
        nombre = cuerpo.get('nombre')
        if not isinstance(nombre, str) or not nombre:
            raise _Error(400, '«nombre» de la herramienta es obligatorio.')
        argumentos = cuerpo.get('argumentos', {})
        if argumentos is None:
            argumentos = {}
        if not isinstance(argumentos, dict):
            raise _Error(400, '«argumentos» debe ser un objeto.')
        if nombre not in {h['nombre'] for h in self._catalogo(entorno)}:
            raise _Error(404, f'No existe la herramienta «{nombre[:60]}».')
        conversacion_id = cuerpo.get('conversacion_id')
        contexto = {}
        if conversacion_id is not None:
            if not isinstance(conversacion_id, int) or isinstance(conversacion_id, bool):
                raise _Error(400, '«conversacion_id» debe ser un número entero.')
            if not entorno['dcasa.conversacion'].sudo().browse(conversacion_id).exists():
                raise _Error(404, 'No existe esa conversación.')
            contexto['juan_conversacion_id'] = conversacion_id
        resultado = entorno['brian.herramientas'].with_context(**contexto).ejecutar(
            PREFIJO_HERRAMIENTA + nombre, argumentos, canal='juan')
        if resultado.get('ok'):
            return _respuesta({'ok': True, 'resultado': resultado.get('datos') or {}})
        if resultado.get('requiere_confirmacion'):
            return _respuesta({'ok': False, 'error': 'Esa herramienta necesita confirmación de una persona.'}, 409)
        return _respuesta({'ok': False, 'error': resultado.get('error') or 'No se pudo ejecutar la herramienta.'}, 422)

    # ------------------------------------------------------------------
    # POST /seguimiento/hecho
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/seguimiento/hecho', type='http', auth='none', methods=['POST'], csrf=False,
                save_session=False, readonly=False)
    def seguimiento_hecho(self, **_kw):
        return self._servir(self._seguimiento_hecho)

    def _seguimiento_hecho(self, entorno):
        cuerpo = self._cuerpo()
        conversacion_id, numero = cuerpo.get('conversacion_id'), cuerpo.get('numero')
        resultado = cuerpo.get('resultado')
        if not isinstance(conversacion_id, int) or isinstance(conversacion_id, bool):
            raise _Error(400, '«conversacion_id» debe ser un número entero.')
        if numero not in (1, 2) or isinstance(numero, bool):
            raise _Error(400, '«numero» debe ser 1 o 2.')
        if resultado not in ('enviado', 'descartado'):
            raise _Error(400, '«resultado» debe ser «enviado» o «descartado».')
        motivo = _texto_opcional(cuerpo.get('motivo'), 200, 'motivo')
        conversacion = entorno['dcasa.conversacion'].sudo().browse(conversacion_id).exists()
        if not conversacion:
            raise _Error(404, 'No existe esa conversación.')
        conversacion._seguimiento_hecho(numero, resultado, motivo)
        return _respuesta({'ok': True, 'conversacion_id': conversacion.id,
                           'seguimientos_enviados': conversacion.seguimientos_enviados})
