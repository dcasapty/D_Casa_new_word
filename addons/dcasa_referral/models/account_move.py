from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_referrer_id = fields.Many2one(
        'res.partner', string='Referido por', copy=False, index='btree_not_null',
        compute='_compute_dcasa_referrer_id', store=True, readonly=False, precompute=True,
        domain="[('dcasa_referral_code', '!=', False)]",
        help='Cliente que refirió al comprador. Si se llena, la factura genera una recompensa al publicarse.',
    )
    dcasa_referral_reward_ids = fields.One2many('dcasa.referral.reward', 'move_id', string='Recompensas')

    @api.depends('partner_id', 'move_type')
    def _compute_dcasa_referrer_id(self):
        for move in self:
            if move.move_type != 'out_invoice':
                move.dcasa_referrer_id = False
            elif not move.dcasa_referrer_id:
                move.dcasa_referrer_id = move.partner_id.commercial_partner_id.dcasa_referrer_id

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        self.env['dcasa.referral.reward'].sudo()._create_for_invoices(posted)
        return posted
