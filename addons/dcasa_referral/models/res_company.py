from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dcasa_referral_reward_type = fields.Selection(
        [('percent', 'Porcentaje del subtotal'), ('fixed', 'Monto fijo')],
        string='Tipo de recompensa', default='percent', required=True,
    )
    dcasa_referral_reward_value = fields.Float(
        string='Valor de la recompensa', default=5.0,
        help='Porcentaje del subtotal sin ITBMS, o monto fijo en la moneda de la empresa.',
    )
    dcasa_referral_min_amount = fields.Monetary(
        string='Compra mínima', currency_field='currency_id', default=0.0,
        help='Subtotal sin ITBMS mínimo de la factura para generar recompensa.',
    )
    dcasa_referral_first_purchase_only = fields.Boolean(
        string='Solo la primera compra',
        help='Si está activo, cada referido genera recompensa solo en su primera factura.',
    )

    _check_dcasa_referral_reward_value = models.Constraint(
        'CHECK(dcasa_referral_reward_value >= 0)',
        'El valor de la recompensa de referidos no puede ser negativo.',
    )
