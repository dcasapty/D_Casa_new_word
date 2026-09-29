from urllib.parse import quote

from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request

from ..models.ir_http import SESSION_KEY
from ..models.res_partner import normalize_referral_code


class DcasaReferral(http.Controller):

    @http.route('/r/<string:code>', type='http', auth='public', website=True, sitemap=False)
    def referral_link(self, code, **kwargs):
        """Link que comparte el cliente: guarda el código y lleva a la tienda."""
        referrer = request.env['res.partner']._dcasa_find_by_referral_code(code)
        if referrer:
            request.session[SESSION_KEY] = normalize_referral_code(code)
        return request.redirect('/')


class DcasaReferralPortal(CustomerPortal):

    def _dcasa_referrer(self):
        return request.env.user.partner_id

    @http.route('/my/referidos', type='http', auth='user', website=True)
    def portal_my_referrals(self, **kwargs):
        partner = self._dcasa_referrer()
        rewards = request.env['dcasa.referral.reward'].sudo().search([('referrer_id', '=', partner.id)])
        totals = {
            state: sum(rewards.filtered(lambda r, s=state: r.state == s).mapped('amount'))
            for state in ('pending', 'earned', 'paid')
        }
        share_text = (
            f"Mira D'CASA Panamá, tienen de todo para la casa. "
            f"Compra con mi código {partner.dcasa_referral_code}: {partner.dcasa_referral_url}"
        ) if partner.dcasa_referral_code else ''
        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'dcasa_referrals',
            'partner': partner,
            'rewards': rewards,
            'totals': totals,
            'currency': request.env.company.currency_id,
            'whatsapp_share_url': f'https://wa.me/?text={quote(share_text)}' if share_text else '',
        })
        return request.render('dcasa_referral.portal_my_referrals', values)

    @http.route('/my/referidos/generar', type='http', auth='user', website=True, methods=['POST'])
    def portal_generate_referral_code(self, **kwargs):
        self._dcasa_referrer().sudo().action_dcasa_generate_referral_code()
        return request.redirect('/my/referidos')
