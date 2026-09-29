from urllib.parse import urlparse

from odoo import http
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.tests import HttpCase, tagged

from ..models.ir_http import SESSION_KEY
from .common import DcasaReferralCommon


@tagged('post_install', '-at_install')
class TestReferralWebsite(DcasaReferralCommon):

    def test_cart_gets_referrer_from_session(self):
        website = self.env['website'].get_current_website()
        code = self.referrer.dcasa_referral_code
        with MockRequest(self.env, website=website) as request:
            request.session[SESSION_KEY] = code
            vals = website._prepare_sale_order_values(self.customer)
        self.assertEqual(vals.get('dcasa_referrer_id'), self.referrer.id)

    def test_cart_ignores_unknown_or_own_code(self):
        website = self.env['website'].get_current_website()
        with MockRequest(self.env, website=website) as request:
            request.session[SESSION_KEY] = 'DCNOEXISTE'
            self.assertNotIn('dcasa_referrer_id', website._prepare_sale_order_values(self.customer))
            request.session[SESSION_KEY] = self.referrer.dcasa_referral_code
            self.assertNotIn('dcasa_referrer_id', website._prepare_sale_order_values(self.referrer))


@tagged('post_install', '-at_install')
class TestReferralPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Cliente Portal',
            'login': 'cliente_portal_referidos',
            'password': 'cliente_portal_referidos',
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })

    def test_referral_link_redirects_home(self):
        self.portal_user.partner_id.action_dcasa_generate_referral_code()
        code = self.portal_user.partner_id.dcasa_referral_code
        response = self.url_open(f'/r/{code}', allow_redirects=False)
        self.assertIn(response.status_code, (301, 302, 303))
        self.assertEqual(urlparse(response.headers['Location']).path, '/')

    def test_portal_generate_and_show_code(self):
        self.authenticate('cliente_portal_referidos', 'cliente_portal_referidos')
        page = self.url_open('/my/referidos')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Generar mi código', page.text)

        self.url_open('/my/referidos/generar', data={'csrf_token': http.Request.csrf_token(self)})
        partner = self.portal_user.partner_id
        self.assertTrue(partner.dcasa_referral_code)

        page = self.url_open('/my/referidos')
        self.assertIn(partner.dcasa_referral_code, page.text)
        self.assertIn('wa.me', page.text)
