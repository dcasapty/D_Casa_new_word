from odoo import api, fields, models
from odoo.exceptions import UserError

STATES = [
    ('pending', 'Pendiente de pago'),
    ('earned', 'Ganada'),
    ('paid', 'Pagada al referidor'),
    ('cancelled', 'Anulada'),
]


class DcasaReferralReward(models.Model):
    _name = 'dcasa.referral.reward'
    _description = 'Recompensa de referido'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(string='Referencia', required=True, readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)
    referrer_id = fields.Many2one(
        'res.partner', string='Referidor', required=True, readonly=True, index=True, ondelete='restrict')
    referred_partner_id = fields.Many2one(
        'res.partner', string='Cliente referido', required=True, readonly=True, index=True, ondelete='restrict')
    move_id = fields.Many2one(
        'account.move', string='Factura', required=True, readonly=True, index=True, ondelete='restrict',
        check_company=True)
    sale_order_ids = fields.Many2many(
        'sale.order', string='Órdenes de venta', compute='_compute_sale_order_ids')
    invoice_date = fields.Date(related='move_id.invoice_date', store=True, string='Fecha de factura')
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)
    base_amount = fields.Monetary(string='Subtotal de la factura', readonly=True,
                                  help='Subtotal sin ITBMS sobre el que se calculó la recompensa.')
    amount = fields.Monetary(string='Recompensa', readonly=True, tracking=True)
    payout_date = fields.Date(string='Pagada el', readonly=True, copy=False, tracking=True)
    payout_note = fields.Char(string='Nota del pago', copy=False,
                              help='Cómo se pagó: efectivo, transferencia, crédito en tienda…')
    state = fields.Selection(
        STATES, string='Estado', compute='_compute_state', store=True, index=True, tracking=True)

    _move_unique = models.Constraint('UNIQUE(move_id)', 'Ya existe una recompensa para esta factura.')

    @api.depends('move_id.state', 'move_id.payment_state', 'payout_date')
    def _compute_state(self):
        for reward in self:
            move = reward.move_id
            if reward.payout_date:
                reward.state = 'paid'
            elif move.state == 'cancel' or move.payment_state == 'reversed':
                reward.state = 'cancelled'
            elif move.state == 'posted' and move.payment_state in ('paid', 'in_payment'):
                reward.state = 'earned'
            else:
                reward.state = 'pending'

    @api.depends('move_id')
    def _compute_sale_order_ids(self):
        for reward in self:
            reward.sale_order_ids = reward.move_id.line_ids.sale_line_ids.order_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dcasa.referral.reward') or '/'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Generación
    # ------------------------------------------------------------------

    @api.model
    def _compute_reward_amount(self, move):
        """Recompensa que genera ``move`` según la configuración de su empresa."""
        company = move.company_id
        if company.dcasa_referral_reward_type == 'fixed':
            return company.currency_id._convert(
                company.dcasa_referral_reward_value, move.currency_id, company,
                move.invoice_date or fields.Date.context_today(self),
            )
        return move.currency_id.round(move.amount_untaxed * company.dcasa_referral_reward_value / 100.0)

    @api.model
    def _create_for_invoices(self, moves):
        """Crea la recompensa (pendiente) de cada factura de cliente con referidor."""
        already_rewarded = set(self.search([('move_id', 'in', moves.ids)]).move_id.ids)
        vals_list = []
        for move in moves:
            referrer = move.dcasa_referrer_id
            referred = move.commercial_partner_id
            company = move.company_id
            if (
                move.move_type != 'out_invoice'
                or not referrer
                or move.id in already_rewarded
                or referrer.commercial_partner_id == referred
                or move.amount_untaxed <= 0
                or move.amount_untaxed < company.dcasa_referral_min_amount
            ):
                continue
            if company.dcasa_referral_first_purchase_only and self.search_count([
                ('company_id', '=', company.id),
                ('referred_partner_id', '=', referred.id),
                ('state', '!=', 'cancelled'),
            ], limit=1):
                continue
            amount = self._compute_reward_amount(move)
            if move.currency_id.is_zero(amount):
                continue
            vals_list.append({
                'company_id': company.id,
                'referrer_id': referrer.id,
                'referred_partner_id': referred.id,
                'move_id': move.id,
                'currency_id': move.currency_id.id,
                'base_amount': move.amount_untaxed,
                'amount': amount,
            })
        return self.create(vals_list)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def action_mark_paid(self):
        not_earned = self.filtered(lambda r: r.state != 'earned')
        if not_earned:
            raise UserError(self.env._(
                'Solo se pueden pagar recompensas ganadas (factura del referido pagada): %s',
                ', '.join(not_earned.mapped('name')),
            ))
        self.payout_date = fields.Date.context_today(self)
        return True

    def action_undo_payout(self):
        self.filtered(lambda r: r.state == 'paid').payout_date = False
        return True

    def action_open_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }
