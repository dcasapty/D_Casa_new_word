from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_historica = fields.Boolean(
        'Cargada del sistema anterior', readonly=True, copy=False,
        help='Factura o nota que viene de la carga única de la contabilidad anterior (dcasa_migracion). Es historia: '
             'no se manda a la DGI, no da puntos de Socios y no cambia las páginas de la tienda.')
