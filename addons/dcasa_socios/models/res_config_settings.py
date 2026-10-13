from odoo import fields, models

from .sale_order import PARAM_PUNTOS_EN_CARRITO


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_puntos_en_carrito = fields.Selection(
        [('premios', 'Solo los premios del catálogo'),
         ('todo', 'Premios del catálogo y puntos sueltos contra cualquier producto')],
        string='Puntos en el carrito web', default='premios',
        config_parameter=PARAM_PUNTOS_EN_CARRITO,
        help='Cómo usa sus puntos un socio en la tienda web. Con «puntos sueltos», el descuento sale de '
             'canje.puntosPorDolar en puntos.json. Las dos opciones están probadas.')
