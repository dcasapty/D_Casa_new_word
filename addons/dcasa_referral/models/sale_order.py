from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_referrer_id = fields.Many2one(
        'res.partner', string='Referido por', copy=False, index='btree_not_null',
        compute='_compute_dcasa_referrer_id', store=True, readonly=False, precompute=True,
        domain="[('dcasa_referral_code', '!=', False)]", tracking=True,
        help='Cliente que refirió al comprador. Escribe su código o su nombre.',
    )

    @api.depends('partner_id')
    def _compute_dcasa_referrer_id(self):
        for order in self:
            # El referidor ya registrado en el cliente manda; si no tiene, se
            # conserva el de la orden (p. ej. el que llegó por el link web).
            order.dcasa_referrer_id = (
                order.partner_id.commercial_partner_id.dcasa_referrer_id or order.dcasa_referrer_id
            )

    def _dcasa_valid_referrer(self):
        self.ensure_one()
        referrer = self.dcasa_referrer_id
        customer = self.partner_id.commercial_partner_id
        # El usuario público (visitante sin sesión) está archivado: buscarlo con active_test=False.
        is_public = any(user._is_public() for user in customer.with_context(active_test=False).user_ids)
        if not referrer or is_public or referrer.commercial_partner_id == customer:
            return self.env['res.partner']
        return referrer

    def action_confirm(self):
        res = super().action_confirm()
        # La primera venta confirmada fija al referidor del cliente.
        for order in self:
            customer = order.partner_id.commercial_partner_id
            referrer = order._dcasa_valid_referrer()
            if referrer and not customer.dcasa_referrer_id:
                customer.sudo().dcasa_referrer_id = referrer
        return res

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        referrer = self._dcasa_valid_referrer()
        if referrer:
            vals['dcasa_referrer_id'] = referrer.id
        return vals
