from odoo import fields, models
from odoo.exceptions import UserError

from ..models.res_partner_vend import TIPOS_VENDEDOR


class DcasaAfiliarVendedorWizard(models.TransientModel):
    """Afilia a una persona como vendedor, en caja o en Gerencia.

    El consentimiento lo da la persona: aquí solo se anota que lo dio, quién lo recogió y qué versión de los términos
    leyó. Sin cédula, sin celular válido y sin esa casilla no hay afiliación.
    """

    _name = 'dcasa.afiliar.vendedor.wizard'
    _description = 'Afiliar a un vendedor'

    partner_id = fields.Many2one('res.partner', string='Persona', required=True, readonly=True)
    tipo = fields.Selection(TIPOS_VENDEDOR, required=True, string='Es')
    patrocinador_id = fields.Many2one(
        'res.partner', string='Patrocinado por', domain="[('dcasa_vendedor_estado', '=', 'activo')]",
        help='Código VEN… o nombre del vendedor que lo trajo. Se escribe una vez y no se cambia jamás.')
    acepta = fields.Boolean(string='La persona leyó y aceptó los términos', required=True)

    def action_confirmar(self):
        self.ensure_one()
        self.partner_id._dcasa_exigir_grupo('sales_team.group_sale_salesman')
        if not self.acepta:
            raise UserError(self.env._('La persona tiene que leer y aceptar los términos del programa de vendedores.'))
        self.partner_id._dcasa_afiliar_vendedor(
            self.tipo, self.patrocinador_id, autor=self.env.user.login, acepto_terminos=True)
        return {'type': 'ir.actions.act_window_close'}


class DcasaVendAjusteWizard(models.TransientModel):
    """Corrección manual del saldo de un vendedor. Lleva motivo porque el vendedor lo lee en su cuenta."""

    _name = 'dcasa.vend.ajuste.wizard'
    _description = 'Ajustar puntos de un vendedor'

    partner_id = fields.Many2one('res.partner', string='Vendedor', required=True, readonly=True)
    saldo = fields.Integer(related='partner_id.dcasa_vend_saldo', string='Saldo actual')
    puntos = fields.Integer(required=True, help='Positivo suma, negativo resta.')
    motivo = fields.Char(required=True, help='Escríbelo pensando en que lo va a leer el vendedor.')

    def action_confirmar(self):
        self.ensure_one()
        self.partner_id._dcasa_exigir_grupo('sales_team.group_sale_manager')
        if not self.puntos:
            raise UserError(self.env._('El ajuste tiene que ser un número distinto de cero.'))
        if not (self.motivo or '').strip():
            raise UserError(self.env._('Escribe por qué: el vendedor lo va a leer tal cual en su cuenta.'))
        if self.puntos < 0 and self.saldo + self.puntos < 0:
            raise UserError(self.env._('No se le pueden quitar %(quitar)s puntos: solo tiene %(saldo)s.',
                                       quitar=abs(self.puntos), saldo=self.saldo))
        if not self.partner_id.dcasa_vendedor_codigo:
            raise UserError(self.env._('Esta persona no es vendedora.'))
        self.env['dcasa.vend.movimiento']._asentar(
            self.partner_id, 'ajuste', self.puntos, self.env.user.login, motivo=self.motivo.strip())
        return {'type': 'ir.actions.act_window_close'}
