from odoo import fields, models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _create_payment(self, **extra_create_values):
        """El pago de una pasarela lleva la fecha de PANAMÁ: sin esto toma la zona horaria de quien lo crea (el usuario
        público o un proceso en UTC) y, entre las 7 de la noche y la medianoche, el día de cobro (que decide a quién le
        toca una venta online) salía un día adelantado."""
        if 'date' not in extra_create_values:
            extra_create_values['date'] = fields.Date.context_today(self.with_context(tz='America/Panama'))
        return super()._create_payment(**extra_create_values)

    dcasa_comision_pasarela = fields.Monetary(
        'Comisión de la pasarela', readonly=True, copy=False, currency_field='currency_id',
        help='Lo que cobró la pasarela por este pago, si el pago lo guarda. Hoy ninguna pasarela lo escribe; sirve '
             'para el interruptor «restar lo que cobra la pasarela» de las reglas de la comisión web.')
