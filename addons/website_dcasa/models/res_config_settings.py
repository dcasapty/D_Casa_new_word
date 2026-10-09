from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_whatsapp_number = fields.Char(related='website_id.dcasa_whatsapp_number', readonly=False)
    dcasa_apartado_dias = fields.Integer(
        'Días que se guarda un pedido de la tienda sin cobrar', config_parameter='website_dcasa.apartado_dias',
        default=7, help='Pasado ese plazo sin que el cliente lo reclame, el pedido se anula solo y el inventario '
                        'vuelve a quedar libre. 0 = nunca se anula solo.')
