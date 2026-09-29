import re

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWhatsappLink(TransactionCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')

    def test_whatsapp_url_uses_configured_number(self):
        self.website.dcasa_whatsapp_number = '+507 6026-1919'
        url = self.website._dcasa_whatsapp_url('Hola D\'CASA')
        self.assertTrue(url.startswith('https://wa.me/50760261919?text='))
        self.assertIn('Hola%20D%27CASA', url)

    def test_whatsapp_url_falls_back_to_company_phone(self):
        self.website.dcasa_whatsapp_number = False
        self.website.company_id.phone = '+507 6000-1111'
        self.assertTrue(self.website._dcasa_whatsapp_url().startswith('https://wa.me/50760001111'))

    def test_whatsapp_url_without_number_goes_to_contact(self):
        self.website.dcasa_whatsapp_number = False
        self.website.company_id.phone = False
        self.assertEqual(self.website._dcasa_whatsapp_url(), '/contactus')


@tagged('post_install', '-at_install')
class TestWebsitePages(HttpCase):

    def test_homepage(self):
        response = self.url_open('/')
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('Tu casa, bien amueblada.', html)
        self.assertIn('https://wa.me/50760261919', html)
        self.assertIn('o_dcasa_wa_float', html)
        salas = self.env.ref('website_dcasa.public_category_salas')
        self.assertIn(f'/shop/category/{salas.id}', html)
        self.assertIn('info@dcasapty.com', html, 'El pie de página muestra los datos reales')
        self.assertNotIn('555-555-5556', html, 'No debe quedar el teléfono de ejemplo de Odoo')
        self.assertNotIn('Company name', html, 'No debe quedar el copyright de ejemplo de Odoo')

    def test_referral_page(self):
        response = self.url_open('/referidos')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Refiere y gana', response.text)
        self.assertIn('/my/referidos', response.text)

    def test_shop(self):
        self.assertEqual(self.url_open('/shop').status_code, 200)

    def test_frontend_css_compiles_with_brand(self):
        html = self.url_open('/').text
        css_links = re.findall(r'href="([^"]*web\.assets_frontend[^"]*\.css)"', html)
        self.assertTrue(css_links, 'La página debe enlazar el bundle CSS del sitio')
        css = self.url_open(css_links[0]).text
        self.assertIn('o_dcasa_card', css)
        self.assertIn('o_dcasa_wa_float', css)
        self.assertRegex(css.lower(), r'#1340b1|rgb\(19,\s*64,\s*177\)')
