"""Los ajustes de Sofía viven en Ajustes de Juan (Conversaciones › Configuración), en su propio grupo."""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class JuanAjustesSofia(models.Model):
    _inherit = 'dcasa.juan.ajustes'

    sofia_manana = fields.Boolean(
        'Sofía revisa el CRM cada mañana', default=True, tracking=True,
        help='Media hora después de abrir, Sofía revisa el CRM y deja sus propuestas para el día. Con el botón se '
             'puede pedir cuando quieras.')
    sofia_telegram = fields.Boolean(
        'Resumen de la mañana por Telegram', default=True, tracking=True,
        help='Cada vendedora recibe lo suyo y Gerencia el resumen de todo (solo quien tiene Telegram vinculado).')
    sofia_dias_sin_repetir = fields.Integer(
        'Lo descartado no vuelve en (días)', default=7, tracking=True,
        help='Si alguien descarta una propuesta, Sofía no la vuelve a proponer en estos días.')
    sofia_dias_datos = fields.Integer(
        'No volver a pedir sus datos en (días)', default=30, tracking=True,
        help='A quien ya se le pidió su nombre o su correo no se le vuelve a pedir en estos días.')

    @api.constrains('sofia_dias_sin_repetir', 'sofia_dias_datos')
    def _check_sofia_dias(self):
        for ajustes in self:
            if not 1 <= ajustes.sofia_dias_sin_repetir <= 60:
                raise ValidationError(self.env._('«Lo descartado no vuelve en» va de 1 a 60 días.'))
            if not 7 <= ajustes.sofia_dias_datos <= 365:
                raise ValidationError(self.env._('«No volver a pedir sus datos en» va de 7 a 365 días.'))
