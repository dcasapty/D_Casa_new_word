"""API de Juan para el Worker: ``/dcasa/juan/v1/*`` (contrato: docs/JUAN.md, «Worker → Odoo»).

* ``POST /mensaje``            — registrar un mensaje (idempotente por ``id_mensaje``).
* ``GET  /estado``             — ¿puede contestar el bot ahora? (el Worker lo pregunta justo antes de enviar).
* ``GET  /config``             — la configuración que edita la dueña.
* ``GET  /herramientas``       — definición de las herramientas (fuente única).
* ``POST /herramienta``        — ejecutar una herramienta como el usuario técnico ``juan``.
* ``POST /seguimiento/hecho``  — el Worker confirma que envió (o descartó) un seguimiento.
* ``POST /escribiendo``        — el asistente empezó (o terminó) de preparar una respuesta: la pantalla lo muestra.
* ``POST /foto-perfil``        — la foto de perfil de quien escribe (base64), para el avatar de la pantalla.
* ``POST /eventos``            — palomitas (enviado, entregado, leído, no llegó) y reacciones del cliente, en tandas.
* ``POST /comentario``         — un comentario de Instagram o Facebook que Juan atendió: el aviso en el hilo y, si es
  una queja, Telegram a Gerencia (idempotente por red e id del comentario; ver ``models/comentario.py``).

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
from urllib.parse import urlsplit

from odoo import SUPERUSER_ID, fields, http
from odoo.exceptions import ConcurrencyError
from odoo.http import request
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY

from ..models import adjuntos as A
from ..models import crm_reglas as R
from ..models import horario as H
from ..models.ajustes import CANALES
from ..models.comentario import CLASES as _CLASES_DE_COMENTARIO
from ..models.comentario import RESPUESTA_PRIVADA, RESPUESTA_PUBLICA
from ..models.mensaje import MAX_PARTES, MAX_TEXTO_CITA, RANGO_CANAL
from ..models.mensaje import TIPOS_DE_PARTE as _TIPOS_DE_PARTE

_logger = logging.getLogger(__name__)

RAIZ = '/dcasa/juan/v1'
MAX_CUERPO = 256 * 1024
MAX_CUERPO_MENSAJE = 14 * 1024 * 1024   # un mensaje con adjuntos en base64
MAX_CUERPO_FOTO = 512 * 1024            # una foto de perfil (hasta 300 KB) en base64
MAX_TEXTO = 10000
MAX_FALLOS_POR_MINUTO = 30
PREFIJO_HERRAMIENTA = 'juan_'
CANALES_VALIDOS = {canal for canal, _nombre in CANALES}
DIRECCIONES = {'entrante': {'cliente'}, 'saliente': {'bot', 'vendedora'}}
RE_ID_EXTERNO = re.compile(r'^[A-Za-z0-9_.:@+\-]{1,128}$')
RE_ID_MENSAJE = re.compile(r'^[\x21-\x7e]{1,255}$')
TOLERANCIA_RELOJ = 600   # segundos hacia el futuro que se aceptan en «ts»
MAX_EVENTOS = 100        # palomitas y reacciones por petición (una tanda por aviso del canal)
MAX_EMOJI = 32
ESTADOS_DE_EVENTO = frozenset(RANGO_CANAL)
TIPOS_DE_PARTE = dict(_TIPOS_DE_PARTE)
# Comentarios: la red y el canal por el que va la respuesta privada (Facebook → Messenger).
CANAL_DE_LA_RED = {'facebook': 'messenger', 'instagram': 'instagram'}
RE_ID_COMENTARIO = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
# El anfitrión ENTERO (sin usuario, clave ni puerto): letras, cifras y guiones por partes, y que termine en uno de Meta.
RE_HOST_DE_META = re.compile(r'^(?:[a-z0-9-]+\.)*(?:facebook\.com|instagram\.com|fb\.com|fb\.me)$', re.IGNORECASE)
MAX_TEXTO_COMENTARIO = 2000
# «Brian de la tienda» (el chat de la web, dcasa_brian_tienda): el Worker llama con ``origen: "tienda"`` y sin
# conversación, y solo puede usar las herramientas de LEER de esta lista blanca (contrato §5). El Worker ya corta las
# demás; Odoo lo vuelve a exigir.
ORIGEN_TIENDA = 'tienda'
HERRAMIENTAS_DE_LA_TIENDA = frozenset({
    'buscar_productos', 'ver_producto', 'listar_categorias', 'buscar_conocimiento', 'horario_y_tienda',
    'reglas_socios', 'cotizar_envio',
})

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


# Lo que no se puede guardar o engaña a la vista (revisión 2026-11-07): un sustituto UTF-16 suelto (un emoji cortado a
# la mitad) hace fallar a PostgreSQL al guardar, y los controles bidi (U+202E…) dan vuelta el texto en la pantalla.
RE_NO_GUARDABLE = re.compile(r'[\ud800-\udfff\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c]')


def _texto_libre(valor, maximo):
    """Un texto opcional del canal (lo citado en Telegram, el error de WhatsApp): recortado y sin saltos; si no es
    texto, nada. Lo que no se entiende se ignora: un dato de más nunca hace perder el mensaje del cliente."""
    if not isinstance(valor, str):
        return None
    return ' '.join(RE_NO_GUARDABLE.sub('', valor).split())[:maximo] or None


def _cita(valor):
    """``cita: {id_canal, texto?}``: el mensaje que el cliente citó. Mal formada, se ignora (el mensaje entra igual)."""
    if not isinstance(valor, dict):
        return None
    id_canal = valor.get('id_canal')
    if not isinstance(id_canal, str) or not RE_ID_MENSAJE.match(id_canal):
        return None
    return {'id_canal': id_canal, 'texto': _texto_libre(valor.get('texto'), MAX_TEXTO_CITA)}


def _reenviado(valor):
    return valor if valor in ('una', 'muchas') else None


def _partes(valor):
    """``partes: [{id_canal, tipo, texto}]``: los ids que el canal dio a cada burbuja o archivo de un mensaje
    nuestro."""
    if not isinstance(valor, list):
        return None
    partes = []
    for parte in valor[:MAX_PARTES]:
        if not isinstance(parte, dict):
            continue
        id_canal = parte.get('id_canal')
        if not isinstance(id_canal, str) or not RE_ID_MENSAJE.match(id_canal):
            continue
        tipo = parte.get('tipo') if parte.get('tipo') in TIPOS_DE_PARTE else 'texto'
        partes.append({'id_canal': id_canal, 'tipo': tipo, 'texto': _texto_libre(parte.get('texto'), MAX_TEXTO_CITA)})
    return partes or None


def _emoji(valor):
    """Una reacción: un emoji (unas pocas letras sin espacios ni letras ASCII). ``''`` = el cliente la quitó."""
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    if valor == '':
        return ''
    if len(valor) > MAX_EMOJI or re.search(r'[\sA-Za-z<>&"\'\\\x00-\x1f\x7f]', valor) or RE_NO_GUARDABLE.search(valor):
        return None
    return valor


def _evento(crudo):
    """Un aviso del canal validado: ``{tipo, canal, id_externo, id_mensaje, ts, estado|emoji, error?}`` o ``None``."""
    if not isinstance(crudo, dict):
        return None
    tipo = crudo.get('tipo')
    if tipo not in ('estado', 'reaccion'):
        return None
    try:
        canal = _canal(crudo.get('canal'))
        id_externo = _id_externo(crudo.get('id_externo'), canal)
    except _Error:
        return None
    id_mensaje = crudo.get('id_mensaje')
    if not isinstance(id_mensaje, str) or not RE_ID_MENSAJE.match(id_mensaje):
        return None
    ahora = fields.Datetime.now()
    ts = ahora
    if crudo.get('ts') is not None:
        try:
            ts = H.de_iso(crudo['ts'])
        except (ValueError, TypeError):
            return None
        if (ts - ahora).total_seconds() > TOLERANCIA_RELOJ:
            ts = ahora
    evento = {'tipo': tipo, 'canal': canal, 'id_externo': id_externo, 'id_mensaje': id_mensaje, 'ts': ts}
    if tipo == 'estado':
        if crudo.get('estado') not in ESTADOS_DE_EVENTO:
            return None
        evento['estado'] = crudo['estado']
        evento['error'] = _texto_libre(crudo.get('error'), 200)
    else:
        emoji = _emoji(crudo.get('emoji'))
        if emoji is None:
            return None
        evento['emoji'] = emoji
    return evento


def _enlace_de_meta(valor):
    """El enlace a la publicación comentada: solo https de Facebook o Instagram (nunca otra dirección); si no, nada.

    Se mira como lo mira un navegador, no como ``urlsplit``: el navegador toma «\\» como «/» (con
    ``https://evil.example\\@www.facebook.com/x`` iría a evil.example) y quita tabuladores y saltos. Por eso no se
    acepta ninguna «\\», espacio ni control, y el anfitrión (``netloc`` entero) tiene que ser de Meta, sin usuario,
    clave ni puerto."""
    if not isinstance(valor, str) or len(valor) > 500 or RE_NO_GUARDABLE.search(valor):
        return None
    if '\\' in valor or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in valor):
        return None
    try:
        partes = urlsplit(valor)
    except ValueError:
        return None
    if partes.scheme != 'https' or not RE_HOST_DE_META.match(partes.netloc or ''):
        return None
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
            # 2026-11-07, opcionales (un Juan viejo no los manda): cita, reenviado y los ids de cada burbuja nuestra.
            'cita': _cita(cuerpo.get('cita')) if direccion == 'entrante' else None,
            'reenviado': _reenviado(cuerpo.get('reenviado')) if direccion == 'entrante' else None,
            'partes': _partes(cuerpo.get('partes')) if direccion == 'saliente' else None,
        }
        conversacion, mensaje, _creado = entorno['dcasa.conversacion']._registrar_mensaje(datos)
        # Todo lo de ``_estado_para_worker`` (estado, pausa, horario, nota y lo que agreguen otros módulos, como la
        # campaña de correo por la que llegó el cliente: ``campana_correo`` de dcasa_camila).
        respuesta = {'ok': True, 'conversacion_id': conversacion.id, 'partner_id': conversacion.partner_id.id,
                     **conversacion._estado_para_worker()}
        if adjuntos:
            respuesta['adjuntos'] = [
                {'id': a.id, 'nombre': a.name, 'sensible': bool(a.dcasa_sensible)} for a in mensaje.adjunto_ids.sudo()]
        if datos['cita']:
            # Lo que decía el mensaje citado, por si Juan no lo tiene en su memoria (es de antes): lo lee como un dato
            # que mandó el cliente, nunca como una orden.
            cita = mensaje.sudo()._cita_como_dict()
            if cita and cita['en_historial']:
                respuesta['cita'] = {'id_canal': datos['cita']['id_canal'], 'autor': cita['autor'],
                                     'texto': cita['texto']}
        return _respuesta(respuesta)

    # ------------------------------------------------------------------
    # POST /eventos (palomitas y reacciones: no son mensajes)
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/eventos', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def eventos(self, **_kw):
        return self._servir(self._eventos)

    def _eventos(self, entorno):
        """Lo que el canal avisa de un mensaje que ya existe: entregado, leído, no llegó, o la reacción del cliente.

        Una tanda por aviso del canal (hasta ``MAX_EVENTOS``): son muchos y tiene que ser barato. Un evento mal formado
        se ignora (se cuenta en ``invalidos``) sin tumbar a los demás. Nada de esto toca la actividad del cliente.
        """
        cuerpo = self._cuerpo()
        lista = cuerpo.get('eventos')
        if not isinstance(lista, list) or not lista:
            raise _Error(400, '«eventos» es obligatorio: una lista de avisos del canal.')
        if len(lista) > MAX_EVENTOS:
            raise _Error(413, f'Hasta {MAX_EVENTOS} eventos por petición.')
        validos, invalidos = [], 0
        for crudo in lista:
            evento = _evento(crudo)
            if evento:
                validos.append(evento)
            else:
                invalidos += 1
        resultado = entorno['dcasa.mensaje']._aplicar_eventos(validos) if validos else {
            'aplicados': 0, 'desconocidos': []}
        return _respuesta({'ok': True, **resultado, 'invalidos': invalidos})

    # ------------------------------------------------------------------
    # POST /comentario (Instagram y Facebook: no es un mensaje del cliente)
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/comentario', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def comentario(self, **_kw):
        return self._servir(self._comentario)

    def _comentario(self, entorno):
        """Un comentario de una publicación que Juan atendió (una pregunta, una queja o uno que la IA no pudo
        clasificar). Deja el aviso en el hilo de la conversación de esa persona y, si es una queja, avisa a Gerencia."""
        cuerpo = self._cuerpo()
        red = cuerpo.get('red')
        if red not in CANAL_DE_LA_RED:
            raise _Error(400, '«red» debe ser «facebook» o «instagram».')
        canal = _canal(cuerpo.get('canal'))
        if canal != CANAL_DE_LA_RED[red]:
            raise _Error(400, 'Un comentario de Facebook va con el canal «messenger»; uno de Instagram, con '
                              '«instagram».')
        id_comentario = cuerpo.get('id_comentario')
        if not isinstance(id_comentario, str) or not RE_ID_COMENTARIO.match(id_comentario):
            raise _Error(400, '«id_comentario» es obligatorio (el id del comentario en Meta).')
        texto = _texto_opcional(cuerpo.get('texto'), MAX_TEXTO_COMENTARIO, 'texto')
        texto = RE_NO_GUARDABLE.sub('', texto or '').strip()
        if not texto:
            raise _Error(400, '«texto» es obligatorio (lo que comentó la persona).')
        clase, privada, publica = cuerpo.get('clase'), cuerpo.get('privada'), cuerpo.get('publica')
        if clase not in dict(_CLASES_DE_COMENTARIO):
            raise _Error(400, '«clase» debe ser «pregunta», «queja» o «sin_clasificar».')
        if privada not in dict(RESPUESTA_PRIVADA) or publica not in dict(RESPUESTA_PUBLICA):
            raise _Error(400, '«privada» y «publica» dicen qué pasó con cada respuesta (p. ej. «respondida» o «no»).')
        ahora = fields.Datetime.now()
        ts = ahora
        if cuerpo.get('ts') is not None:
            try:
                ts = H.de_iso(cuerpo['ts'])
            except (ValueError, TypeError):
                raise _Error(400, '«ts» debe ser una fecha ISO 8601, p. ej. 2026-11-12T14:03:00Z.') from None
            if (ts - ahora).total_seconds() > TOLERANCIA_RELOJ:
                ts = ahora
        datos = {
            'canal': canal, 'id_externo': _id_externo(cuerpo.get('id_externo'), canal), 'red': red,
            'id_comentario': id_comentario, 'texto': texto, 'enlace': _enlace_de_meta(cuerpo.get('enlace')),
            'ts': ts, 'clase': clase, 'privada': privada, 'publica': publica,
            'nombre': _texto_libre(_texto_opcional(cuerpo.get('nombre'), 200, 'nombre'), 200),
            'motivo': _texto_libre(cuerpo.get('motivo'), 200),
        }
        comentario, que = entorno['dcasa.comentario']._registrar(datos)
        return _respuesta({'ok': True, 'conversacion_id': comentario.conversacion_id.id, 'comentario_id': comentario.id,
                           'repetido': que == 'repetido'})

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
        contexto = self._contexto_de_herramienta(entorno, cuerpo, nombre)
        if nombre == 'crear_oportunidad' and R.parece_direccion_exacta(argumentos.get('zona')):
            # Una dirección exacta no se guarda (issue #25): tampoco en la auditoría de Brian (``brian.accion``).
            argumentos = {clave: valor for clave, valor in argumentos.items() if clave != 'zona'}
        if nombre == 'cotizar_envio' and cuerpo.get('origen') == ORIGEN_TIENDA \
                and ('lat' in argumentos or 'lon' in argumentos):
            # Solo el chat de la tienda manda coordenadas (el botón «Usar mi ubicación»). A Juan no le sirven: no están
            # en el esquema y la herramienta las rechaza como parámetros que no existen.
            argumentos, directo = self._ubicacion_a_lugar(entorno, argumentos, contexto)
            if directo is not None:
                return _respuesta({'ok': True, 'resultado': directo})
        if nombre == 'cotizar_envio' and isinstance(argumentos.get('lugar'), str) \
                and R.parece_direccion_exacta(argumentos['lugar']):
            # Para el envío basta el barrio, el PH o el punto de referencia: el número de casa, apartamento o piso se
            # quita antes de buscar y de la auditoría (issue #25).
            argumentos = dict(argumentos, lugar=R.quitar_direccion_exacta(argumentos['lugar']))
        resultado = entorno['brian.herramientas'].with_context(**contexto).ejecutar(
            PREFIJO_HERRAMIENTA + nombre, argumentos, canal='juan', auditar=cuerpo.get('origen') != ORIGEN_TIENDA)
        if resultado.get('ok'):
            return _respuesta({'ok': True, 'resultado': resultado.get('datos') or {}})
        if resultado.get('requiere_confirmacion'):
            return _respuesta({'ok': False, 'error': 'Esa herramienta necesita confirmación de una persona.'}, 409)
        return _respuesta({'ok': False, 'error': resultado.get('error') or 'No se pudo ejecutar la herramienta.'}, 422)

    @staticmethod
    def _contexto_de_herramienta(entorno, cuerpo, nombre):
        """La conversación (si viene) y, desde el chat de la tienda (``origen: tienda``), su lista blanca: solo las
        herramientas de leer y nunca con conversación."""
        conversacion_id = cuerpo.get('conversacion_id')
        if cuerpo.get('origen') == ORIGEN_TIENDA:
            if nombre not in HERRAMIENTAS_DE_LA_TIENDA:
                raise _Error(403, f'El chat de la tienda no usa «{nombre[:60]}».')
            if conversacion_id is not None:
                raise _Error(400, 'El chat de la tienda no tiene conversación en Odoo: sin «conversacion_id».')
            # Lo que pregunta el visitante (lo que busca, su barrio) no queda en la auditoría de Brian: la privacidad
            # promete que la conversación no se guarda. Va como parámetro de ``ejecutar`` (``auditar=False``, abajo),
            # nunca en el contexto. Son todas de leer (la lista blanca de arriba).
            return {}
        if conversacion_id is None:
            return {}
        if not isinstance(conversacion_id, int) or isinstance(conversacion_id, bool):
            raise _Error(400, '«conversacion_id» debe ser un número entero.')
        if not entorno['dcasa.conversacion'].sudo().browse(conversacion_id).exists():
            raise _Error(404, 'No existe esa conversación.')
        return {'juan_conversacion_id': conversacion_id}

    @staticmethod
    def _ubicacion_a_lugar(entorno, argumentos, contexto):
        """«Usar mi ubicación» del chat de la tienda (contrato §4): ``lat``/``lon`` se cambian AQUÍ por el lugar de la
        tabla más cercano y no siguen (ni a la herramienta, ni a la auditoría ``brian.accion``, ni al registro).

        Devuelve ``(argumentos, directo)``: ``directo`` es la respuesta sin correr la herramienta (envíos apagados o
        ningún lugar cerca) o ``None``."""
        lat, lon = argumentos.get('lat'), argumentos.get('lon')
        argumentos = {clave: valor for clave, valor in argumentos.items() if clave not in ('lat', 'lon', 'lugar')}
        Herramientas = entorno['brian.herramientas']
        apagado = Herramientas._j_envios_encendidos()
        lugar = None if apagado else Herramientas._j_envio_lugar_cercano(lat, lon)
        del lat, lon
        if apagado:
            return argumentos, dict(apagado, por_ubicacion=True)
        if not lugar:
            return argumentos, Herramientas._j_envio_sin_lugar_cerca()
        contexto['juan_envio_por_ubicacion'] = True
        return dict(argumentos, lugar_id=lugar.id), None

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

    # ------------------------------------------------------------------
    # POST /escribiendo
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/escribiendo', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def escribiendo(self, **_kw):
        return self._servir(self._escribiendo)

    def _escribiendo(self, entorno):
        """Solo avisa a las pantallas abiertas (por el bus, sin texto): no escribe nada en la conversación."""
        cuerpo = self._cuerpo()
        canal = _canal(cuerpo.get('canal'))
        id_externo = _id_externo(cuerpo.get('id_externo'), canal)
        activo = cuerpo.get('activo')
        if not isinstance(activo, bool):
            raise _Error(400, '«activo» debe ser verdadero o falso.')
        conversacion = entorno['dcasa.conversacion'].sudo().search(
            [('canal', '=', canal), ('id_externo', '=', id_externo)], limit=1)
        if conversacion:
            conversacion._notificar_panel('escribiendo', activo=activo)
        return _respuesta({'ok': True})

    # ------------------------------------------------------------------
    # POST /foto-perfil
    # ------------------------------------------------------------------

    @http.route(f'{RAIZ}/foto-perfil', type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def foto_perfil(self, **_kw):
        return self._servir(self._foto_perfil)

    def _foto_perfil(self, entorno):
        """Guarda la foto de perfil de quien escribe. Apagado en Ajustes de Juan: no guarda nada (y lo dice)."""
        cuerpo = self._cuerpo(MAX_CUERPO_FOTO)
        canal = _canal(cuerpo.get('canal'))
        id_externo = _id_externo(cuerpo.get('id_externo'), canal)
        contenido = cuerpo.get('base64')
        if not isinstance(contenido, str) or not contenido:
            raise _Error(400, '«base64» es obligatorio (la foto, en base64).')
        if not entorno['dcasa.juan.ajustes'].obtener().guardar_foto_perfil:
            return _respuesta({'ok': True, 'guardada': False, 'motivo': 'apagado'})
        conversacion = entorno['dcasa.conversacion'].sudo().search(
            [('canal', '=', canal), ('id_externo', '=', id_externo)], limit=1)
        if not conversacion:
            raise _Error(404, 'No existe esa conversación.')
        datos = A.decodificar_base64(contenido, max_bytes=A.MAX_FOTO_DE_PERFIL)
        if datos is None:
            return _respuesta({'ok': True, 'guardada': False, 'motivo': 'no es una foto válida'})
        return _respuesta({'ok': True, 'guardada': conversacion._guardar_foto_de_perfil(datos)})
