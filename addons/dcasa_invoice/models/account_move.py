from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _dcasa_is_paid(self):
        """True si la factura está saldada (pagada o en proceso de pago)."""
        self.ensure_one()
        return self.is_invoice(include_receipts=True) and self.payment_state in ('paid', 'in_payment')

    def _dcasa_last_payment_date(self):
        """Fecha del último pago conciliado, para el sello de "PAGADO"."""
        self.ensure_one()
        widget = self.invoice_payments_widget or {}
        dates = [payment['date'] for payment in widget.get('content', []) if payment.get('date')]
        return max(dates) if dates else False
