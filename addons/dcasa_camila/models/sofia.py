"""Sofía: el mensaje que DE VERDAD salió con «Enviar ya» de una propuesta que pedía los datos del cliente.

El permiso de novedades que se lee de Sofía (``permiso.py``) se ata a ese mensaje y no a cualquiera con «promoci…» en
el chat: al «Enviar ya» se guarda cuál fue. Si algo falla al buscarlo, el envío de Sofía sigue igual (solo no habrá
permiso por ese camino).
"""
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SofiaPropuesta(models.Model):
    _inherit = 'dcasa.sofia.propuesta'

    dcasa_camila_mensaje_id = fields.Many2one(
        'dcasa.mensaje', 'Mensaje enviado (Camila)', readonly=True, ondelete='set null',
        help='El mensaje que salió con «Enviar ya»: el permiso de novedades solo se lee de ese.')


class DcasaSofia(models.AbstractModel):
    _inherit = 'dcasa.sofia'

    def _aplicar_enviar(self, p, texto):
        Mensaje = self.env['dcasa.mensaje'].sudo()
        ultimo = Mensaje.search([], order='id desc', limit=1).id or 0
        resultado = super()._aplicar_enviar(p, texto)
        if p.pide_datos and p.conversacion_id:
            try:
                with self.env.cr.savepoint():
                    # El primero de la vendedora en ese chat creado en esta petición: el de «Enviar ya».
                    mensaje = Mensaje.search([
                        ('conversacion_id', '=', p.conversacion_id.id), ('id', '>', ultimo),
                        ('autor', '=', 'vendedora'), ('tipo', '=', 'mensaje')], order='id', limit=1)
                    if mensaje:
                        p.sudo().write({'dcasa_camila_mensaje_id': mensaje.id})
            except Exception:   # Sofía envía igual; solo no habrá permiso de novedades por este camino
                _logger.warning('Camila: no se pudo guardar el mensaje de Sofía de la propuesta %s', p.id,
                                exc_info=True)
        return resultado
