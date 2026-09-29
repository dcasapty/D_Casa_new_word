from odoo import models
from odoo.http import request

from .ir_http import SESSION_KEY


class Website(models.Model):
    _inherit = 'website'

    def _prepare_sale_order_values(self, partner_sudo):
        vals = super()._prepare_sale_order_values(partner_sudo)
        code = request.session.get(SESSION_KEY) if request else None
        referrer = self.env['res.partner']._dcasa_find_by_referral_code(code)
        if referrer and referrer.commercial_partner_id != partner_sudo.commercial_partner_id:
            vals['dcasa_referrer_id'] = referrer.id
        return vals
