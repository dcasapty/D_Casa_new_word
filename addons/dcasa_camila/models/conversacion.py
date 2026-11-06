"""Los chats que llegaron por una campaña: la marca («Ref. DCN-0007») en el mensaje del cliente al entrar.

Se mira del lado de Odoo, cuando el mensaje entra a Conversaciones (no se toca a Juan). Un error aquí nunca frena el
mensaje: va en un savepoint y solo deja una línea en el registro.
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
