"""Servidor MCP de Brian: ``POST /brian/mcp`` (MCP 2025-06-18, transporte Streamable HTTP).

* JSON-RPC 2.0, un mensaje por petición (la revisión 2025-06-18 eliminó los lotes: un
  arreglo se rechaza con ``-32600``). Respuestas ``application/json`` (sin SSE).
* ``GET`` y ``DELETE`` → 405: el servidor no abre flujos SSE ni guarda sesiones.
* Métodos: ``initialize``, ``ping``, ``tools/list``, ``tools/call`` y las notificaciones
  (``notifications/initialized``, ``notifications/cancelled``…) → 202 sin cuerpo.
* Autenticación en CADA petición: ``Authorization: Bearer <clave de API de Odoo>``
  (Preferencias → Seguridad → Claves de API). Vale una clave global o con alcance
  ``brian``. Sin clave válida → 401 con ``WWW-Authenticate``. Todo corre como ese usuario.
* Protección: tamaño de cuerpo (1 MB), límite de peticiones por usuario y de intentos
  fallidos por IP, validación de ``Origin`` (DNS rebinding) y de ``MCP-Protocol-Version``.

Acciones sensibles
------------------
``tools/call`` de una herramienta ``sensible`` NUNCA la ejecuta: la deja «por confirmar»
en ``brian.accion`` y responde ``isError: true`` con el resumen y el ``accion_id``. La
confirma un humano en el panel de Odoo o en Telegram (si el usuario tiene el chat
vinculado, le llegan los botones Confirmar / Cancelar al instante).

Solo si un administrador activa el parámetro ``dcasa_brian.mcp_permite_confirmar`` (por
defecto apagado), MCP publica además la herramienta ``confirmar_accion`` (marcada
``destructiveHint``), para clientes que piden aprobación humana en cada llamada. La
herramienta ``rechazar_accion`` está siempre: descartar nunca hace daño.
"""
import json
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from odoo import SUPERUSER_ID, http
from odoo.http import request
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)

VERSIONES = ('2025-06-18', '2025-03-26', '2024-11-05')
VERSION_ACTUAL = VERSIONES[0]
MAX_CUERPO = 1024 * 1024
MAX_PETICIONES_MINUTO = 120
MAX_FALLOS_IP_MINUTO = 20

INSTRUCCIONES = (
    "Brian es el asistente del ERP de D'CASA Panamá (Odoo). Las herramientas corren con los "
    "permisos del usuario dueño de la clave de API. Las de lectura no cambian nada; las de "
    "construcción crean o editan y quedan auditadas; las sensibles no se ejecutan aquí: quedan "
    "por confirmar y las aprueba una persona en el panel o en Telegram. Responde en español."
)

HERRAMIENTAS_MCP = {
    'rechazar_accion': {
        'name': 'rechazar_accion',
        'title': 'Rechazar acción pendiente',
        'description': 'Descarta una acción sensible que quedó por confirmar. Ejemplo: {"accion_id": 42}.',
        'inputSchema': {'type': 'object', 'properties': {'accion_id': {'type': 'integer'}},
                        'required': ['accion_id'], 'additionalProperties': False},
        'annotations': {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': True,
                        'openWorldHint': False},
    },
    'confirmar_accion': {
        'name': 'confirmar_accion',
        'title': 'Confirmar acción sensible',
        'description': ('Ejecuta una acción sensible que quedó por confirmar. Úsala SOLO si la persona '
                        'lo aprobó explícitamente. Ejemplo: {"accion_id": 42}.'),
        'inputSchema': {'type': 'object', 'properties': {'accion_id': {'type': 'integer'}},
                        'required': ['accion_id'], 'additionalProperties': False},
        'annotations': {'readOnlyHint': False, 'destructiveHint': True, 'idempotentHint': False,
                        'openWorldHint': False},
    },
}

_candado = threading.Lock()
_ventanas = defaultdict(deque)


def _excede(clave, maximo, ventana=60):
    ahora = time.monotonic()
    with _candado:
        cola = _ventanas[clave]
        while cola and cola[0] < ahora - ventana:
            cola.popleft()
        if len(cola) >= maximo:
            return True
        cola.append(ahora)
        return False


def _compacto(datos):
    return json.dumps(datos, ensure_ascii=False, separators=(',', ':'), default=str)


class _Rechazo(Exception):
    def __init__(self, estado, codigo, mensaje, id_=None, encabezados=None):
        super().__init__(mensaje)
        self.estado, self.codigo, self.mensaje, self.id_ = estado, codigo, mensaje, id_
        self.encabezados = encabezados or {}


class BrianMCP(http.Controller):

    # ------------------------------------------------------------------
    # Transporte
    # ------------------------------------------------------------------

    def _responder(self, cuerpo=None, estado=200, encabezados=None):
        cabeceras = [('Cache-Control', 'no-store')]
        cabeceras += list((encabezados or {}).items())
        if cuerpo is None:
            return request.make_response('', headers=cabeceras, status=estado)
        cabeceras.append(('Content-Type', 'application/json; charset=utf-8'))
        return request.make_response(_compacto(cuerpo), headers=cabeceras, status=estado)

    def _error(self, id_, codigo, mensaje, estado=200, encabezados=None):
        return self._responder({'jsonrpc': '2.0', 'id': id_, 'error': {'code': codigo, 'message': mensaje}},
                               estado, encabezados)

    @http.route('/brian/mcp', type='http', auth='none', methods=['GET', 'DELETE'], csrf=False,
                save_session=False)
    def no_permitido(self, **_kw):
        return self._responder({'error': 'Este servidor MCP solo acepta POST (sin SSE ni sesiones).'},
                               405, {'Allow': 'POST'})

    @http.route('/brian/mcp', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def mcp(self, **_kw):
        try:
            self._validar_origen()
            usuario = self._autenticar()
            mensaje = self._leer()
        except _Rechazo as rechazo:
            return self._error(rechazo.id_, rechazo.codigo, rechazo.mensaje, rechazo.estado, rechazo.encabezados)

        if not isinstance(mensaje, dict) or mensaje.get('jsonrpc') != '2.0':
            return self._error(None, -32600, 'Petición JSON-RPC 2.0 inválida.', 400)
        if 'method' not in mensaje:
            return self._responder(estado=202)   # respuesta del cliente: no esperamos ninguna
        if 'id' not in mensaje:
            return self._responder(estado=202)   # notificación (initialized, cancelled…)

        id_, metodo, params = mensaje['id'], mensaje['method'], mensaje.get('params') or {}
        version = request.httprequest.headers.get('MCP-Protocol-Version')
        if metodo != 'initialize' and version and version not in VERSIONES:
            return self._error(id_, -32600, f'Versión de protocolo MCP no soportada: {version}.', 400)
        if _excede(('uid', usuario.id), MAX_PETICIONES_MINUTO):
            return self._error(id_, -32000, 'Demasiadas peticiones: espera un minuto.', 429, {'Retry-After': '60'})
        if not isinstance(params, dict):
            return self._error(id_, -32602, 'params debe ser un objeto.')

        try:
            resultado = self._despachar(metodo, params)
        except _Rechazo as rechazo:
            return self._error(id_, rechazo.codigo, rechazo.mensaje)
        encabezados = {'Mcp-Session-Id': secrets.token_urlsafe(24)} if metodo == 'initialize' else {}
        return self._responder({'jsonrpc': '2.0', 'id': id_, 'result': resultado}, encabezados=encabezados)

    def _despachar(self, metodo, params):
        if metodo == 'initialize':
            return self._initialize(params)
        if metodo == 'ping':
            return {}
        if metodo == 'tools/list':
            return {'tools': self._herramientas()}
        if metodo == 'tools/call':
            return self._llamar(params)
        raise _Rechazo(200, -32601, f'Método no soportado: {metodo}.')

    def _validar_origen(self):
        origen = request.httprequest.headers.get('Origin')
        if not origen:
            return
        parametros = request.env(user=SUPERUSER_ID)['ir.config_parameter']
        permitidos = {urlsplit(parametros.get_param('web.base.url') or '').netloc}
        permitidos |= {urlsplit(o.strip()).netloc for o in
                       (parametros.get_param('dcasa_brian.mcp_origenes') or '').split(',') if o.strip()}
        if urlsplit(origen).netloc not in permitidos - {''}:
            raise _Rechazo(403, -32600, 'Origen no permitido.')

    def _autenticar(self):
        ip = request.httprequest.remote_addr or '-'
        encabezado = request.httprequest.headers.get('Authorization') or ''
        esquema, _, clave = encabezado.partition(' ')
        clave = clave.strip()
        desafio = 'Bearer realm="brian-mcp"'
        if esquema.lower() != 'bearer' or not clave:
            raise _Rechazo(401, -32001, 'Falta la clave de API: Authorization: Bearer <clave>.',
                           encabezados={'WWW-Authenticate': desafio})
        with _candado:
            fallos = sum(1 for t in _ventanas[('fallo', ip)] if t > time.monotonic() - 60)
        if fallos >= MAX_FALLOS_IP_MINUTO:
            raise _Rechazo(429, -32000, 'Demasiados intentos fallidos: espera un minuto.',
                           encabezados={'Retry-After': '60'})
        env = request.env(user=SUPERUSER_ID)
        uid = env['res.users.apikeys']._check_credentials(scope='brian', key=clave)
        usuario = env['res.users'].browse(uid).exists() if uid else env['res.users']
        if not usuario or not usuario.active or not usuario._is_internal():
            _excede(('fallo', ip), 10 ** 6)   # solo registra el fallo
            _logger.info('Brian/MCP: clave de API rechazada desde %s', ip)
            raise _Rechazo(401, -32001, 'Clave de API inválida o vencida.',
                           encabezados={'WWW-Authenticate': desafio + ', error="invalid_token"'})
        request.update_env(user=usuario.id)
        request.update_context(lang=usuario.lang, tz=usuario.tz)
        return request.env.user

    def _leer(self):
        largo = request.httprequest.content_length
        if largo and largo > MAX_CUERPO:
            raise _Rechazo(413, -32600, 'El mensaje es demasiado grande (máximo 1 MB).')
        crudo = request.httprequest.get_data(cache=False)
        if len(crudo) > MAX_CUERPO:
            raise _Rechazo(413, -32600, 'El mensaje es demasiado grande (máximo 1 MB).')
        try:
            mensaje = json.loads(crudo or b'null')
        except ValueError:
            raise _Rechazo(400, -32700, 'JSON inválido.') from None
        if isinstance(mensaje, list):
            raise _Rechazo(400, -32600, 'Los lotes JSON-RPC no están soportados (MCP 2025-06-18): '
                                        'envía un mensaje por petición.')
        return mensaje

    # ------------------------------------------------------------------
    # Métodos
    # ------------------------------------------------------------------

    def _initialize(self, params):
        pedida = params.get('protocolVersion')
        return {
            'protocolVersion': pedida if pedida in VERSIONES else VERSION_ACTUAL,
            'capabilities': {'tools': {'listChanged': False}},
            'serverInfo': {'name': 'brian-dcasa', 'title': "Brian — D'CASA Panamá", 'version': '19.0.1.0.0'},
            'instructions': INSTRUCCIONES,
        }

    def _permite_confirmar(self):
        valor = request.env(user=SUPERUSER_ID)['ir.config_parameter'].get_param('dcasa_brian.mcp_permite_confirmar')
        return str2bool(valor or 'False', default=False)

    def _extras(self):
        extras = [HERRAMIENTAS_MCP['rechazar_accion']]
        if self._permite_confirmar():
            extras.append(HERRAMIENTAS_MCP['confirmar_accion'])
        return extras

    def _herramientas(self):
        herramientas = []
        for esquema in request.env['brian.herramientas'].catalogo():
            nivel = esquema.get('nivel')
            herramientas.append({
                'name': esquema['name'],
                'title': esquema['name'].replace('_', ' ').capitalize(),
                'description': esquema['description'] + (
                    ' (Sensible: queda por confirmar en el panel o en Telegram.)' if nivel == 'sensible' else ''),
                'inputSchema': esquema['input_schema'],
                'annotations': {
                    'readOnlyHint': nivel == 'lectura',
                    'destructiveHint': nivel == 'sensible',
                    'idempotentHint': nivel == 'lectura',
                    'openWorldHint': False,
                },
            })
        return herramientas + self._extras()

    def _resultado(self, datos, error=False):
        salida = {'content': [{'type': 'text', 'text': _compacto(datos)}], 'isError': error}
        if isinstance(datos, dict):
            salida['structuredContent'] = datos
        return salida

    def _llamar(self, params):
        nombre = params.get('name')
        argumentos = params.get('arguments') or {}
        if not isinstance(nombre, str) or not isinstance(argumentos, dict):
            raise _Rechazo(200, -32602, 'tools/call necesita name (texto) y arguments (objeto).')
        Herramientas = request.env['brian.herramientas']
        extras = {h['name'] for h in self._extras()}
        if nombre in extras:
            accion_id = argumentos.get('accion_id')
            if not isinstance(accion_id, int) or isinstance(accion_id, bool):
                return self._resultado({'ok': False, 'error': 'accion_id debe ser un número entero.'}, True)
            if nombre == 'rechazar_accion':
                return self._resultado(Herramientas.rechazar(accion_id))
            resultado = Herramientas.confirmar(accion_id)
            return self._resultado(resultado, not resultado.get('ok'))
        if nombre not in {h['name'] for h in Herramientas.catalogo()}:
            raise _Rechazo(200, -32602, f'Herramienta desconocida: {nombre}.')

        resultado = Herramientas.ejecutar(nombre, argumentos, canal='mcp')
        if resultado.get('ok'):
            return self._resultado(resultado.get('datos') or {})
        if resultado.get('requiere_confirmacion'):
            aviso = self._avisar_telegram(resultado)
            donde = 'en Telegram (te llegó el aviso) o en el panel' if aviso else 'en el panel de Odoo'
            return self._resultado({
                'ok': False,
                'requiere_confirmacion': True,
                'accion_id': resultado['accion_id'],
                'resumen': resultado.get('resumen'),
                'mensaje': (f'Acción sensible: no se ejecutó. Una persona debe confirmarla {donde}. '
                            f'Resumen: {resultado.get("resumen")}'),
            }, True)
        return self._resultado({'ok': False, 'error': resultado.get('error')}, True)

    def _avisar_telegram(self, resultado):
        try:
            with request.env.cr.savepoint():
                return request.env['brian.telegram.enlace'].notificar_confirmacion(
                    request.env.user, resultado['accion_id'], resultado.get('resumen') or '')
        except Exception:  # noqa: BLE001 — el aviso es opcional
            _logger.exception('Brian/MCP: no se pudo avisar por Telegram')
            return False
