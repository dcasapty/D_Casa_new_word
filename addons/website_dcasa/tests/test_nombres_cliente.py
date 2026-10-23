"""F5: en la tienda y en el portal el cliente lee los nombres en formato título; por dentro siguen en MAYÚSCULAS.

Decisión de la dueña (2026-10-22): «Lo que ve el cliente: "Cama Queen Tapizada", y solo por dentro queden en
MAYÚSCULAS». Se mira el texto VISIBLE de cada página (sin scripts ni estilos): ahí no puede quedar el nombre guardado.
"""
import json
import re

from lxml import etree
from lxml import html as lxml_html

from odoo.tests import HttpCase, tagged

GUARDADO, CLIENTE = 'CAMA DE METAL CON BAÚL', 'Cama de Metal con Baúl'


def texto_visible(pagina):
    arbol = lxml_html.document_fromstring(pagina)
    for nodo in arbol.xpath('//script|//style|//template'):
        nodo.drop_tree()
    return ' '.join(arbol.find('body').text_content().split())


@tagged('post_install', '-at_install')
class TestNombresParaElClienteEnLaTienda(HttpCase):

    def setUp(self):
        super().setUp()
        self.producto = self.env['product.template'].create({
            'name': GUARDADO, 'list_price': 150.0, 'is_published': True, 'sale_ok': True,
            'website_sequence': -100000, 'default_code': 'PROV-TITULO-1',
        })
        self.variante = self.producto.product_variant_id

    def assertParaElCliente(self, pagina, donde):
        visible = texto_visible(pagina)
        self.assertIn(CLIENTE, visible, donde)
        self.assertNotIn(GUARDADO, visible, f'{donde}: el cliente no lee el nombre en MAYÚSCULAS')

    def test_tienda_ficha_y_busqueda(self):
        for ruta in ('/shop', self.producto.website_url, '/shop?search=metal'):
            self.assertParaElCliente(self.url_open(ruta).text, ruta)
        ficha = self.url_open(self.producto.website_url).text
        self.assertRegex(ficha, rf'<title>\s*{CLIENTE}')
        self.assertRegex(ficha, rf'<meta property="og:title" content="{CLIENTE}"')
        patron = r'<script type="application/ld\+json">(.*?)</script>'
        bloques = [json.loads(b) for b in re.findall(patron, ficha, re.S)]
        planos = [p for b in bloques for p in (b if isinstance(b, list) else [b])]
        nombres = {p.get('name') for p in planos if isinstance(p, dict) and p.get('@type') == 'Product'}
        self.assertEqual(nombres, {CLIENTE}, 'los datos para Google llevan el nombre en formato título')

    def test_buscador_del_sitio(self):
        resultados = self.producto._search_render_results(
            ['id', 'name', 'website_url'], {'name': {'name': 'name', 'type': 'text', 'match': True}}, 'fa-shop', 5)
        self.assertEqual(resultados[0]['name'], CLIENTE)

    def test_carrito_y_pago(self):
        self.authenticate(None, None)
        pagina = self.url_open(self.producto.website_url).text
        token = re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', pagina).group(1)
        self.url_open('/dcasa/carrito/agregar', data={'csrf_token': token, 'product_template_id': self.producto.id})
        for ruta in ('/shop/cart', '/shop/address'):
            self.assertParaElCliente(self.url_open(ruta).text, ruta)

    def test_lineas_del_carrito(self):
        cliente = self.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA'})
        orden = self.env['sale.order'].create({'partner_id': cliente.id, 'order_line': [
            (0, 0, {'product_id': self.variante.id})]})
        linea = orden.order_line
        self.assertEqual(linea.name_short, CLIENTE)
        self.assertEqual(linea._get_line_header(), CLIENTE)
        self.assertIn(GUARDADO, linea.name, 'lo guardado en la línea sigue en MAYÚSCULAS')

    def test_portal_del_pedido(self):
        cliente = self.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA', 'email': 'cliente.titulo@example.com'})
        orden = self.env['sale.order'].create({'partner_id': cliente.id, 'order_line': [
            (0, 0, {'product_id': self.variante.id})]})
        orden.action_quotation_sent()
        self.assertParaElCliente(self.url_open(orden.get_portal_url()).text, 'el portal del pedido')

    def test_fuera_del_sitio_sigue_en_mayusculas(self):
        """Sin una página del sitio (el backend, un informe interno) el t-field pinta el nombre guardado."""
        self.assertEqual(self.producto.with_context(display_default_code=False).display_name, GUARDADO)
        plantilla = etree.fromstring('<t t-name="prueba_nombre"><span t-field="producto.name"/></t>')
        self.assertIn(GUARDADO, str(self.env['ir.qweb']._render(plantilla, {'producto': self.producto})))
