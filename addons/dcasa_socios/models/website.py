from odoo import models
from odoo.http import request

from .ir_http import SESSION_PADRINO


class Website(models.Model):
    _inherit = 'website'

    def _prepare_sale_order_values(self, partner_sudo):
        """El carrito de quien llegó por un link de socio queda propuesto con su padrino."""
        vals = super()._prepare_sale_order_values(partner_sudo)
        codigo = request.session.get(SESSION_PADRINO) if request else None
        padrino = self.env['res.partner']._dcasa_por_codigo(codigo) if codigo else None
        if padrino and padrino.commercial_partner_id != partner_sudo.commercial_partner_id:
            vals['dcasa_referido_por_id'] = padrino.id
        return vals
