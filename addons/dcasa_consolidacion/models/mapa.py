"""Mapa de cuentas: a qué cuenta consolidada va cada cuenta de cada empresa.

Por omisión las cuentas se unen por **código** (las empresas de D'CASA usan el mismo plan ``l10n_pa``).
Este mapa solo hace falta cuando los planes difieren: lo que esté aquí manda sobre el código.
Una cuenta que no está en el mapa se une por su código; una cuenta que solo existe en una empresa
aparece igual en el consolidado.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DcasaConsolidacionMapa(models.Model):
    _name = 'dcasa.consolidacion.mapa'
    _description = 'Mapa de cuentas para consolidar'
    _order = 'company_id, codigo_consolidado, id'

    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True,
                                 default=lambda self: self.env.company)
    account_id = fields.Many2one('account.account', 'Cuenta de la empresa', required=True, index=True,
                                 ondelete='cascade', domain="[('company_ids', 'in', company_id)]")
    codigo_cuenta = fields.Char('Código en la empresa', compute='_compute_codigo_cuenta')
    tipo_cuenta = fields.Selection(related='account_id.account_type', string='Tipo de cuenta', store=True,
                                   help='Sirve para ver que las cuentas que se unen en un mismo código sean del '
                                        'mismo tipo: una de ingresos y una de gastos con el mismo código darían un '
                                        'consolidado sin sentido.')
    codigo_consolidado = fields.Char(
        'Código consolidado', required=True,
        help='Las cuentas de cualquier empresa con este mismo código consolidado se suman en una sola fila.')
    nombre_consolidado = fields.Char(
        'Nombre consolidado',
        help='Opcional. Si lo dejas vacío se usa el nombre de la cuenta de la primera empresa del grupo.')

    _cuenta_unica = models.Constraint('UNIQUE(company_id, account_id)',
                                      'Esa cuenta ya está en el mapa de esa empresa.')

    @api.depends('account_id', 'company_id')
    def _compute_codigo_cuenta(self):
        for mapa in self:
            mapa.codigo_cuenta = mapa.account_id.with_company(mapa.company_id).code if mapa.company_id else False

    @api.constrains('company_id', 'account_id')
    def _check_cuenta_de_la_empresa(self):
        for mapa in self:
            if mapa.company_id not in mapa.account_id.sudo().company_ids:
                raise ValidationError(self.env._('La cuenta %(cuenta)s no pertenece a la empresa %(empresa)s.',
                                                 cuenta=mapa.account_id.display_name, empresa=mapa.company_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._limpiar(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._limpiar(vals)
        return super().write(vals)

    @api.model
    def _limpiar(self, vals):
        """El código consolidado se guarda sin espacios sobrantes (si no, «4101 » y «4101» no se unirían)."""
        for campo in ('codigo_consolidado', 'nombre_consolidado'):
            if isinstance(vals.get(campo), str):
                vals[campo] = vals[campo].strip() or False
