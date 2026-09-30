from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models import reglas as R


class DcasaCobrarPremioWizard(models.TransientModel):
    """Cobra el código de un premio dentro de una venta.

    El importe lo pone el premio, no quien teclea; y solo lo usa quien lo ganó.
    Se marca entregado al confirmar la venta, en la misma transacción.
    """

    _name = 'dcasa.cobrar.premio.wizard'
    _description = 'Cobrar premio en una venta'

    order_id = fields.Many2one('sale.order', required=True, readonly=True)
    codigo = fields.Char(string='Código del premio', required=True)
    canje_id = fields.Many2one('dcasa.canje', compute='_compute_canje_id')

    @api.depends('codigo')
    def _compute_canje_id(self):
        for wizard in self:
            codigo = R.codigo_normal(wizard.codigo)
            wizard.canje_id = self.env['dcasa.canje'].sudo().search([('codigo', '=', codigo)], limit=1) \
                if codigo else False

    def action_confirmar(self):
        self.ensure_one()
        canje = self.canje_id
        order = self.order_id
        if not canje:
            raise UserError(self.env._('Ese código no existe. Revísalo.'))
        if canje.partner_id != order.partner_id.commercial_partner_id:
            raise UserError(self.env._('El premio %s es de otro cliente. Solo lo puede usar quien lo ganó.',
                                       canje.codigo))
        if canje.estado != 'solicitado':
            raise UserError(self.env._('El premio %s ya no está pendiente.', canje.codigo))
        if order.order_line.filtered(lambda line: line.dcasa_canje_id == canje):
            raise UserError(self.env._('Ese premio ya está en esta venta.'))
        if canje.premio_tipo == 'producto':
            raise UserError(self.env._('Los premios de producto se entregan desde Socios > Canjes.'))
        producto = self.env.ref('dcasa_socios.product_premio_canje')
        order.write({'order_line': [(0, 0, {
            'product_id': producto.id,
            'name': self.env._('Premio %(codigo)s: %(premio)s', codigo=canje.codigo, premio=canje.premio_nombre),
            'product_uom_qty': 1,
            # Lo pagado con puntos rebaja la base, igual que un descuento (el ITBMS se calcula después).
            'price_unit': -canje.valor,
            # ITBMS explícito: el producto puede haberse creado antes de cargar el plan contable.
            'tax_ids': [(6, 0, (producto.taxes_id or order.company_id.account_sale_tax_id).ids)],
            'dcasa_canje_id': canje.id,
        })]})
        return {'type': 'ir.actions.act_window_close'}
