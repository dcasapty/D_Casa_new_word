"""Un ajuste a mano en el libro de la comisión web: la corrección de lo ya pagado, de una tarifa parcial o de cualquier
error que el sistema no pueda ver por sí solo. **Siempre con motivo**, solo Gerencia y quien administra la nómina, y por
la puerta única del libro (``_asentar``): nunca se edita ni se borra una fila, se anota otra."""
from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from .calculo import a_centavos
from .movimiento import CONCEPTOS

GRUPO = 'dcasa_nomina.group_nomina'


class DcasaWebAjuste(models.TransientModel):
    _name = 'dcasa.web.ajuste'
    _description = 'Ajuste a mano en el libro de la comisión web'

    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    empleado_id = fields.Many2one('hr.employee', 'Persona', required=True,
                                  domain="[('dcasa_en_planilla', '=', True)]")
    concepto = fields.Selection(CONCEPTOS, 'Concepto', required=True, default='comision')
    monto = fields.Monetary('Monto', required=True,
                            help='Positivo: se le debe más. Negativo: se le debe menos (por ejemplo, para corregir '
                                 'algo que ya se pagó de más).')
    motivo = fields.Char('Motivo', required=True, help='Se ve en el libro. Explica por qué se ajusta.')

    def action_anotar(self):
        """Anota el ajuste en el libro (una fila nueva, con su motivo y quién la hizo)."""
        if not self.env.user.has_group(GRUPO):
            raise AccessError(self.env._('Solo Gerencia y quien administra la nómina anotan ajustes.'))
        self.ensure_one()
        centavos = a_centavos(self.monto)
        if not centavos:
            raise UserError(self.env._('Un ajuste de cero no dice nada: escribe un monto.'))
        if not (self.motivo or '').strip():
            raise UserError(self.env._('Escribe el motivo del ajuste.'))
        self.env['dcasa.web.movimiento']._asentar(
            self.empleado_id, 'ajuste', centavos, self.company_id, autor=self.env.user.login,
            concepto=self.concepto, motivo=self.motivo.strip())
        return {'type': 'ir.actions.act_window_close'}
