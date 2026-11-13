"""La invitación a opinar en el correo de la factura pagada (lote 2 de la web): solo pagada por completo y solo si de
esa factura le queda algo por opinar (a la vista en la tienda y sin opinión). Nunca con saldo."""
from unittest.mock import patch

from odoo.tests import tagged

from .common import CorreoCase

MI_CUENTA = 'odoo.addons.dcasa_correo.models.correo.DcasaCorreo._mi_cuenta_instalado'


@tagged('post_install', '-at_install')
class TestInvitacionAOpinar(CorreoCase):

    def setUp(self):
        super().setUp()
        self.mueble.is_published = True
        self.startPatcher(patch(MI_CUENTA, return_value=True))

    def test_pagada_invita_a_mi_cuenta(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura)
        valores = factura._dcasa_correo_valores()
        self.assertTrue(valores['pagada'])
        self.assertEqual(valores['opinar'], f"{valores['enlaces']['cuenta']}/opiniones")
        self.procesar()
        (correo,) = self.correos_de(factura)
        self.assertIn('Mi cuenta › Tus opiniones', correo.body_html)
        self.assertIn('/mi-cuenta/opiniones', correo.body_html)

    def test_con_saldo_no_invita(self):
        factura = self.factura()
        self.pagar(factura, 50.0)
        valores = factura._dcasa_correo_valores()
        self.assertTrue(valores['con_saldo'])
        self.assertEqual(valores['opinar'], '')

    def test_sin_nada_por_opinar_no_invita(self):
        self.mueble.is_published = False
        factura = self.factura()
        self.pagar(factura)
        self.assertEqual(factura._dcasa_correo_valores()['opinar'], '', 'No está en la tienda')
        self.mueble.is_published = True
        self.env['dcasa.resena']._dcasa_crear_del_cliente(self.ana, self.mueble.product_tmpl_id.id, 5)
        self.assertEqual(factura._dcasa_correo_valores()['opinar'], '', 'Ya opinó de lo que trae esta factura')

    def test_sin_mi_cuenta_no_invita(self):
        factura = self.factura()
        self.pagar(factura)
        with patch(MI_CUENTA, return_value=False):
            self.assertEqual(factura._dcasa_correo_valores()['opinar'], '')
