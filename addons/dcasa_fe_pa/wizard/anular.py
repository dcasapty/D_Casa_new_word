from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from ..models import catalogos as C


class DcasaFeAnularWizard(models.TransientModel):
    """Anula ante la DGI una factura electrónica autorizada (solo si la operación NO ocurrió).

    Si la venta sí ocurrió y hay que corregirla, lo que va es una nota de crédito.
    """
    _name = 'dcasa.fe.anular.wizard'
    _description = 'Anular factura electrónica'

    documento_id = fields.Many2one('dcasa.fe.documento', required=True, readonly=True)
    motivo = fields.Char(required=True, size=C.MOTIVO_MAX)

    def action_confirmar(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(self.env._('Solo Facturación puede anular facturas electrónicas.'))
        motivo = (self.motivo or '').strip()
        if len(motivo) < C.MOTIVO_MIN:
            raise UserError(self.env._('Explica el motivo con al menos %s caracteres.', C.MOTIVO_MIN))
        self.documento_id.sudo()._anular_en_pac(motivo)
        return {'type': 'ir.actions.act_window_close'}
