from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    dcasa_actividad_flujo = fields.Selection(
        [('operacion', 'Operación'), ('inversion', 'Inversión'), ('financiamiento', 'Financiamiento')],
        string='Actividad en el flujo de efectivo',
        help='Dónde va esta cuenta en el flujo de efectivo. Vacío = según el tipo de cuenta (por cobrar, '
             'proveedores e impuestos → operación; activo fijo y no corriente → inversión; préstamos de largo '
             'plazo y patrimonio → financiamiento). Lo decide el contador; p. ej. un préstamo bancario de corto '
             'plazo → financiamiento.')
