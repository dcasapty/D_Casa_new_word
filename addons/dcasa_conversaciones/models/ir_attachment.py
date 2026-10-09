from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    dcasa_sensible = fields.Boolean(
        'Sensible (Juan)', copy=False,
        help='Comprobante de pago o documento de identidad que mandó un cliente: lo revisa una vendedora y '
             'no se le muestra a la IA.')
