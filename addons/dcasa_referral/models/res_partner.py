import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Sin 0/O ni 1/I/L para que el código se pueda dictar por WhatsApp sin errores.
CODE_ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'
CODE_PREFIX = 'DC'
CODE_LENGTH = 6


def normalize_referral_code(code):
    return (code or '').strip().upper()[:32]


class ResPartner(models.Model):
    _inherit = 'res.partner'
    # Permite buscar al referidor por su código en cualquier campo Many2one.
    _rec_names_search = ['complete_name', 'email', 'ref', 'vat', 'company_registry', 'dcasa_referral_code']

    dcasa_referral_code = fields.Char(
        string='Código de referido', copy=False, readonly=True, index='btree_not_null',
        help='Código que el cliente comparte para referir a otros.',
    )
    dcasa_referral_url = fields.Char(string='Link de referido', compute='_compute_dcasa_referral_url')
    dcasa_referrer_id = fields.Many2one(
        'res.partner', string='Referido por', copy=False, index='btree_not_null',
        domain="[('dcasa_referral_code', '!=', False)]",
        help='Cliente que refirió a este contacto. Se asigna en su primera venta confirmada.',
    )
    dcasa_referred_ids = fields.One2many('res.partner', 'dcasa_referrer_id', string='Clientes referidos')
    dcasa_referred_count = fields.Integer(string='N.º de referidos', compute='_compute_dcasa_referral_stats')
    dcasa_referral_reward_ids = fields.One2many(
        'dcasa.referral.reward', 'referrer_id', string='Recompensas de referidos')
    dcasa_referral_balance = fields.Monetary(
        string='Recompensas por pagar', compute='_compute_dcasa_referral_stats',
        currency_field='currency_id',
        help='Recompensas ganadas (factura del referido pagada) que aún no se le pagan al cliente.',
    )

    _dcasa_referral_code_unique = models.Constraint(
        'UNIQUE(dcasa_referral_code)',
        'Ese código de referido ya está en uso.',
    )

    @api.depends('dcasa_referral_code')
    def _compute_dcasa_referral_url(self):
        for partner in self:
            partner.dcasa_referral_url = (
                f'{partner.get_base_url()}/r/{partner.dcasa_referral_code}'
                if partner.dcasa_referral_code else False
            )

    @api.depends('dcasa_referred_ids', 'dcasa_referral_reward_ids.state', 'dcasa_referral_reward_ids.amount')
    def _compute_dcasa_referral_stats(self):
        for partner in self:
            partner.dcasa_referred_count = len(partner.dcasa_referred_ids)
            partner.dcasa_referral_balance = sum(
                partner.dcasa_referral_reward_ids.filtered(lambda r: r.state == 'earned').mapped('amount')
            )

    @api.constrains('dcasa_referrer_id')
    def _check_dcasa_referrer_id(self):
        for partner in self:
            referrer = partner.dcasa_referrer_id
            if not referrer:
                continue
            if referrer.commercial_partner_id == partner.commercial_partner_id:
                raise ValidationError(self.env._('Un cliente no puede referirse a sí mismo.'))
            if referrer.dcasa_referrer_id.commercial_partner_id == partner.commercial_partner_id:
                raise ValidationError(self.env._(
                    '%(referrer)s ya fue referido por %(partner)s: no pueden referirse mutuamente.',
                    referrer=referrer.display_name, partner=partner.display_name,
                ))

    @api.model
    def _dcasa_new_referral_code(self):
        while True:
            code = CODE_PREFIX + ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if not self.sudo().search_count([('dcasa_referral_code', '=', code)], limit=1):
                return code

    def action_dcasa_generate_referral_code(self):
        for partner in self.filtered(lambda p: not p.dcasa_referral_code):
            partner.sudo().dcasa_referral_code = self._dcasa_new_referral_code()
        return True

    @api.model
    def _dcasa_find_by_referral_code(self, code):
        code = normalize_referral_code(code)
        if not code:
            return self.browse()
        return self.sudo().search([('dcasa_referral_code', '=', code)], limit=1)

    def action_dcasa_view_referral_rewards(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dcasa_referral.action_dcasa_referral_reward')
        action['domain'] = [('referrer_id', '=', self.id)]
        action['context'] = {'default_referrer_id': self.id}
        return action
