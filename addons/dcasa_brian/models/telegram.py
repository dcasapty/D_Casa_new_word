"""Brian en Telegram: vínculo chat ↔ usuario de Odoo, códigos de un solo uso y el bot.

Flujo
-----
1. El usuario pide un código desde su ficha (Preferencias → «Vincular Telegram») o desde
   Brian → Telegram. El código (6 dígitos) vence en 10 minutos y sirve una sola vez.
2. En Telegram le escribe al bot ``/vincular 123456``. El chat queda enlazado a ese usuario
   y todo lo que Brian haga desde ese chat corre COMO ÉL (sus permisos, sus compañías).
3. Mensajes (texto, fotos, documentos) → ``brian.conversacion.enviar`` en la conversación
   activa del chat (canal ``telegram``). Las acciones sensibles llegan con botones
   Confirmar / Cancelar; solo el mismo usuario puede confirmarlas.

Seguridad
---------
* Solo chats privados: en grupos el bot no responde (cualquiera podría pulsar un botón).
* Chats no vinculados solo reciben instrucciones para vincularse; nada más.
* Intentos de ``/vincular`` limitados por chat; el código se guarda con hash.
* El token (``TELEGRAM_BOT_TOKEN``) y el secreto del webhook (``BRIAN_TELEGRAM_SECRETO``)
  se leen de variables de entorno (secretos de Cloudflare); como alternativa, de los
  parámetros ``dcasa_brian.telegram_token`` / ``dcasa_brian.telegram_secreto``.
  El token nunca se escribe en el log.
"""
import hashlib
import logging
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

API_TELEGRAM = 'https://api.telegram.org'
LIMITE_MENSAJE = 4096
VIGENCIA_CODIGO = timedelta(minutes=10)
MAX_INTENTOS = 5                 # /vincular fallidos por chat cada 10 minutos
MAX_MENSAJES_MINUTO = 20         # mensajes por chat por minuto
MAX_ADJUNTO = 10 * 1024 * 1024   # 10 MB por archivo
TIMEOUT = (5, 30)

_candado = threading.Lock()
_intentos = defaultdict(deque)
_mensajes = defaultdict(deque)


def _limitar(registro, clave, maximo, ventana):
    """True si ``clave`` ya superó ``maximo`` eventos en ``ventana`` segundos (y cuenta este)."""
    ahora = time.monotonic()
    with _candado:
        cola = registro[clave]
        while cola and cola[0] < ahora - ventana:
            cola.popleft()
        if len(cola) >= maximo:
            return True
        cola.append(ahora)
        return False


def partir_texto(texto, limite=LIMITE_MENSAJE):
    """Parte un texto largo en trozos ≤ ``limite``, preferentemente en saltos de línea."""
    texto = texto or ''
    trozos = []
    while len(texto) > limite:
        corte = texto.rfind('\n', 0, limite)
        if corte < limite // 2:
            corte = texto.rfind(' ', 0, limite)
        if corte < limite // 2:
            corte = limite
        trozos.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip('\n ')
    if texto or not trozos:
        trozos.append(texto)
    return [t for t in trozos if t] or ['…']


AYUDA = (
    "Soy Brian, el asistente de D'CASA.\n\n"
    "Escríbeme lo que necesitas (por ejemplo: «¿cómo van las ventas de hoy?») o mándame "
    "una foto o un documento.\n\n"
    "Comandos:\n"
    "/nuevo — empezar una conversación nueva\n"
    "/desvincular — desconectar este chat de tu usuario\n"
    "/ayuda — ver este mensaje"
)

INSTRUCCIONES_VINCULAR = (
    "Hola, soy Brian, el asistente de D'CASA. Este chat todavía no está vinculado a un "
    "usuario.\n\n"
    "1. Entra al panel de Odoo → tu perfil (Mis preferencias) → «Vincular Telegram».\n"
    "2. Envíame aquí: /vincular 123456 (con el código que te muestra; vence en 10 minutos)."
)


class BrianTelegramCodigo(models.Model):
    _name = 'brian.telegram.codigo'
    _description = 'Código para vincular Telegram con Brian'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', string='Usuario', required=True, ondelete='cascade', index=True)
    codigo_hash = fields.Char(required=True, index=True)
    vence = fields.Datetime(required=True)
    usado = fields.Boolean(default=False)

    @api.model
    def _hash(self, codigo):
        sal = self.env['ir.config_parameter'].sudo().get_param('database.secret', '')
        return hashlib.sha256(f'{sal}:{codigo}'.encode()).hexdigest()


class BrianTelegramEnlace(models.Model):
    _name = 'brian.telegram.enlace'
    _description = 'Chat de Telegram vinculado a Brian'
    _order = 'fecha desc, id desc'
    _rec_name = 'nombre'

    user_id = fields.Many2one('res.users', string='Usuario', required=True, ondelete='cascade', index=True)
    chat_id = fields.Char(string='Chat de Telegram', required=True, readonly=True, index=True)
    nombre = fields.Char(string='Nombre en Telegram', readonly=True)
    activo = fields.Boolean(default=True)
    fecha = fields.Datetime(string='Vinculado el', default=fields.Datetime.now, readonly=True)
    conversacion_id = fields.Many2one('brian.conversacion', string='Conversación activa', ondelete='set null')
    ultimo_update = fields.Integer(readonly=True)

    _chat_unico = models.Constraint('unique(chat_id)', 'Ese chat de Telegram ya está vinculado.')

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    @api.model
    def _token(self):
        return os.environ.get('TELEGRAM_BOT_TOKEN') or \
            self.env['ir.config_parameter'].sudo().get_param('dcasa_brian.telegram_token') or ''

    @api.model
    def _secreto(self):
        return os.environ.get('BRIAN_TELEGRAM_SECRETO') or \
            self.env['ir.config_parameter'].sudo().get_param('dcasa_brian.telegram_secreto') or ''

    @api.model
    def _nombre_bot(self):
        bot = self.env['ir.config_parameter'].sudo().get_param('dcasa_brian.telegram_bot') or ''
        return f'@{bot}' if bot else 'el bot de Brian'

    # ------------------------------------------------------------------
    # API de Telegram
    # ------------------------------------------------------------------

    @api.model
    def _api(self, metodo, datos=None):
        """Llama a la API de bots. Devuelve ``result`` o ``None``; nunca registra el token."""
        token = self._token()
        if not token:
            _logger.warning('Brian/Telegram: falta TELEGRAM_BOT_TOKEN; no se envía %s.', metodo)
            return None
        try:
            respuesta = requests.post(f'{API_TELEGRAM}/bot{token}/{metodo}', json=datos or {}, timeout=TIMEOUT)
            cuerpo = respuesta.json()
        except (requests.RequestException, ValueError) as error:
            _logger.warning('Brian/Telegram: fallo al llamar %s (%s).', metodo, type(error).__name__)
            return None
        if not cuerpo.get('ok'):
            _logger.warning('Brian/Telegram: %s respondió %s: %s', metodo, respuesta.status_code,
                            cuerpo.get('description'))
            return None
        return cuerpo.get('result')

    @api.model
    def _enviar(self, chat_id, texto, botones=None):
        """Texto plano (sin parse_mode: nada que escapar), partido en trozos de 4096."""
        trozos = partir_texto(texto)
        resultado = None
        for i, trozo in enumerate(trozos):
            datos = {'chat_id': chat_id, 'text': trozo, 'disable_web_page_preview': True}
            if botones and i == len(trozos) - 1:
                datos['reply_markup'] = {'inline_keyboard': botones}
            resultado = self._api('sendMessage', datos)
        return resultado

    @api.model
    def _descargar(self, file_id):
        """Descarga un archivo del bot (getFile). Devuelve bytes o None."""
        info = self._api('getFile', {'file_id': file_id})
        if not info or not info.get('file_path'):
            return None
        if (info.get('file_size') or 0) > MAX_ADJUNTO:
            return None
        try:
            respuesta = requests.get(f'{API_TELEGRAM}/file/bot{self._token()}/{info["file_path"]}',
                                     timeout=TIMEOUT)
        except requests.RequestException as error:
            _logger.warning('Brian/Telegram: no se pudo descargar un archivo (%s).', type(error).__name__)
            return None
        if respuesta.status_code != 200 or len(respuesta.content) > MAX_ADJUNTO:
            return None
        return respuesta.content

    @staticmethod
    def _botones(accion_id):
        return [[{'text': 'Confirmar', 'callback_data': f'brian:c:{accion_id}'},
                 {'text': 'Cancelar', 'callback_data': f'brian:r:{accion_id}'}]]

    # ------------------------------------------------------------------
    # Vincular (panel)
    # ------------------------------------------------------------------

    @api.model
    def generar_codigo(self):
        """Código de un solo uso para el usuario actual. Invalida los anteriores."""
        usuario = self.env.user
        if usuario._is_public() or not usuario._is_internal():
            raise UserError(self.env._('Solo los usuarios internos pueden vincular Telegram.'))
        Codigo = self.env['brian.telegram.codigo'].sudo()
        Codigo.search([('user_id', '=', usuario.id), ('usado', '=', False)]).write({'usado': True})
        codigo = f'{secrets.randbelow(10 ** 6):06d}'
        Codigo.create({
            'user_id': usuario.id,
            'codigo_hash': Codigo._hash(codigo),
            'vence': fields.Datetime.now() + VIGENCIA_CODIGO,
        })
        return codigo

    @api.model
    def action_vincular(self):
        codigo = self.generar_codigo()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Vincular Telegram'),
                'message': self.env._('Envía «/vincular %(codigo)s» a %(bot)s en Telegram. '
                                      'El código vence en 10 minutos y sirve una sola vez.',
                                      codigo=codigo, bot=self._nombre_bot()),
                'sticky': True,
                'type': 'info',
            },
        }

    def action_desvincular(self):
        for enlace in self:
            if enlace.user_id != self.env.user and not self.env.user.has_group('base.group_system'):
                raise UserError(self.env._('Solo puedes desvincular tus propios chats.'))
        self.sudo().write({'activo': False, 'conversacion_id': False})
        return True

    @api.model
    def action_registrar_webhook(self):
        """setWebhook con la URL pública (web.base.url) y el secreto. Solo administradores."""
        if not self.env.user.has_group('base.group_system'):
            raise UserError(self.env._('Solo un administrador puede registrar el webhook.'))
        if not self._token():
            raise UserError(self.env._('Falta TELEGRAM_BOT_TOKEN (secreto de Cloudflare) o el parámetro '
                                       'dcasa_brian.telegram_token.'))
        Parametros = self.env['ir.config_parameter'].sudo()
        secreto = self._secreto()
        if not secreto:
            secreto = secrets.token_urlsafe(32)
            Parametros.set_param('dcasa_brian.telegram_secreto', secreto)
        base = (Parametros.get_param('web.base.url') or '').rstrip('/')
        if not base.startswith('https://'):
            raise UserError(self.env._('Telegram exige HTTPS: revisa el parámetro web.base.url (%s).', base))
        resultado = self._api('setWebhook', {
            'url': f'{base}/brian/telegram/{secreto}',
            'secret_token': secreto,
            'allowed_updates': ['message', 'callback_query'],
        })
        if resultado is None:
            raise UserError(self.env._('Telegram no aceptó el webhook; revisa el token y el registro del servidor.'))
        yo = self._api('getMe') or {}
        if yo.get('username'):
            Parametros.set_param('dcasa_brian.telegram_bot', yo['username'])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Telegram', 'type': 'success',
                       'message': self.env._('Webhook registrado en %s/brian/telegram/…', base)},
        }

    # ------------------------------------------------------------------
    # Aviso fuera de banda (MCP → Telegram)
    # ------------------------------------------------------------------

    @api.model
    def notificar_confirmacion(self, usuario, accion_id, resumen, origen='MCP'):
        """Si el usuario tiene Telegram vinculado, le manda la acción sensible con botones."""
        enlaces = self.sudo().search([('user_id', '=', usuario.id), ('activo', '=', True)])
        for enlace in enlaces:
            self._enviar(enlace.chat_id,
                         f'Brian ({origen}) quiere hacer algo que necesita tu confirmación:\n\n{resumen}',
                         botones=self._botones(accion_id))
        return bool(enlaces)

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    @api.model
    def procesar_update(self, update):
        """Punto de entrada del webhook (se llama con superusuario; cada acción baja al usuario)."""
        if update.get('callback_query'):
            return self._procesar_callback(update['callback_query'], update.get('update_id'))
        mensaje = update.get('message')
        if not mensaje:
            return False
        chat = mensaje.get('chat') or {}
        if chat.get('type') != 'private' or not chat.get('id'):
            return False
        chat_id = str(chat['id'])
        texto = (mensaje.get('text') or mensaje.get('caption') or '').strip()
        enlace = self.sudo().search([('chat_id', '=', chat_id), ('activo', '=', True)], limit=1)

        comando, _, resto = texto.partition(' ')
        comando = comando.split('@')[0].lower() if texto.startswith('/') else ''
        if comando == '/vincular':
            return self._vincular(chat_id, resto.strip(), mensaje.get('from') or {})
        if not enlace:
            return self._enviar(chat_id, INSTRUCCIONES_VINCULAR)
        if update.get('update_id') and update['update_id'] <= enlace.ultimo_update:
            return False   # reintento de Telegram: ya procesado
        enlace.ultimo_update = update.get('update_id') or enlace.ultimo_update
        if _limitar(_mensajes, chat_id, MAX_MENSAJES_MINUTO, 60):
            return self._enviar(chat_id, 'Vas muy rápido. Espera un minuto y vuelve a escribirme.')
        if comando in ('/start', '/ayuda', '/help'):
            return self._enviar(chat_id, f'Hola, {enlace.user_id.name}. {AYUDA}')
        if comando == '/nuevo':
            enlace.conversacion_id = False
            return self._enviar(chat_id, 'Listo, empezamos una conversación nueva.')
        if comando == '/desvincular':
            enlace.write({'activo': False, 'conversacion_id': False})
            return self._enviar(chat_id, 'Este chat quedó desvinculado. Para volver, pide un código nuevo en el panel.')
        return enlace._conversar(texto, mensaje)

    def _vincular(self, chat_id, codigo, remitente):
        if _limitar(_intentos, chat_id, MAX_INTENTOS, VIGENCIA_CODIGO.total_seconds()):
            return self._enviar(chat_id, 'Demasiados intentos. Espera unos minutos y pide un código nuevo en el panel.')
        if not re.fullmatch(r'\d{6}', codigo or ''):
            return self._enviar(chat_id, 'Envía el código así: /vincular 123456')
        Codigo = self.env['brian.telegram.codigo'].sudo()
        registro = Codigo.search([('codigo_hash', '=', Codigo._hash(codigo)), ('usado', '=', False)], limit=1)
        if not registro or registro.vence < fields.Datetime.now():
            return self._enviar(chat_id, 'Ese código no es válido o ya venció. Pide uno nuevo en el panel '
                                         '(Mis preferencias → Vincular Telegram).')
        registro.usado = True
        usuario = registro.user_id
        if not usuario.active or not usuario._is_internal():
            return self._enviar(chat_id, 'Ese usuario no puede usar Brian.')
        nombre = ' '.join(filter(None, [remitente.get('first_name'), remitente.get('last_name')]))
        if remitente.get('username'):
            nombre = f'{nombre} (@{remitente["username"]})'.strip()
        valores = {'user_id': usuario.id, 'nombre': nombre or chat_id, 'activo': True,
                   'fecha': fields.Datetime.now(), 'conversacion_id': False}
        enlace = self.sudo().search([('chat_id', '=', chat_id)], limit=1)
        if enlace:
            enlace.write(valores)
        else:
            self.sudo().create(dict(valores, chat_id=chat_id))
        with _candado:
            _intentos.pop(chat_id, None)
        return self._enviar(chat_id, f'Listo, {usuario.name}: este chat quedó vinculado a tu usuario. {AYUDA}')

    def _como_usuario(self):
        usuario = self.user_id
        return self.with_user(usuario).with_context(lang=usuario.lang, tz=usuario.tz)

    def _conversacion(self):
        """La conversación activa del chat (como el usuario); crea una si no hay."""
        self.ensure_one()
        Conversacion = self._como_usuario().env['brian.conversacion']
        conversacion = Conversacion.browse(self.conversacion_id.id).exists() if self.conversacion_id else Conversacion
        if not conversacion:
            conversacion = Conversacion.browse(Conversacion.nueva(canal='telegram')['id'])
            self.sudo().conversacion_id = conversacion.id
        return conversacion

    def _adjuntos(self, mensaje, conversacion):
        """Fotos y documentos del mensaje → ir.attachment (en la base, como el usuario)."""
        archivos = []
        if mensaje.get('photo'):
            foto = max(mensaje['photo'], key=lambda f: f.get('file_size') or f.get('width', 0))
            archivos.append((foto['file_id'], f'foto_{mensaje.get("message_id", "")}.jpg', 'image/jpeg'))
        if mensaje.get('document'):
            doc = mensaje['document']
            archivos.append((doc['file_id'], doc.get('file_name') or 'documento', doc.get('mime_type')))
        ids = []
        for file_id, nombre, mimetype in archivos:
            contenido = self._descargar(file_id)
            if contenido is None:
                continue
            valores = {'name': nombre, 'raw': contenido, 'res_model': 'brian.conversacion',
                       'res_id': conversacion.id}
            if mimetype:
                valores['mimetype'] = mimetype
            ids.append(conversacion.env['ir.attachment'].create(valores).id)
        return ids, len(archivos) - len(ids)

    def _conversar(self, texto, mensaje):
        self.ensure_one()
        self._api('sendChatAction', {'chat_id': self.chat_id, 'action': 'typing'})
        conversacion = self._conversacion()
        adjunto_ids, fallidos = self._adjuntos(mensaje, conversacion)
        if fallidos:
            self._enviar(self.chat_id, 'No pude descargar uno de los archivos (máximo 10 MB).')
        if not texto and not adjunto_ids:
            return self._enviar(self.chat_id, 'Por ahora entiendo texto, fotos y documentos.')
        resultado = conversacion.enviar(texto or 'Te mando este archivo.', adjunto_ids=adjunto_ids)
        return self._responder(resultado)

    def _responder(self, resultado, ignorar_accion=None):
        """Manda a Telegram lo nuevo de Brian. ``ignorar_accion``: la tarjeta ya respondida
        (tras confirmar, ``mensajes`` trae de nuevo el mensaje viejo que la contenía)."""
        enviados = False
        for mensaje in resultado.get('mensajes') or []:
            confirmacion = mensaje.get('confirmacion')
            if ignorar_accion and confirmacion and confirmacion.get('accion_id') == ignorar_accion:
                continue
            texto = (mensaje.get('texto') or '').strip() if mensaje.get('rol') == 'assistant' else ''
            if confirmacion and confirmacion.get('estado') == 'por_confirmar':
                previo = f'{texto}\n\n' if texto else ''
                self._enviar(self.chat_id, f'{previo}Necesito tu confirmación:\n\n{confirmacion.get("resumen") or ""}',
                             botones=self._botones(confirmacion['accion_id']))
                enviados = True
            elif texto:
                self._enviar(self.chat_id, mensaje['texto'])
                enviados = True
        if not resultado.get('ok') and resultado.get('error'):
            self._enviar(self.chat_id, resultado['error'])
            enviados = True
        return enviados

    def _procesar_callback(self, callback, update_id=None):
        mensaje = callback.get('message') or {}
        chat = mensaje.get('chat') or {}
        chat_id = str(chat.get('id') or '')
        self._api('answerCallbackQuery', {'callback_query_id': callback.get('id')})
        if chat.get('type') != 'private' or str((callback.get('from') or {}).get('id')) != chat_id:
            return False
        enlace = self.sudo().search([('chat_id', '=', chat_id), ('activo', '=', True)], limit=1)
        coincide = re.fullmatch(r'brian:([cr]):(\d+)', callback.get('data') or '')
        if not enlace or not coincide:
            return False
        if mensaje.get('message_id'):
            self._api('editMessageReplyMarkup', {'chat_id': chat_id, 'message_id': mensaje['message_id'],
                                                 'reply_markup': {'inline_keyboard': []}})
        confirmar, accion_id = coincide.group(1) == 'c', int(coincide.group(2))
        yo = enlace._como_usuario()
        accion = yo.env['brian.accion'].sudo().browse(accion_id).exists()
        if not accion or accion.create_uid != enlace.user_id:
            return self._enviar(chat_id, 'Esa acción ya no está pendiente de confirmación.')
        conversacion = accion.conversacion_id if 'conversacion_id' in accion._fields else False
        if conversacion:
            Conversacion = yo.env['brian.conversacion'].browse(conversacion.id)
            resultado = Conversacion.confirmar_accion(accion_id) if confirmar else \
                Conversacion.rechazar_accion(accion_id)
            if not enlace._responder(resultado, ignorar_accion=accion_id):
                enlace._enviar(chat_id, 'Listo.' if confirmar else 'Cancelado.')
            return True
        # Acción sin conversación (por ejemplo, propuesta desde MCP).
        Herramientas = yo.env['brian.herramientas']
        if not confirmar:
            Herramientas.rechazar(accion_id)
            return self._enviar(chat_id, 'Cancelado: no se hizo nada.')
        resultado = Herramientas.confirmar(accion_id)
        if resultado.get('ok'):
            return self._enviar(chat_id, 'Listo, hecho.')
        return self._enviar(chat_id, f'No se pudo: {resultado.get("error")}')


class ResUsers(models.Model):
    _inherit = 'res.users'

    def action_dcasa_brian_vincular_telegram(self):
        if self and self != self.env.user:
            raise UserError(self.env._('Solo puedes vincular tu propio Telegram: hazlo desde tu perfil.'))
        return self.env['brian.telegram.enlace'].action_vincular()
