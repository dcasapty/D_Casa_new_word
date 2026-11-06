"""El pie del correo de la factura y de la bienvenida: «¿Te avisamos de lo nuevo? Sí, quiero».

Un enlace firmado (HMAC con el secreto de la base) que lleva a una página con la marca: allí la persona toca «Sí,
quiero» y queda el permiso con la fecha y por dónde. Un error aquí NUNCA tumba el correo de la factura: se arma en un
savepoint y, si falla, el correo sale sin la línea.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class DcasaCorreo(models.AbstractModel):
    _inherit = 'dcasa.correo'

    @api.model
    def _contexto_layout(self, registro=None, message=None, company=None):
        contexto = super()._contexto_layout(registro, message, company)
        contexto['novedades'] = None
        if getattr(registro, '_name', None) not in ('account.move', 'res.partner'):
            return contexto   # solo la factura y la bienvenida llevan la línea
        try:
            with self.env.cr.savepoint():
                contexto['novedades'] = self.env['dcasa.camila'].sudo()._enlace_si(registro)
        except Exception:   # el correo de la factura sale igual, sin la línea
            _logger.warning('Camila: no se pudo armar el enlace «Sí, quiero» del pie', exc_info=True)
        return contexto
