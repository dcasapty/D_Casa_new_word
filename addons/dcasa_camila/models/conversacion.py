"""Los chats que llegaron por una campaña: la marca («DCN-0007») en el mensaje del cliente al entrar.

* Se mira del lado de Odoo, cuando el mensaje entra a Conversaciones. Un error aquí nunca frena el mensaje: va en un
  savepoint y solo deja una línea en el registro.
* **Juan lo sabe** (decisión de la dueña, etapa 2): en lo que Odoo le contesta al Worker por cada mensaje (``/mensaje``
  y ``/estado``) va ``campana_correo`` con el asunto de la campaña, cuándo salió y sus productos, solo los primeros
  días desde que llegó; si no llegó por una campaña, el campo no va (y Juan no tiene nada que decir de eso).
"""
import logging

from odoo import models

from . import reglas as R

_logger = logging.getLogger(__name__)


class DcasaConversacion(models.Model):
    _inherit = 'dcasa.conversacion'

    def _despues_de_mensaje(self, mensaje):
        super()._despues_de_mensaje(mensaje)
        # Primero la marca en el texto (sin tocar la base): a los demás mensajes no se les suma ni una consulta.
        if mensaje.autor != 'cliente' or mensaje.tipo != 'mensaje' or not R.campana_de_la_marca(mensaje.texto):
            return
        try:
            with self.env.cr.savepoint():
                self.env['dcasa.camila'].sudo()._anotar_llegada(self, mensaje)
        except Exception:
            _logger.warning('Camila: no se pudo anotar la marca de la campaña en el chat %s', self.id, exc_info=True)

    def _estado_para_worker(self, ajustes=None):
        estado = super()._estado_para_worker(ajustes)
        try:
            with self.env.cr.savepoint():
                contexto = self.env['dcasa.camila'].sudo()._contexto_para_juan(self)
        except Exception:   # Juan contesta igual, sin el dato de la campaña
            _logger.warning('Camila: no se pudo armar el dato de la campaña para Juan (chat %s)', self.id,
                            exc_info=True)
            contexto = None
        if contexto:
            estado['campana_correo'] = contexto
        return estado
