from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

GRUPO_GERENTE = 'sales_team.group_sale_manager'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_vendedor_id = fields.Many2one(
        'res.partner', string='Vendedor (código VEN…)', copy=False, index='btree_not_null', ondelete='restrict',
        domain="[('dcasa_vendedor_estado', '=', 'activo')]",
        help='El vendedor del programa cuyo código dio el cliente (escribe su código VEN… o su nombre). Se anota '
             'ANTES de facturar: confirmada la venta, solo Gerencia lo cambia.')
    dcasa_vendedor_anotado_por = fields.Many2one(
        'res.users', string='Código anotado por', readonly=True, copy=False,
        help='Quién escribió el código en la venta. Queda de rastro para Gerencia.')
    dcasa_vendedor_fijo = fields.Boolean(compute='_compute_dcasa_vendedor_fijo')

    @api.depends('state')
    def _compute_dcasa_vendedor_fijo(self):
        for order in self:
            order.dcasa_vendedor_fijo = order.state in ('sale', 'done', 'cancel')

    @api.constrains('dcasa_vendedor_id', 'partner_id')
    def _check_dcasa_vendedor_no_es_el_cliente(self):
        # El carrito web nunca falla por esto (el vendedor que compra con su propio link simplemente no gana):
        # la regla se aplica al pagar. Aquí solo se avisa en el mostrador, donde alguien escribe el código a mano.
        for order in self.filtered(lambda o: o.dcasa_vendedor_id and not o.website_id):
            cliente = order.partner_id
            if not cliente._is_public() and order.dcasa_vendedor_id._dcasa_es_la_misma_persona(cliente):
                raise ValidationError(self.env._(
                    'Un vendedor no gana por sus propias compras: este cliente comparte sus datos con el vendedor.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('dcasa_vendedor_id'):
                vals.setdefault('dcasa_vendedor_anotado_por', self.env.user.id)
        return super().create(vals_list)

    def write(self, vals):
        if 'dcasa_vendedor_id' in vals:
            nuevo = vals['dcasa_vendedor_id'] or False
            for order in self.filtered(lambda o: o.dcasa_vendedor_id.id != nuevo):
                if order.state in ('sale', 'done') and not self.env.su and not self.env.user.has_group(GRUPO_GERENTE):
                    raise UserError(self.env._(
                        'La venta %s ya está confirmada: el vendedor solo lo cambia Gerencia.', order.name))
                if order.sudo().invoice_ids.dcasa_vend_comision_ids.filtered(lambda c: not c.anulada_en):
                    raise UserError(self.env._(
                        'La venta %s ya dio comisión de vendedor: primero se anula esa comisión.', order.name))
            vals.setdefault('dcasa_vendedor_anotado_por', self.env.user.id)
        return super().write(vals)

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.dcasa_vendedor_id:
            vals['dcasa_vendedor_id'] = self.dcasa_vendedor_id.id
            vals['dcasa_vendedor_anotado_por'] = self.dcasa_vendedor_anotado_por.id
        return vals
