import re

from markupsafe import Markup

from odoo import api, models


class IrQwebFieldMonetary(models.AbstractModel):
    _inherit = 'ir.qweb.field.monetary'

    @api.model
    def value_to_html(self, value, options):
        html = super().value_to_html(value, options)
        # Odoo separa el símbolo con un espacio duro («$ 98.12»). En un documento
        # impreso de D'CASA se escribe pegado, como en Panamá: «$98.12».
        # Y un monto negativo lleva el signo delante del símbolo: «-$9.35», no «$-9.35».
        moneda = options.get('display_currency')
        if self.env.context.get('dcasa_moneda_compacta') and moneda and moneda.position == 'before' \
                and moneda.symbol:
            html = html.replace(f'{moneda.symbol}\N{NO-BREAK SPACE}', moneda.symbol, 1)
            # Odoo escribe «$<span class="oe_currency_value">-\ufeff9.35</span>».
            # (re.sub sobre un Markup escaparía el reemplazo: se trabaja sobre el texto y se vuelve a marcar.)
            html = Markup(re.sub(
                re.escape(moneda.symbol) + r'(<span[^>]*>)-\ufeff?', rf'-{moneda.symbol}\1', str(html), count=1))
        return html
