"""Un ajuste a mano en el libro de la comisión web: la corrección de lo ya pagado, de una tarifa parcial o de cualquier
error que el sistema no pueda ver por sí solo. **Siempre con motivo**, solo Gerencia y quien administra la nómina, y por
la puerta única del libro (``_asentar``): nunca se edita ni se borra una fila, se anota otra."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .calculo import a_centavos, numero_finito
from .movimiento import CONCEPTOS, MAXIMO_CENTAVOS

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

    @api.model
    def _validar_monto(self, monto):
        """Un monto que no es un número (``inf``, ``nan``, un texto, un entero de 30 cifras: una llamada RPC manda lo
        que quiera) o que no cabe en el libro se rechaza con un mensaje claro, antes de que Odoo intente redondearlo y
        falle con un error de Python sin traducir."""
        numero = numero_finito(monto)
        if numero is None:
            raise UserError(self.env._('El monto no es un número válido: escribe una cifra, por ejemplo 25.50.'))
        if abs(numero) > MAXIMO_CENTAVOS / 100:
            raise UserError(self._monto_demasiado_grande())

    @api.model
    def _monto_demasiado_grande(self):
        return self.env._(
            'Ese monto es demasiado grande para anotarlo en el libro (llega hasta %s). Revisa los ceros.',
            f'{MAXIMO_CENTAVOS / 100:,.2f}')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._validar_monto(vals.get('monto'))
        return super().create(vals_list)

    def write(self, vals):
        self._validar_monto(vals.get('monto'))
        return super().write(vals)

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
        self._validar_monto(self.monto)
        centavos = a_centavos(self.monto)
        if abs(centavos) > MAXIMO_CENTAVOS:
            raise UserError(self._monto_demasiado_grande())
        # Un tope que no sea un número (no debería haber ninguno guardado) o que no cabe en el libro (más de lo que
        # cabe en un ajuste) no frena nada: nunca rompe los ajustes.
        tope = self.env['dcasa.web.reglas']._vigente(self.company_id).tope_ajuste
        if tope and numero_finito(tope) and abs(centavos) > a_centavos(tope):
            raise UserError(self.env._(
                'Un ajuste no puede pasar de %(tope)s (el tope que Gerencia puso en las reglas vigentes). Si de verdad '
                'hace falta más, pídele a Gerencia que cambie el tope en una versión nueva de las reglas.',
                tope=f'{tope:,.2f}'))
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
