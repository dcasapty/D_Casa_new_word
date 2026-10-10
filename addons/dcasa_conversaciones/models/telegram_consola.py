"""La consola de Telegram de Juan: atender y contestar a un cliente desde el aviso, sin abrir Odoo.

Los avisos de un cliente que espera (traspaso del asistente, lleva rato sin respuesta, mandó un comprobante o un
archivo) llegan por el bot de Brian con dos cosas más:

* El botón **Atender**: la conversación pasa a quien lo pulsa (el asistente calla), igual que el botón de la pantalla.
* Al final, «Conversación n.º N». **Quien responde a ese mensaje** (la función «Responder» de Telegram) escribe el
  texto que quiere mandarle al cliente. El bot NO lo manda: se lo enseña tal cual con los botones **Enviar** y
  **Cancelar**. Solo al pulsar «Enviar» sale por el canal del cliente.

Seguridad (la misma que Brian, que ya filtra estas cosas antes de llegar aquí):

* Solo chats privados vinculados a un usuario de Odoo. Todo corre COMO ESE USUARIO: lo que no podría hacer en la
  pantalla de Conversaciones (no ser del equipo de ventas, una conversación que no es suya) tampoco lo puede hacer
  desde Telegram.
* Nada sale sin el segundo paso. El borrador se guarda ligado a la persona y a la conversación, sirve una sola vez y
  vence a los 15 minutos; otro usuario (aunque tenga el botón a la vista) no puede confirmarlo.
* Solo texto: una foto o un archivo se rechazan con una explicación (para archivos está la pantalla de Conversaciones).
* No se toca Brian ni su webhook: esta clase solo se engancha a dos puntos de ``brian.telegram.enlace``.
"""
import logging
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .conversacion import REFERENCIA_DE_AVISO
from .conversacion_panel import MAX_RESPUESTA

_logger = logging.getLogger(__name__)

VIGENCIA_BORRADOR = timedelta(minutes=15)
_CALLBACK = re.compile(r'juan:([tex]):(\d+)')


class DcasaTelegramBorrador(models.Model):
    _name = 'dcasa.telegram_borrador'
    _description = 'Respuesta escrita desde Telegram, esperando que se confirme'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', 'Quién la escribió', required=True, ondelete='cascade', index=True)
    conversacion_id = fields.Many2one('dcasa.conversacion', 'Conversación', required=True, ondelete='cascade',
                                      index=True)
    texto = fields.Text('Texto', required=True)
    vence = fields.Datetime('Vence', required=True)

    @api.model
    def _crear(self, usuario, conversacion, texto):
        """Guarda un borrador nuevo (y limpia los vencidos de paso: no hace falta una tarea programada)."""
        self.sudo().search([('vence', '<', fields.Datetime.now())]).unlink()
        return self.sudo().create({
            'user_id': usuario.id, 'conversacion_id': conversacion.id, 'texto': texto,
            'vence': fields.Datetime.now() + VIGENCIA_BORRADOR})


class BrianTelegramEnlace(models.Model):
    _inherit = 'brian.telegram.enlace'

    # ------------------------------------------------------------------
    # Responder a un aviso → borrador con confirmación
    # ------------------------------------------------------------------

    @staticmethod
    def _conversacion_del_aviso(mensaje):
        """El número de conversación si el mensaje es una respuesta a un aviso del bot; si no, ``False``."""
        previo = mensaje.get('reply_to_message') or {}
        if not (previo.get('from') or {}).get('is_bot'):
            return False
        # La ÚLTIMA coincidencia: la referencia real va al final del aviso (``PIE_DE_AVISO``); antes vienen el
        # nombre del cliente y el motivo, que escribe el cliente o el bot y podrían traer un «n.º 12» falso.
        encontrados = re.findall(REFERENCIA_DE_AVISO, previo.get('text') or '')
        return int(encontrados[-1]) if encontrados else False

    def _conversar(self, texto, mensaje):
        """Brian llama aquí con cada mensaje de texto de un chat vinculado (ya filtrado y con límite de velocidad).
        Si es la respuesta a un aviso de Juan, se prepara el borrador; si no, sigue Brian como siempre."""
        conversacion_id = self._conversacion_del_aviso(mensaje)
        if not conversacion_id:
            return super()._conversar(texto, mensaje)
        self.ensure_one()
        if mensaje.get('photo') or mensaje.get('document') or mensaje.get('voice') or mensaje.get('video'):
            return self._enviar(self.chat_id, 'Por Telegram solo puedo mandarle texto al cliente. Para mandar una '
                                              'foto o un archivo, usa la pantalla de Conversaciones.')
        texto = (texto or '').strip()
        if not texto:
            return self._enviar(self.chat_id, 'Escribe el mensaje que quieres mandarle al cliente.')
        if len(texto) > MAX_RESPUESTA:
            return self._enviar(self.chat_id, f'Es muy largo (máximo {MAX_RESPUESTA} letras). Acórtalo y vuelve a '
                                              'responder al aviso.')
        yo = self._como_usuario()
        try:
            with self.env.cr.savepoint():
                conv = yo.env['dcasa.conversacion']._para_panel(conversacion_id, escritura=True)
        except (UserError, AccessError) as error:
            return self._enviar(self.chat_id, str(error))
        borrador = self.env['dcasa.telegram_borrador']._crear(self.user_id, conv, texto)
        canal = dict(conv._fields['canal'].selection).get(conv.canal, conv.canal)
        return self._enviar(
            self.chat_id,
            f'Le voy a escribir a {conv.name or conv.display_name} por {canal}:\n\n{texto}\n\n'
            '¿Lo envío? (Vence en 15 minutos.)',
            botones=[[{'text': 'Enviar', 'callback_data': f'juan:e:{borrador.id}'},
                      {'text': 'Cancelar', 'callback_data': f'juan:x:{borrador.id}'}]])

    # ------------------------------------------------------------------
    # Botones: Atender, Enviar, Cancelar
    # ------------------------------------------------------------------

    def _procesar_callback(self, callback, update_id=None):
        if not str(callback.get('data') or '').startswith('juan:'):
            return super()._procesar_callback(callback, update_id)
        mensaje = callback.get('message') or {}
        chat = mensaje.get('chat') or {}
        chat_id = str(chat.get('id') or '')
        self._api('answerCallbackQuery', {'callback_query_id': callback.get('id')})
        if chat.get('type') != 'private' or str((callback.get('from') or {}).get('id')) != chat_id:
            return False
        enlace = self.sudo().search([('chat_id', '=', chat_id), ('activo', '=', True)], limit=1)
        coincide = _CALLBACK.fullmatch(callback.get('data') or '')
        if not enlace or not coincide:
            return False
        if mensaje.get('message_id'):
            # Los botones se quitan en cuanto se pulsan: un doble toque no repite nada.
            self._api('editMessageReplyMarkup', {'chat_id': chat_id, 'message_id': mensaje['message_id'],
                                                 'reply_markup': {'inline_keyboard': []}})
        accion, identificador = coincide.group(1), int(coincide.group(2))
        if accion == 't':
            return enlace._atender_desde_telegram(identificador)
        return enlace._resolver_borrador(identificador, enviar=accion == 'e')

    def _atender_desde_telegram(self, conversacion_id):
        self.ensure_one()
        yo = self._como_usuario()
        try:
            with self.env.cr.savepoint():
                conv = yo.env['dcasa.conversacion']._para_panel(conversacion_id, escritura=True)
                nombre = conv.name or conv.display_name
                yo.env['dcasa.conversacion'].tomar(conversacion_id)
        except (UserError, AccessError) as error:
            return self._enviar(self.chat_id, str(error))
        return self._enviar(self.chat_id, f'Listo: tomaste la conversación de {nombre}. El asistente calla. '
                                          'Responde al aviso con tu mensaje para escribirle.')

    def _resolver_borrador(self, borrador_id, enviar):
        self.ensure_one()
        borrador = self.env['dcasa.telegram_borrador'].sudo().browse(borrador_id).exists()
        if not borrador or borrador.user_id != self.user_id or borrador.vence < fields.Datetime.now():
            return self._enviar(self.chat_id, 'Ese mensaje ya no está pendiente (vence a los 15 minutos o ya se '
                                              'resolvió). Responde otra vez al aviso para escribirlo de nuevo.')
        texto, conversacion_id = borrador.texto, borrador.conversacion_id.id
        borrador.unlink()      # una sola vez: un segundo toque ya no encuentra nada
        if not enviar:
            return self._enviar(self.chat_id, 'Cancelado: no se mandó nada.')
        yo = self._como_usuario()
        try:
            # Sin savepoint: enviar confirma la transacción (COMMIT) y un COMMIT destruye los savepoints abiertos.
            resultado = yo.env['dcasa.conversacion'].enviar_respuesta(conversacion_id, texto)
        except (UserError, AccessError) as error:
            return self._enviar(self.chat_id, f'No se mandó: {error}')
        if resultado.get('enviado'):
            return self._enviar(self.chat_id, 'Enviado ✅')
        return self._enviar(self.chat_id, 'Quedó guardado, pero el canal todavía no lo entrega. Se reintenta solo; '
                                          'míralo en la pantalla de Conversaciones.')
