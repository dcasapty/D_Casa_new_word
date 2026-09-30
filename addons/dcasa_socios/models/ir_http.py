from odoo import models
from odoo.http import request

from . import reglas as R

SESSION_PADRINO = 'dcasa_padrino'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        # Cualquier página del sitio acepta ?ref=DCA… (p. ej. /shop?ref=DCA7K3M9Q).
        if not getattr(request, 'is_frontend', False):
            return
        codigo = R.codigo_normal(request.httprequest.args.get('ref'))
        if R.es_codigo_valido(codigo):
            request.session[SESSION_PADRINO] = codigo
