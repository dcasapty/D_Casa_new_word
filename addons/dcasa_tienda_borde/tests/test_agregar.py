from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestAgregarDesdeElBorde(HttpCase):
    """«Agregar al carrito» de las páginas estáticas: sin token CSRF, pero solo del mismo origen."""

    def setUp(self):
        super().setUp()
        Product = self.env['product.template']
        self.mesa = Product.create({'name': 'Mesa borde prueba', 'list_price': 40, 'is_published': True})
        self.oculta = Product.create({'name': 'Mesa oculta borde', 'list_price': 40, 'is_published': False})
        talla = self.env['product.attribute'].create({
            'name': 'Tamaño borde', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Full'}), (0, 0, {'name': 'King'})],
        })
        self.cama = Product.create({
            'name': 'Cama borde prueba', 'list_price': 90, 'is_published': True,
            'attribute_line_ids': [(0, 0, {'attribute_id': talla.id, 'value_ids': [(6, 0, talla.value_ids.ids)]})],
        })
        self.authenticate(None, None)

    def _agregar(self, origen='propio', **datos):
        headers = {}
        if origen == 'propio':
            headers['Origin'] = self.base_url()
        elif origen:
            headers['Origin'] = origen
        return self.url_open('/dcasa/carrito/agregar-borde', data=datos, headers=headers, allow_redirects=False)

    def test_mismo_origen_agrega(self):
        respuesta = self._agregar(product_template_id=self.mesa.id)
        self.assertIn(respuesta.status_code, (302, 303))
        self.assertTrue(respuesta.headers['Location'].endswith('/shop/cart'))
        self.assertIn('Mesa borde prueba', self.url_open('/shop/cart').text)

    def test_otro_sitio_no(self):
        ajeno = self._agregar(origen='https://malo.example', product_template_id=self.mesa.id)
        self.assertEqual(ajeno.status_code, 403)
        self.assertEqual(self._agregar(origen=None, product_template_id=self.mesa.id).status_code, 403)
        self.assertNotIn('Mesa borde prueba', self.url_open('/shop/cart').text)

    def test_referer_o_sec_fetch_site(self):
        respuesta = self.url_open('/dcasa/carrito/agregar-borde', data={'product_template_id': self.mesa.id},
                                  headers={'Sec-Fetch-Site': 'cross-site'}, allow_redirects=False)
        self.assertEqual(respuesta.status_code, 403)
        respuesta = self.url_open('/dcasa/carrito/agregar-borde', data={'product_template_id': self.mesa.id},
                                  headers={'Referer': self.base_url() + self.mesa.website_url}, allow_redirects=False)
        self.assertIn(respuesta.status_code, (302, 303))

    def test_no_publicado_no(self):
        respuesta = self._agregar(product_template_id=self.oculta.id)
        self.assertTrue(respuesta.headers['Location'].endswith('/shop'))
        self.assertNotIn('Mesa oculta borde', self.url_open('/shop/cart').text)

    def test_variante_elegida(self):
        king = self.cama.product_variant_ids.filtered(
            lambda v: 'King' in v.product_template_attribute_value_ids.mapped('name'))
        respuesta = self._agregar(product_id=king.id)
        self.assertTrue(respuesta.headers['Location'].endswith('/shop/cart'))
        carrito = self.url_open('/shop/cart').text
        self.assertIn('Cama borde prueba', carrito)
        self.assertIn('King', carrito)

    def test_plantilla_con_variantes_va_a_la_ficha(self):
        respuesta = self._agregar(product_template_id=self.cama.id)
        self.assertTrue(respuesta.headers['Location'].endswith(self.cama.website_url))

    def test_entrada_basura(self):
        for valor in ('abc', '-1', str(2**40)):
            respuesta = self._agregar(product_template_id=valor)
            self.assertTrue(respuesta.headers['Location'].endswith('/shop'))
