"""Quien compra sin cuenta con un celular, correo o RUC que ya son de una ficha cae en ESA ficha (dcasa_contactos)."""
from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.website_dcasa.controllers.main import DcasaCheckout
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDireccionDelVisitante(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.panama = cls.env.ref('base.pa')
        cls.ficha = cls.env['res.partner'].create({
            'name': 'Clienta Fiel Tienda', 'phone': '+507 6777-0101', 'email': 'fiel@correo.com', 'vat': '8-777-101'})
        cls.antes = cls.env['res.partner'].with_context(active_test=False).search_count([])

    def _direccion(self, **extra):
        return {'name': 'Quien compra', 'phone': '', 'email': '', 'street': 'Calle 1', 'city': 'La Chorrera',
                'country_id': self.panama.id, 'lang': self.env.lang or 'es_419',
                'company_id': self.website.company_id.id, **extra}

    def _crear(self, tipo, **extra):
        orden = self.env['sale.order'].create({'partner_id': self.env.ref('base.public_partner').id,
                                               'website_id': self.website.id})
        with MockRequest(self.env, website=self.website):
            return DcasaCheckout()._create_new_address(self._direccion(**extra), tipo, True, orden.sudo())

    def test_el_mismo_celular_cuelga_la_direccion_de_la_ficha(self):
        nueva = self._crear('delivery', phone='6777-0101')
        self.assertEqual(nueva.parent_id, self.ficha)
        self.assertEqual(nueva.commercial_partner_id, self.ficha)
        self.assertEqual(self.ficha.name, 'Clienta Fiel Tienda')  # sus datos no se tocan

    def test_el_mismo_correo_o_ruc_tambien(self):
        self.assertEqual(self._crear('billing', email='FIEL@correo.com').parent_id, self.ficha)
        self.assertEqual(self._crear('billing', vat='8 777 101').parent_id, self.ficha)

    def test_quien_es_nuevo_se_crea_como_siempre(self):
        nueva = self._crear('billing', phone='6777-9999', email='nueva@correo.com')
        self.assertFalse(nueva.parent_id)
        self.assertEqual(nueva.phone, '6777-9999')

    def test_un_cliente_nuevo_con_datos_ajenos_no_rompe_la_compra(self):
        # sin la reutilización esto fallaría con «ese correo ya está registrado»
        nueva = self._crear('delivery', phone='+507 6777-0101', email='fiel@correo.com', vat='8-777-101')
        self.assertTrue(nueva.id)
        self.assertEqual(nueva.parent_id, self.ficha)
