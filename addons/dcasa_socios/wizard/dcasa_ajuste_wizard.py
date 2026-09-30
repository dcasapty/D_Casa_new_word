from odoo import fields, models
from odoo.exceptions import UserError


class DcasaAjusteWizard(models.TransientModel):
    """Corrección manual del saldo. Lleva motivo porque el socio lo lee en su cuenta."""

    _name = 'dcasa.ajuste.wizard'
    _description = 'Ajustar puntos de un socio'

    partner_id = fields.Many2one('res.partner', string='Socio', required=True, readonly=True)
    saldo = fields.Integer(related='partner_id.dcasa_saldo', string='Saldo actual')
    puntos = fields.Integer(required=True, help='Positivo suma, negativo resta.')
    motivo = fields.Char(required=True, help='Escríbelo pensando en que lo va a leer el socio.')

    def action_confirmar(self):
        self.ensure_one()
        if not self.puntos:
            raise UserError(self.env._('El ajuste tiene que ser un número distinto de cero.'))
        if not (self.motivo or '').strip():
            raise UserError(self.env._('Escribe por qué: el socio lo va a leer tal cual en su cuenta.'))
        if self.puntos < 0 and self.saldo + self.puntos < 0:
            raise UserError(self.env._('No se le pueden quitar %(quitar)s puntos: solo tiene %(saldo)s.',
                                       quitar=abs(self.puntos), saldo=self.saldo))
        ficha = self.partner_id._dcasa_asegurar_ficha()
        self.env['dcasa.movimiento']._asentar(ficha, 'ajuste', self.puntos, self.env.user.login,
                                             motivo=self.motivo.strip())
        return {'type': 'ir.actions.act_window_close'}
