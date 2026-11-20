"""Un ajuste a mano en el libro de la comisión web: la corrección de lo ya pagado, de una tarifa parcial o de cualquier
error que el sistema no pueda ver por sí solo. **Siempre con motivo**, solo Gerencia y quien administra la nómina, y por
la puerta única del libro (``_asentar``): nunca se edita ni se borra una fila, se anota otra."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .calculo import a_centavos
from .movimiento import CONCEPTOS

GRUPO = 'dcasa_nomina.group_nomina'


class DcasaWebAjuste(models.TransientModel):
    _name = 'dcasa.web.ajuste'
    _description = 'Ajuste a mano en el libro de la comisión web'

    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    permitidos_ids = fields.Many2many('hr.employee', compute='_compute_permitidos',
                                      help='Quienes figuran o han figurado en el reparto de alguna versión.')
    empleado_id = fields.Many2one('hr.employee', 'Persona', required=True,
                                  domain="[('id', 'in', permitidos_ids)]",
                                  help='Solo quien figura o ha figurado entre quienes reciben la comisión.')
    concepto = fields.Selection(CONCEPTOS, 'Concepto', required=True, default='comision')
    monto = fields.Monetary('Monto', required=True,
                            help='Positivo: se le debe más. Negativo: se le debe menos (por ejemplo, para corregir '
                                 'algo que ya se pagó de más).')
    motivo = fields.Char('Motivo', required=True, help='Se ve en el libro. Explica por qué se ajusta.')

    @api.depends('company_id')
    def _compute_permitidos(self):
        for ajuste in self:
            ajuste.permitidos_ids = self._empleados_del_reparto(ajuste.company_id)

    @api.model
    def _empleados_del_reparto(self, company):
        """Los empleados que figuran o han figurado en alguna versión del reparto de ``company``."""
        return self.env['dcasa.web.reparto'].sudo().search([('company_id', '=', company.id)]).empleado_id

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
        if self.empleado_id not in self._empleados_del_reparto(self.company_id):
            raise UserError(self.env._(
                '%s no figura ni ha figurado entre quienes reciben la comisión del sitio: un ajuste solo se anota a '
                'quien está (o estuvo) en el reparto de una versión.', self.empleado_id.name))
        self.env['dcasa.web.movimiento']._asentar(
            self.empleado_id, 'ajuste', centavos, self.company_id, autor=self.env.user.login,
            concepto=self.concepto, motivo=self.motivo.strip())
        return {'type': 'ir.actions.act_window_close'}
