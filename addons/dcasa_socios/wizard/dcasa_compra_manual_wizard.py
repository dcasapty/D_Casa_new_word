from odoo import fields, models
from odoo.exceptions import UserError

from ..models import reglas as R


class DcasaCompraManualWizard(models.TransientModel):
    """Carga a mano una factura que no salió de Odoo (p. ej. las del sistema anterior).

    Las facturas de Odoo suman puntos solas al pagarse: esto es solo para la transición.
    """

    _name = 'dcasa.compra.manual.wizard'
    _description = 'Registrar compra a mano'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True)
    factura = fields.Char(string='N.º de factura fiscal', required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    monto = fields.Monetary(string='Total pagado (con ITBMS)', required=True)
    notas = fields.Char()

    def action_confirmar(self):
        self.ensure_one()
        centavos = R.a_centavos(self.monto)
        if centavos <= 0:
            raise UserError(self.env._('El monto tiene que ser mayor que cero.'))
        if self.env['dcasa.compra'].sudo().search_count([('factura_normal', '=', R.factura_normal(self.factura))]):
            raise UserError(self.env._('Esa factura ya dio puntos. Una factura, una carga.'))
        compra = self.env['dcasa.compra']._registrar(
            self.partner_id, self.factura.strip(), centavos, self.env.user, self.env.user.login, notas=self.notas or '')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dcasa.compra',
            'res_id': compra.id,
            'view_mode': 'form',
        }
