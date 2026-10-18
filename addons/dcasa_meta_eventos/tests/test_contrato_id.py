"""Contrato 2.1 del diseño de Meta: el `id` del catálogo (dcasa_meta_catalogo) es el mismo número que los
`content_ids` que dibuja la ficha para el píxel y que arma el Purchase del servidor. Los dos módulos no dependen uno
del otro: esta prueba solo corre cuando están los dos (la unión de los paquetes)."""
import base64
import csv
import io
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from odoo import Command, fields
from odoo.tests import HttpCase, tagged

from ..models import meta_api
from .common import PIXEL, entorno, publicar_privacidad

BASE = 'https://tienda.example'


def foto():
    """Una foto lisa de 600×600 (el catálogo deja fuera los productos sin foto)."""
    salida = io.BytesIO()
    Image.new('RGB', (600, 600), (19, 64, 177)).save(salida, format='PNG')
    return base64.b64encode(salida.getvalue())


@tagged('post_install', '-at_install')
class TestContratoId(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        instalado = cls.env['ir.module.module'].search_count(
            [('name', '=', 'dcasa_meta_catalogo'), ('state', '=', 'installed')])
        if not instalado:
            raise unittest.SkipTest('dcasa_meta_catalogo no está instalado: el contrato se prueba en la unión')
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.website = cls.env.ref('website.default_website')
        color = cls.env['product.attribute'].create({
            'name': 'Color Contrato Meta', 'create_variant': 'always',
            'value_ids': [Command.create({'name': 'Rojo'}), Command.create({'name': 'Negro'})]})
        cls.sofa = cls.env['product.template'].create({
            'name': 'SOFÁ CONTRATO META', 'type': 'consu', 'list_price': 250.0, 'is_published': True,
            'sale_ok': True, 'website_id': False, 'taxes_id': [Command.clear()],
            'image_1920': foto(),
            'attribute_line_ids': [Command.create({'attribute_id': color.id,
                                                   'value_ids': [Command.set(color.value_ids.ids)]})]})
        cls.cliente = cls.env['res.partner'].create({
            'name': 'CLIENTE CONTRATO META', 'email': 'contrato.meta@example.com', 'phone': '6000-3131'})

    def setUp(self):
        super().setUp()
        parche = entorno(**{meta_api.VARIABLE_TOKEN: 'EAAprueba-contrato'})
        parche.start()
        self.addCleanup(parche.stop)
        parche_post = patch('requests.post', MagicMock(side_effect=AssertionError('nada sale a Meta')))
        parche_post.start()
        self.addCleanup(parche_post.stop)
        self.ICP.set_param('web.base.url', BASE)
        self.ICP.set_param('web.base.url.freeze', 'True')
        publicar_privacidad(self.env)
        self.ICP.set_param('dcasa_meta.pixel_id', PIXEL)
        self.ICP.set_param('dcasa_meta.pixel_activo', 'True')
        self.ICP.set_param('dcasa_meta.capi_tienda', 'True')
        self.website.cookies_bar = True

    def ids_del_catalogo(self):
        feed = self.env['product.feed'].sudo().search([('target', '=', 'meta')], limit=1)
        self.assertTrue(feed, 'dcasa_meta_catalogo trae su feed «Catálogo para Meta»')
        self.assertFalse(feed.dcasa_activo, 'El catálogo viene apagado de fábrica')
        feed.dcasa_activo = True  # lo que haría Gerencia al pegar la dirección en Meta
        respuesta = self.url_open(f'/dcasa/meta/catalogo.csv?feed={feed.id}&token={feed.access_token}')
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:300])
        return {fila['id'] for fila in csv.DictReader(io.StringIO(respuesta.text))}

    def test_catalogo_ficha_y_compra_usan_el_mismo_id(self):
        variantes = self.sofa.product_variant_ids
        catalogo = self.ids_del_catalogo()
        for variante in variantes:
            self.assertIn(str(variante.id), catalogo)
        # Ficha: el id que lleva el píxel para la variante que se muestra.
        combinacion = self.sofa._get_first_possible_combination()
        mostrada = self.sofa._get_variant_for_combination(combinacion)
        self.assertIn(f'data-dcasa-meta-id="{mostrada.id}"', self.url_open(self.sofa.website_url).text)
        self.assertIn(str(mostrada.id), catalogo)
        # Purchase del servidor con las dos variantes.
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': v.id, 'quantity': 1, 'price_unit': 250.0,
                                                 'tax_ids': [Command.clear()]}) for v in variantes]})
        datos = factura._dcasa_meta_custom_data()
        self.assertEqual(set(datos['content_ids']), {str(v.id) for v in variantes})
        self.assertTrue(set(datos['content_ids']) <= catalogo)
        self.assertEqual(datos['content_type'], 'product')
