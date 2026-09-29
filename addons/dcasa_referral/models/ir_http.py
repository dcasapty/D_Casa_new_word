from odoo import models
from odoo.http import request

from .res_partner import normalize_referral_code

SESSION_KEY = 'dcasa_referral_code'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        # Cualquier URL del sitio acepta ?ref=CODIGO (p. ej. /shop?ref=DC7K3M9Q).
        if not getattr(request, 'is_frontend', False):
            return
        code = normalize_referral_code(request.httprequest.args.get('ref'))
        if code:
            request.session[SESSION_KEY] = code
