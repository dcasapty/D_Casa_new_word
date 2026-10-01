from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_socio_codigo = fields.Char(related='partner_id.commercial_partner_id.dcasa_socio_codigo',
                                     string='Código de socio')
    dcasa_socio_saldo = fields.Integer(related='partner_id.commercial_partner_id.dcasa_saldo',
                                       string='Puntos del cliente')
    dcasa_referido_por_id = fields.Many2one(
        'res.partner', string='Invitado por', copy=False, index='btree_not_null',
        compute='_compute_dcasa_referido_por_id', store=True, readonly=False, precompute=True,
        domain="[('dcasa_socio_codigo', '!=', False)]",
        help='Quién invitó a este cliente (escribe su código DCA… o su nombre). Solo se registra si el '
             'cliente todavía no tiene padrino y no ha comprado con puntos; después no se cambia nunca.')
    dcasa_padrino_fijo = fields.Boolean(compute='_compute_dcasa_padrino_fijo')

    @api.depends('partner_id')
    def _compute_dcasa_referido_por_id(self):
        for order in self:
            padrino = order.partner_id.commercial_partner_id.dcasa_referido_por_id
            # El padrino ya registrado manda; si no hay, se conserva la propuesta (p. ej. el link web).
            order.dcasa_referido_por_id = padrino or order.dcasa_referido_por_id

    @api.depends('partner_id')
    def _compute_dcasa_padrino_fijo(self):
        for order in self:
            order.dcasa_padrino_fijo = bool(order.partner_id.commercial_partner_id.dcasa_referido_por_id)

    def action_confirm(self):
        # Los premios se sellan en la misma transacción que la venta: si alguno ya
        # no está disponible, la venta entera no se confirma. El permiso de escribir la
        # venta se comprueba ANTES de sellar premios con sudo (método público por RPC).
        self.check_access('write')
        for order in self:
            order.order_line.dcasa_canje_id._entregar(
                self.env.user.login, sale_order=order, partner=order.partner_id.commercial_partner_id)
        res = super().action_confirm()
        for order in self.filtered('dcasa_referido_por_id'):
            if not order.partner_id.commercial_partner_id._is_public():
                order.partner_id._dcasa_asignar_padrino(order.dcasa_referido_por_id)
        return res

    def action_dcasa_cobrar_premio(self):
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(self.env._('Los premios se cobran antes de confirmar la venta.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Cobrar premio'),
            'res_model': 'dcasa.cobrar.premio.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_canje_id = fields.Many2one('dcasa.canje', string='Premio cobrado', readonly=True, copy=False,
                                     index='btree_not_null', ondelete='restrict')

    def _dcasa_exenta_tope_descuento(self):
        # La línea de premio es negativa por diseño: la pagan los puntos, no la vendedora.
        return super()._dcasa_exenta_tope_descuento() or bool(self.dcasa_canje_id)

