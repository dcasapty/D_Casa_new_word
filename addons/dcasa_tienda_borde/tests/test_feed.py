import os
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

TOKEN = 'x' * 40


@tagged('post_install', '-at_install')
class TestFeedTienda(HttpCase):
    """El feed del catálogo: con secreto, solo lo publicado, y con las mismas URL y precios que Odoo."""

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        Product = self.env['product.template']
        self.categoria = self.env['product.public.category'].create({'name': 'Mesas feed prueba'})
        self.mesa = Product.create({
            'name': 'Mesa feed prueba', 'list_price': 39.99, 'is_published': True,
            'public_categ_ids': [(6, 0, self.categoria.ids)], 'website_sequence': -500,
            'description_sale': 'Mesa de comedor de madera.',
        })
        self.sin_impuesto = Product.create({
            'name': 'Servicio feed prueba', 'list_price': 15.0, 'is_published': True,
            'taxes_id': [(5, 0, 0)],
        })
        self.oculto = Product.create({'name': 'Borrador feed prueba', 'list_price': 10, 'is_published': False})
        talla = self.env['product.attribute'].create({
            'name': 'Tamaño feed', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Twin'}), (0, 0, {'name': 'Queen'})],
        })
        self.cama = Product.create({
            'name': 'Cama feed prueba', 'list_price': 100, 'is_published': True,
            'attribute_line_ids': [(0, 0, {'attribute_id': talla.id, 'value_ids': [(6, 0, talla.value_ids.ids)]})],
        })
        queen = self.cama.attribute_line_ids.product_template_value_ids.filtered(lambda v: v.name == 'Queen')
        queen.price_extra = 50

    def _feed(self, token=TOKEN, configurado=TOKEN):
        entorno = {'TIENDA_FEED_TOKEN': configurado} if configurado else {}
        with patch.dict(os.environ, entorno):
            if not configurado:
                os.environ.pop('TIENDA_FEED_TOKEN', None)
            headers = {'X-Dcasa-Tienda-Token': token} if token else {}
            return self.url_open('/dcasa/tienda/feed', headers=headers)

    def _producto(self, datos, plantilla):
        return next((p for p in datos['productos'] if p['id'] == plantilla.id), None)

    def test_sin_secreto_no_existe(self):
        self.assertEqual(self._feed(token=None).status_code, 404)
        self.assertEqual(self._feed(token='otro' * 10).status_code, 404)
        self.assertEqual(self._feed(token=TOKEN, configurado='').status_code, 404,
                         'Sin TIENDA_FEED_TOKEN no hay feed')
        self.assertEqual(self._feed(token='corto', configurado='corto').status_code, 404,
                         'Token corto = no configurado')

    def test_solo_publicados_con_url_de_odoo(self):
        respuesta = self._feed()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        datos = respuesta.json()
        ids = {p['id'] for p in datos['productos']}
        self.assertIn(self.mesa.id, ids)
        self.assertNotIn(self.oculto.id, ids)
        mesa = self._producto(datos, self.mesa)
        self.assertEqual(mesa['url'], self.mesa.website_url)
        self.assertTrue(mesa['url'].startswith('/shop/') and mesa['url'].endswith(f'-{self.mesa.id}'))
        categoria = next(c for c in datos['categorias'] if c['id'] == self.categoria.id)
        self.assertEqual(categoria['url'], f"/shop/category/{self.env['ir.http']._slug(self.categoria)}")
        self.assertEqual(mesa['categorias'], self.categoria.ids)
        # La URL de Odoo responde con esa misma ficha.
        self.assertEqual(self.url_open(mesa['url']).status_code, 200)

    def test_precio_sin_itbms_y_leyenda(self):
        datos = self._feed().json()
        mesa = self._producto(datos, self.mesa)
        self.assertEqual(mesa['precio'], 39.99)
        self.assertTrue(mesa['precio_visible'])
        self.assertTrue(mesa['mas_itbms'])
        self.assertEqual(mesa['moneda'], 'USD')
        self.assertFalse(self._producto(datos, self.sin_impuesto)['mas_itbms'])
        self.assertEqual(mesa['compra'], 'directa')

    def test_json_ld_como_la_ficha_de_odoo(self):
        mesa = self._producto(self._feed().json(), self.mesa)
        tipos = [d['@type'] for d in mesa['json_ld']]
        self.assertEqual(tipos, ['Product', 'BreadcrumbList'])
        producto = mesa['json_ld'][0]
        self.assertEqual(producto['offers']['price'], 39.99)
        self.assertNotIn('availability', producto['offers'], 'Existencias sin confirmar: no se publican')
        self.assertEqual(producto['url'].rsplit('/shop/', 1)[1], self.mesa.website_url.rsplit('/shop/', 1)[1])
        self.assertEqual(mesa['json_ld'][1]['itemListElement'][0]['name'], 'Todos los productos')
        self.assertIsNone(mesa['disponible'])
        self.assertIsNone(mesa['existencias'])

    def test_variantes_con_su_precio(self):
        cama = self._producto(self._feed().json(), self.cama)
        self.assertEqual(cama['compra'], 'variantes')
        precios = sorted(v['precio'] for v in cama['variantes'])
        self.assertEqual(precios, [100, 150])
        self.assertEqual({v['id'] for v in cama['variantes']}, set(self.cama.product_variant_ids.ids))

    def test_disponibilidad_si_se_publica(self):
        mesa_almacenable = self.env['product.template'].create({
            'name': 'Mesa con stock feed', 'list_price': 20, 'is_published': True, 'is_storable': True,
            'allow_out_of_stock_order': False,
        })
        with patch('odoo.addons.website_dcasa.controllers.main.PUBLICAR_DISPONIBILIDAD', True):
            datos = self._feed().json()
        mesa = self._producto(datos, mesa_almacenable)
        self.assertTrue(datos['sitio']['publicar_disponibilidad'])
        self.assertEqual(mesa['existencias'], 0)
        self.assertFalse(mesa['disponible'])

    def test_sitio_paginas_y_socios(self):
        datos = self._feed().json()
        self.assertEqual(datos['version'], 1)
        self.assertIn('wa.me/', datos['sitio']['whatsapp'])
        self.assertEqual(datos['sitio']['json_ld_tienda']['@type'], 'FurnitureStore')
        self.assertIn('/privacidad', datos['paginas'])
        self.assertIn('Ley 81 de 2019', datos['paginas']['/privacidad']['html'])
        self.assertIn('no incluyen el ITBMS', datos['paginas']['/terminos']['html'])
        self.assertIn('puntos_al_padrino', datos['socios'])
        self.assertTrue(datos['portada']['categorias'])
