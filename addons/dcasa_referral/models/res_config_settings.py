from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_referral_reward_type = fields.Selection(
        related='company_id.dcasa_referral_reward_type', readonly=False)
    dcasa_referral_reward_value = fields.Float(
        related='company_id.dcasa_referral_reward_value', readonly=False)
    dcasa_referral_min_amount = fields.Monetary(
        related='company_id.dcasa_referral_min_amount', readonly=False)
    dcasa_referral_first_purchase_only = fields.Boolean(
        related='company_id.dcasa_referral_first_purchase_only', readonly=False)
