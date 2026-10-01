import json
import re

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPrecioMasItbms(HttpCase):
    """Los precios de D'CASA son sin ITBMS: la web dice «$39.99 + ITBMS» y el carrito suma el 7 %."""

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        Product = self.env['product.template']
        # Sin impuesto explícito: nace con el ITBMS de venta por defecto (el que se suma).
        self.mesa = Product.create({
            'name': 'Mesa ITBMS prueba', 'list_price': 39.99, 'is_published': True,
            'website_sequence': -300,
        })
        self.sin_impuesto = Product.create({
            'name': 'Servicio sin impuesto prueba', 'list_price': 15.0, 'is_published': True,
            'taxes_id': [(5, 0, 0)], 'website_sequence': -299,
        })

    def test_tienda_muestra_precio_sin_itbms(self):
        self.assertEqual(self.website.show_line_subtotals_tax_selection, 'tax_excluded')
        self.assertFalse(self.mesa.taxes_id.price_include)
        self.assertTrue(self.website._dcasa_mas_itbms(self.mesa))
        self.assertFalse(self.website._dcasa_mas_itbms(self.sin_impuesto), 'Sin impuesto, sin leyenda')

    def test_ficha_dice_mas_itbms(self):
        html = self.url_open(self.mesa.website_url).text
        self.assertIn('o_dcasa_mas_itbms', html)
        self.assertIn('+ ITBMS', html)
        self.assertIn('39.99', html)
        self.assertNotIn('42.79', html, 'La ficha muestra el precio sin ITBMS')
        self.assertNotIn('o_dcasa_mas_itbms', self.url_open(self.sin_impuesto.website_url).text)

    def test_json_ld_con_precio_sin_itbms(self):
        html = self.url_open(self.mesa.website_url).text
        bloques = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
        productos = []
        for bloque in bloques:
            datos = json.loads(bloque)
            productos += [d for d in (datos if isinstance(datos, list) else [datos]) if d.get('@type') == 'Product']
        self.assertEqual(len(productos), 1)
        self.assertEqual(productos[0]['offers']['price'], 39.99)
        self.assertEqual(productos[0]['offers']['priceCurrency'], 'USD')

    def test_listado_y_portada_dicen_mas_itbms(self):
        tienda = self.url_open('/shop?search=Mesa ITBMS prueba').text
        self.assertIn('Mesa ITBMS prueba', tienda)
        self.assertIn('+ ITBMS', tienda)
        portada = self.url_open('/').text
        tarjeta = re.search(r'Mesa ITBMS prueba.*?o_dcasa_pcard_actions', portada, re.S).group(0)
        self.assertIn('39.99', tarjeta)
        self.assertIn('+ ITBMS', tarjeta)

    def test_carrito_suma_el_itbms(self):
        self.authenticate(None, None)
        home = self.url_open('/').text
        token = re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', home).group(1)
        self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token, 'product_template_id': self.mesa.id,
        }, allow_redirects=False)
        carrito = self.url_open('/shop/cart').text
        self.assertIn('Mesa ITBMS prueba', carrito)
        for cifra in ('39.99', '2.80', '42.79'):
            self.assertIn(cifra, carrito, 'Subtotal, ITBMS y total')
