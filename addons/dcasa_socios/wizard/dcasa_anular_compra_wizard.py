from odoo import fields, models


class DcasaAnularCompraWizard(models.TransientModel):
    _name = 'dcasa.anular.compra.wizard'
    _description = 'Anular una compra con puntos'

    compra_id = fields.Many2one('dcasa.compra', required=True, readonly=True)
    motivo = fields.Char(required=True, help='El socio lo lee en su cuenta.')

    def action_confirmar(self):
        self.ensure_one()
        self.compra_id._anular(self.motivo, self.env.user.login)
        return {'type': 'ir.actions.act_window_close'}
