from odoo import models
from odoo.http import request

from .ir_http import SESSION_PADRINO, SESSION_VENDEDOR


class Website(models.Model):
    _inherit = 'website'

    def _prepare_sale_order_values(self, partner_sudo):
        """El carrito de quien llegó por un link de socio queda propuesto con su padrino."""
        vals = super()._prepare_sale_order_values(partner_sudo)
        codigo = request.session.get(SESSION_PADRINO) if request else None
        padrino = self.env['res.partner']._dcasa_por_codigo(codigo) if codigo else None
        if padrino and padrino.commercial_partner_id != partner_sudo.commercial_partner_id:
            vals['dcasa_referido_por_id'] = padrino.id
        # Y el de quien llegó por el link de un vendedor del programa (si no es él mismo comprando).
        codigo_vendedor = request.session.get(SESSION_VENDEDOR) if request else None
        vendedor = self.env['res.partner']._dcasa_vendedor_por_codigo(codigo_vendedor) if codigo_vendedor else None
        if vendedor and vendedor.dcasa_vendedor_estado == 'activo' and vendedor.active \
                and not vendedor._dcasa_es_la_misma_persona(partner_sudo):
            vals['dcasa_vendedor_id'] = vendedor.id
        return vals
