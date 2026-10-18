"""Lo que el sitio dibuja: con todo apagado, nada de Meta; encendido, solo el atributo (el píxel lo carga el navegador
después del consentimiento); el personal con sesión no lleva píxel; la ficha y el carrito traen el id de la
variante. Y el checkout: la casilla y los datos del navegador, solo con consentimiento."""
import json
import os
import re
from unittest.mock import MagicMock, patch

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged

from ..models import meta_api
from .common import PIXEL, TOKEN, entorno, publicar_privacidad

FBP = 'fb.1.1700000000000.1234567890'
UA = 'Mozilla/5.0 (Prueba Meta)'


def galletas(opcionales):
    """Las cookies del navegador: ``_fbp`` y la elección del aviso (``None`` = todavía no eligió)."""
    valores = {'_fbp': FBP}
    if opcionales is not None:
        valores['website_cookies_bar'] = json.dumps({'required': True, 'optional': opcionales},
                                                    separators=(',', ':'))
    return valores


class SitioMetaCase(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        color = cls.env['product.attribute'].create({
            'name': 'Color Meta Prueba', 'create_variant': 'always',
            'value_ids': [Command.create({'name': 'Azul'}), Command.create({'name': 'Gris'})]})
        cls.sofa = cls.env['product.template'].create({
            'name': 'SOFÁ VARIANTES META', 'type': 'consu', 'list_price': 400.0, 'is_published': True,
            'sale_ok': True, 'website_id': False, 'taxes_id': [Command.clear()],
            'attribute_line_ids': [Command.create({'attribute_id': color.id,
                                                   'value_ids': [Command.set(color.value_ids.ids)]})]})
        cls.mesa = cls.env['product.product'].create({
            'name': 'MESA META RENDER', 'type': 'consu', 'list_price': 120.0, 'is_published': True,
            'sale_ok': True, 'taxes_id': [Command.clear()]})
        panama = cls.env.ref('base.pa')
        cls.cliente_partner = cls.env['res.partner'].create({
            'name': 'CLIENTE WEB META', 'email': 'cliente.web.meta@example.com', 'phone': '6000-7777',
            'street': 'Calle de Prueba 1', 'city': 'La Chorrera', 'country_id': panama.id})
        cls.cliente = cls.env['res.users'].create({
            'name': 'CLIENTE WEB META', 'login': 'cliente_web_meta', 'password': 'clave-cliente-meta-123',
            'partner_id': cls.cliente_partner.id, 'group_ids': [Command.set([cls.env.ref('base.group_portal').id])]})
        cls.vendedora = new_test_user(cls.env, login='meta_web_vendedora', password='clave-vendedora-meta-123',
                                      groups='base.group_user,sales_team.group_sale_salesman')

    def setUp(self):
        super().setUp()
        parche = entorno()
        parche.start()
        self.addCleanup(parche.stop)
        os.environ.pop(meta_api.VARIABLE_TOKEN, None)
        self.post = MagicMock(side_effect=AssertionError('requests.post no debe llamarse en esta prueba'))
        parche_post = patch('requests.post', self.post)
        parche_post.start()
        self.addCleanup(parche_post.stop)
        for clave in ('pixel_id', 'pixel_activo', 'capi_web', 'capi_tienda', 'test_event_code'):
            self.ICP.set_param(f'dcasa_meta.{clave}', False)

    def encender_pixel(self):
        publicar_privacidad(self.env)
        self.ICP.set_param('dcasa_meta.pixel_id', PIXEL)
        self.ICP.set_param('dcasa_meta.pixel_activo', 'True')
        self.website.cookies_bar = True

    def encender_ventas_web(self):
        publicar_privacidad(self.env)
        parche = patch.dict(os.environ, {meta_api.VARIABLE_TOKEN: TOKEN})
        parche.start()
        self.addCleanup(parche.stop)
        self.ICP.set_param('dcasa_meta.pixel_id', PIXEL)
        self.ICP.set_param('dcasa_meta.capi_web', 'True')
        self.website.cookies_bar = True

    def variante_mostrada(self):
        combinacion = self.sofa._get_first_possible_combination()
        return self.sofa._get_variant_for_combination(combinacion)

    def carrito_del_cliente(self, producto=None):
        self.authenticate(self.cliente.login, 'clave-cliente-meta-123')
        producto = producto or self.mesa
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': producto.product_tmpl_id.id, 'product_id': producto.id, 'quantity': 2})
        return self.env['sale.order'].search([('partner_id', '=', self.cliente_partner.id),
                                              ('website_id', '=', self.website.id)], order='id desc', limit=1)


@tagged('post_install', '-at_install')
class TestRender(SitioMetaCase):

    def paginas(self):
        """Portada, tienda con búsqueda, ficha, checkout y confirmación (estas dos con el carrito del cliente)."""
        self.authenticate(None, None)
        html = {
            'portada': self.url_open('/').text,
            'tienda': self.url_open('/shop?search=mesa').text,
            'ficha': self.url_open(self.sofa.website_url).text,
        }
        self.carrito_del_cliente()
        html['checkout'] = self.url_open('/shop/checkout').text
        self.assertIn('id="shop_checkout"', html['checkout'], 'El checkout se dibujó (no redirigió)')
        html['confirmacion'] = self.url_open('/shop/confirmation').text
        return html

    def test_con_todo_apagado_ninguna_pagina_lleva_nada_de_meta(self):
        for nombre, html in self.paginas().items():
            with self.subTest(pagina=nombre):
                minusculas = html.lower()
                for prohibido in ('facebook', 'fbq', 'dcasa-meta-pixel', 'dcasa-meta-datos', 'data-dcasa-meta'):
                    self.assertNotIn(prohibido, minusculas)

    def test_encendido_solo_el_atributo_y_nunca_el_script_de_meta(self):
        self.encender_pixel()
        paginas = self.paginas()
        for nombre, html in paginas.items():
            with self.subTest(pagina=nombre):
                self.assertIn(f'data-dcasa-meta-pixel="{PIXEL}"', html)
                self.assertNotIn('connect.facebook.net', html)
                self.assertNotIn('<noscript><img', html)
        variante = self.variante_mostrada()
        self.assertIn(f'data-dcasa-meta-id="{variante.id}"', paginas['ficha'])
        self.assertIn('data-dcasa-meta-valor="400.00"', paginas['ficha'])
        datos = re.search(r'<script type="application/json" id="dcasa-meta-datos">(.*?)</script>', paginas['checkout'])
        self.assertTrue(datos, 'El checkout lleva los datos de InitiateCheckout')
        datos = json.loads(datos.group(1))
        self.assertEqual(datos['evento'], 'InitiateCheckout')
        self.assertEqual(datos['datos']['content_ids'], [str(self.mesa.id)])
        self.assertEqual(datos['datos']['num_items'], 2)
        self.assertEqual(datos['datos']['value'], 240.0)
        self.assertIn('"evento": "AddPaymentInfo"', paginas['confirmacion'])
        self.assertNotIn('Purchase', paginas['confirmacion'])

    def test_fuera_de_produccion_no_hay_pixel(self):
        self.encender_pixel()
        with patch.dict(os.environ, {'DCASA_ENTORNO': 'staging'}):
            html = self.url_open('/').text
        self.assertNotIn('dcasa-meta-pixel', html)
        self.assertIn('Solo las necesarias', html, 'El aviso de cookies sigue')
        # (Odoo sí nombra facebook.com en la lista de dominios que su vigilante bloquea sin consentimiento.)
        self.assertNotIn('Meta (Facebook e Instagram)', ' '.join(html.split()), 'Sin píxel, el aviso no habla de Meta')

    def test_sin_la_seccion_de_privacidad_no_hay_pixel(self):
        self.ICP.set_param('dcasa_meta.pixel_id', PIXEL)
        self.ICP.set_param('dcasa_meta.pixel_activo', 'True')
        self.website.cookies_bar = True
        self.assertNotIn('dcasa-meta-pixel', self.url_open('/').text)

    def test_el_personal_con_sesion_no_lleva_pixel(self):
        self.encender_pixel()
        self.authenticate(self.vendedora.login, 'clave-vendedora-meta-123')
        for ruta in ('/', self.sofa.website_url):
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                self.assertNotIn('dcasa-meta-pixel', html)
                self.assertNotIn('data-dcasa-meta-id', html)

    def test_el_aviso_de_cookies_en_espanol_con_la_politica(self):
        self.encender_pixel()
        html = self.url_open('/').text
        self.assertIn('Solo las necesarias', html)
        self.assertIn('Aceptar', html)
        self.assertIn('Meta (Facebook e Instagram)', ' '.join(html.split()))
        self.assertIn('href="/privacidad#cookies"', html)
        self.assertIn('Preferencias de cookies', html)

    def test_el_carrito_de_odoo_trae_el_id_de_la_variante_sin_tocar_sus_claves(self):
        self.authenticate(None, None)
        apagado = self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.mesa.product_tmpl_id.id, 'product_id': self.mesa.id, 'quantity': 1})
        self.assertNotIn('dcasa_meta_id', apagado['tracking_info'][0])
        self.encender_pixel()
        variante = self.variante_mostrada()
        encendido = self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.sofa.id, 'product_id': variante.id, 'quantity': 1})
        info = encendido['tracking_info'][0]
        self.assertEqual(info['dcasa_meta_id'], str(variante.id))
        self.assertIn('item_id', info, 'Las claves de Odoo siguen ahí')


@tagged('post_install', '-at_install')
class TestCheckout(SitioMetaCase):

    def test_sin_ventas_web_no_hay_casilla_ni_se_toma_nada(self):
        pedido = self.carrito_del_cliente()
        html = self.url_open('/shop/checkout', headers={'User-Agent': UA}, cookies=galletas(True)).text
        self.assertNotIn('dcasa_meta_consentimiento_compra', html)
        self.assertFalse(pedido.sudo().dcasa_meta_ua)

    def test_sin_consentimiento_no_se_toma_el_navegador(self):
        self.encender_ventas_web()
        pedido = self.carrito_del_cliente()
        html = self.url_open('/shop/checkout', headers={'User-Agent': UA}, cookies=galletas(None)).text
        self.assertIn('id="dcasa_meta_consentimiento_compra"', html, 'La casilla aparece')
        self.assertNotIn('checked', re.search(r'<input[^>]*dcasa_meta_consentimiento_compra[^>]*>', html).group(0),
                         'Desmarcada de fábrica')
        pedido.invalidate_recordset()
        self.assertFalse(pedido.sudo().dcasa_meta_ua)
        self.assertFalse(pedido.sudo().dcasa_meta_fbp)

    def test_con_las_cookies_aceptadas_se_toma_el_navegador(self):
        self.encender_ventas_web()
        pedido = self.carrito_del_cliente()
        self.url_open('/shop/checkout', headers={'User-Agent': UA}, cookies=galletas(True))
        pedido.invalidate_recordset()
        navegador = pedido.sudo()._dcasa_meta_navegador()
        self.assertEqual(navegador['fbp'], FBP)
        self.assertEqual(navegador['ua'], UA)
        self.assertTrue(navegador['ip'])
        self.assertTrue(navegador['url'].endswith('/shop/checkout'))

    def test_solo_las_necesarias_no_cuenta_como_consentimiento(self):
        self.encender_ventas_web()
        pedido = self.carrito_del_cliente()
        self.url_open('/shop/checkout', headers={'User-Agent': UA}, cookies=galletas(False))
        pedido.invalidate_recordset()
        self.assertFalse(pedido.sudo()._dcasa_meta_navegador())

    def test_la_casilla_del_checkout_marca_la_compra_y_la_ficha_de_quien_compra(self):
        self.encender_ventas_web()
        pedido = self.carrito_del_cliente()
        respuesta = self.make_jsonrpc_request('/dcasa/meta/consentimiento-compra', {'acepta': True},
                                              headers={'User-Agent': UA})
        self.assertEqual(respuesta, {'ok': True, 'ficha': True})
        pedido.invalidate_recordset()
        self.cliente_partner.invalidate_recordset()
        self.assertTrue(pedido.sudo().dcasa_meta_consentimiento_compra)
        self.assertEqual(self.cliente_partner.dcasa_meta_consentimiento_origen, 'web')
        self.assertTrue(pedido.sudo()._dcasa_meta_navegador()['url'].endswith('/shop/checkout'),
                        'La página es la del checkout, no la ruta de la casilla')
        # Desmarcarla quita el de la compra, el de la ficha (lo dio aquí) y el navegador (no aceptó las cookies).
        respuesta = self.make_jsonrpc_request('/dcasa/meta/consentimiento-compra', {'acepta': False})
        self.assertTrue(respuesta['ok'])
        pedido.invalidate_recordset()
        self.cliente_partner.invalidate_recordset()
        self.assertFalse(pedido.sudo().dcasa_meta_consentimiento_compra)
        self.assertFalse(self.cliente_partner.dcasa_meta_consentimiento_fecha)
        self.assertFalse(pedido.sudo()._dcasa_meta_navegador())

    def test_sin_ventas_web_la_casilla_no_hace_nada(self):
        pedido = self.carrito_del_cliente()
        respuesta = self.make_jsonrpc_request('/dcasa/meta/consentimiento-compra', {'acepta': True})
        self.assertEqual(respuesta, {'ok': False})
        pedido.invalidate_recordset()
        self.assertFalse(pedido.sudo().dcasa_meta_consentimiento_compra)

    def test_un_visitante_no_marca_la_ficha_de_otra_persona(self):
        """Sin sesión, la casilla solo vale para la ficha nueva de este carrito, nunca para una que ya existía."""
        self.encender_ventas_web()
        self.authenticate(None, None)
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.mesa.product_tmpl_id.id, 'product_id': self.mesa.id, 'quantity': 1})
        pedido = self.env['sale.order'].search([('website_id', '=', self.website.id)], order='id desc', limit=1)
        pedido.sudo().partner_id = self.cliente_partner  # una ficha vieja colgada del carrito
        respuesta = self.make_jsonrpc_request('/dcasa/meta/consentimiento-compra', {'acepta': True})
        self.assertEqual(respuesta, {'ok': True, 'ficha': False})
        self.cliente_partner.invalidate_recordset()
        self.assertFalse(self.cliente_partner.dcasa_meta_consentimiento_fecha)
