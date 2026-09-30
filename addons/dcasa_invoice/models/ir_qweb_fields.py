from odoo import api, models


class IrQwebFieldMonetary(models.AbstractModel):
    _inherit = 'ir.qweb.field.monetary'

    @api.model
    def value_to_html(self, value, options):
        html = super().value_to_html(value, options)
        # Odoo separa el símbolo con un espacio duro («$ 98.12»). En un documento
        # impreso de D'CASA se escribe pegado, como en Panamá: «$98.12».
        moneda = options.get('display_currency')
        if self.env.context.get('dcasa_moneda_compacta') and moneda and moneda.position == 'before' \
                and moneda.symbol:
            html = html.replace(f'{moneda.symbol}\N{NO-BREAK SPACE}', moneda.symbol, 1)
        return html
