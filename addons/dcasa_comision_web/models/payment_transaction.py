from odoo import fields, models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    dcasa_comision_pasarela = fields.Monetary(
        'Comisión de la pasarela', readonly=True, copy=False, currency_field='currency_id',
        help='Lo que cobró la pasarela por este pago, si el pago lo guarda. Hoy ninguna pasarela lo escribe; sirve '
             'para el interruptor «restar lo que cobra la pasarela» de las reglas de la comisión web.')
