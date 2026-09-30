from odoo import api, fields, models
from odoo.addons.dcasa_invoice.models import formato


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_check_printing_layout = fields.Selection(
        selection_add=[('dcasa_contabilidad.accion_cheque', "Cheque D'CASA")],
        ondelete={'dcasa_contabilidad.accion_cheque': 'set default'})


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.depends('amount', 'currency_id')
    def _compute_check_amount_in_words(self):
        """Monto en letras en español, como se escribe un cheque en Panamá."""
        super()._compute_check_amount_in_words()
        for pago in self.filtered('currency_id'):
            singular, plural = formato.MONEDAS.get(pago.currency_id.name, ('Dólar', 'Dólares'))
            pago.check_amount_in_words = formato.monto_en_letras(pago.amount, singular, plural)
