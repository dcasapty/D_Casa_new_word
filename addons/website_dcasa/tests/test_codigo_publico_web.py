"""Lo que ve el cliente en el sitio: el código público (DC-K7M4PX) y nunca la referencia del proveedor.

Pedido de la dueña: «El cliente no tiene que conocer nuestros códigos actuales de proveedores». La referencia interna
(``default_code``) se filtraba sin verse escrita en la ficha: en la dirección de la página, en el mensaje de WhatsApp
que se manda a la tienda, en el nombre de cada foto, en el texto alternativo y en los datos estructurados para Google.
"""
import json
import re
from urllib.parse import unquote

from odoo.addons.website_dcasa.tests.test_imagen import foto
from odoo.tests import HttpCase, tagged

REFERENCIA = 'ZZPROV-9981-X'
CLAVE = REFERENCIA.lower()


@tagged('post_install', '-at_install')
class TestCodigoPublicoEnLaWeb(HttpCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.producto = self.env['product.template'].create({
            'name': 'CAMA DE PRUEBA DEL CÓDIGO', 'list_price': 120.0, 'is_published': True, 'sale_ok': True,
            'default_code': REFERENCIA, 'image_1920': foto(600, 600), 'website_sequence': -100000,
            'public_categ_ids': [(6, 0, self.env.ref('website_dcasa.public_category_recamaras').ids)],
        })
        self.codigo = self.producto.dcasa_codigo_publico

    def _sin_referencia(self, html, donde):
        for variante in (REFERENCIA, CLAVE):
            self.assertNotIn(variante, html, f'La referencia del proveedor se ve en {donde}')

    def test_la_ficha_muestra_el_codigo_publico_y_no_la_referencia(self):
        html = self.url_open(self.producto.website_url).text
        self.assertRegex(html, rf'Código:\s*<strong>{re.escape(self.codigo)}</strong>')
        self._sin_referencia(html, 'la ficha')

    def test_la_direccion_de_la_ficha_no_lleva_la_referencia(self):
        self.assertNotIn(CLAVE, self.producto.website_url)
        self.assertEqual(self.producto.website_url, f'/shop/cama-de-prueba-del-codigo-{self.producto.id}')
        # La dirección vieja (con la referencia) sigue sirviendo: redirige a la nueva.
        vieja = f'/shop/{CLAVE}-cama-de-prueba-del-codigo-{self.producto.id}'
        respuesta = self.url_open(vieja, allow_redirects=False)
        self.assertEqual(respuesta.status_code, 301)
        self.assertTrue(respuesta.headers['Location'].endswith(self.producto.website_url), respuesta.headers)
        self.assertEqual(self.url_open(vieja).status_code, 200)

    def test_el_mensaje_de_whatsapp_lleva_el_codigo_publico(self):
        enlace = self.website._dcasa_whatsapp_producto(self.producto)
        texto = unquote(enlace.split('text=', 1)[1])
        self.assertEqual(texto, f"Hola D'CASA, me interesa: CAMA DE PRUEBA DEL CÓDIGO (código {self.codigo})")
        self.assertNotIn(REFERENCIA, enlace)
        # También la variante (la ficha puede pasar una u otra).
        self.assertIn(self.codigo, unquote(self.website._dcasa_whatsapp_producto(self.producto.product_variant_id)))
        html = self.url_open(self.producto.website_url).text
        self.assertIn(f'c%C3%B3digo%20{self.codigo}', html, 'el botón de la ficha manda el código público')

    def test_datos_estructurados_para_google(self):
        html = self.url_open(self.producto.website_url).text
        bloques = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        productos = [b for b in bloques if isinstance(b, dict) and b.get('@type') == 'Product']
        productos += [p for b in bloques if isinstance(b, list) for p in b if p.get('@type') == 'Product']
        self.assertTrue(productos)
        self.assertEqual({p.get('sku') for p in productos}, {self.codigo})
        self.assertNotIn(REFERENCIA, json.dumps(bloques))

    def test_fotos_sin_la_referencia_en_su_nombre_ni_en_el_texto_alternativo(self):
        for ruta in (self.producto.website_url, '/shop', '/'):
            html = self.url_open(ruta).text
            self._sin_referencia(html, f'las fotos de {ruta}')
        html = self.url_open('/shop').text
        self.assertRegex(html, r'/web/image/product\.(?:template|product)/\d+/image_\d+/CAMA%20DE%20PRUEBA')

    def test_carrito_y_pedido_sin_la_referencia(self):
        self.authenticate(None, None)
        html = self.url_open(self.producto.website_url).text
        token = re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', html).group(1)
        respuesta = self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token, 'product_template_id': self.producto.id}, allow_redirects=False)
        self.assertTrue(respuesta.headers['Location'].endswith('/shop/cart'))
        for ruta in ('/shop/cart', '/shop/address'):
            pagina = self.url_open(ruta).text
            self.assertIn('CAMA DE PRUEBA DEL CÓDIGO', pagina, ruta)
            self._sin_referencia(pagina, ruta)

    def test_el_mapa_del_sitio_no_lleva_la_referencia(self):
        self.env['ir.attachment'].sudo().search([('type', '=', 'binary'), ('url', '=like', '/sitemap-%.xml')]).unlink()
        mapa = self.url_open('/sitemap.xml').text
        self.assertIn(f'/shop/cama-de-prueba-del-codigo-{self.producto.id}', mapa)
        self.assertNotIn(CLAVE, mapa)

    def test_buscar_el_codigo_en_la_tienda(self):
        html = self.url_open('/shop', params={'search': self.codigo}).text
        self.assertIn(self.producto.website_url, html)
        otro = self.env['product.template'].create({'name': 'MESA QUE NO ES', 'list_price': 10.0, 'is_published': True})
        self.assertNotIn(otro.website_url, html)

    def test_el_qr_abre_la_ficha(self):
        """/codigo/DC-… es la dirección que va dentro del QR de una cotización o etiqueta."""
        for escrito in (self.codigo, self.codigo.lower(), self.codigo.replace('-', '')):
            respuesta = self.url_open(f'/codigo/{escrito}', allow_redirects=False)
            self.assertEqual(respuesta.status_code, 302, escrito)
            self.assertTrue(respuesta.headers['Location'].endswith(self.producto.website_url), respuesta.headers)
        self.assertEqual(self.url_open(f'/codigo/{self.codigo}').status_code, 200)
        self.assertEqual(self.producto._dcasa_url_codigo_publico().rsplit('/codigo/', 1)[-1], self.codigo)

    def test_el_qr_de_algo_que_no_esta_en_la_tienda_lleva_a_la_tienda(self):
        """Sin publicar, regenerado, inventado o raro: la misma respuesta, sin decir cuál es."""
        regenerado = self.codigo
        self.producto.with_user(self.env.ref('base.user_admin')).action_dcasa_regenerar_codigo_publico()
        sin_publicar = self.env['product.template'].create({'name': 'MESA SIN PUBLICAR', 'list_price': 10.0})
        for escrito in (regenerado, sin_publicar.dcasa_codigo_publico, 'DC-BCDFGH', 'DC-ABC', 'x', '<script>', '%25'):
            respuesta = self.url_open(f'/codigo/{escrito}', allow_redirects=False)
            self.assertEqual(respuesta.status_code, 302, escrito)
            self.assertTrue(respuesta.headers['Location'].endswith('/shop'), (escrito, respuesta.headers))
