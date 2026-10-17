"""Quien compra sin cuenta con un celular, correo o RUC que ya son de una ficha NO cae en esa ficha: un dato escrito
en la tienda no prueba quién es la persona, y colgarse de su ficha le daba en el checkout las direcciones de ella
(revisión adversarial, 2026-10-17; de punta a punta en test_privacidad_checkout.py). El candado de dcasa_contactos
sigue: una persona, una ficha; la compra con datos ajenos no sigue y el aviso al visitante no dice de quién son."""
from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.website_dcasa.controllers.main import DcasaCheckout
from odoo.exceptions import ValidationError
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

    def _direccion(self, **extra):
        return {'name': 'Quien compra', 'phone': '', 'email': '', 'street': 'Calle 1', 'city': 'La Chorrera',
                'country_id': self.panama.id, 'lang': self.env.lang or 'es_419',
                'company_id': self.website.company_id.id, **extra}

    def _crear(self, tipo, **extra):
        orden = self.env['sale.order'].create({'partner_id': self.env.ref('base.public_partner').id,
                                               'website_id': self.website.id})
        with MockRequest(self.env, website=self.website):
            return DcasaCheckout()._create_new_address(self._direccion(**extra), tipo, True, orden.sudo())

    def test_un_dato_de_una_ficha_no_cuelga_la_direccion_de_ella(self):
        for extra in ({'phone': '6777-0101'}, {'email': 'FIEL@correo.com'}, {'vat': '8 777 101'},
                      {'phone': '+507 6777-0101', 'email': 'fiel@correo.com', 'vat': '8-777-101'}):
            with self.subTest(**extra), self.assertRaises(ValidationError), self.env.cr.savepoint():
                self._crear('delivery', **extra)
        self.ficha.invalidate_recordset()
        self.assertFalse(self.ficha.child_ids, 'Nada del visitante cuelga de la ficha')
        self.assertEqual(self.ficha.name, 'Clienta Fiel Tienda')  # sus datos no se tocan

    def test_quien_es_nuevo_se_crea_como_siempre(self):
        nueva = self._crear('billing', phone='6777-9999', email='nueva@correo.com')
        self.assertFalse(nueva.parent_id)
        self.assertEqual(nueva.phone, '6777-9999')
