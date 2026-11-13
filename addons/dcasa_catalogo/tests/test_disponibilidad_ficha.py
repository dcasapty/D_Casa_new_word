"""Ficha de la tienda: «Disponible», «Quedan pocas» o «Agotado» con la regla de Juan (nunca el número).

Pedido de la dueña (lote 1 de la web, 2026-11-13): la ficha no decía si había producto. La etiqueta sale de
``product.template._dcasa_disponibilidad`` (models/product.py), la misma que usa Juan, y la regla vive en
``dcasa_base/disponibilidad.py``. Lo que deja comprar o no comprar no cambia.
"""
import re

from odoo import Command
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestDisponibilidadEnLaFicha(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Plantilla = cls.env['product.template']
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'is_published': True,
                'allow_out_of_stock_order': True, 'list_price': 199.99}
        cls.muchas = Plantilla.create({**base, 'name': 'ZZMESA DISPONIBLE DE PRUEBA'})
        cls.pocas = Plantilla.create({**base, 'name': 'ZZMESA CON POCAS DE PRUEBA'})
        cls.agotada = Plantilla.create({**base, 'name': 'ZZMESA AGOTADA DE PRUEBA'})
        cls.sin_control = Plantilla.create({**base, 'name': 'ZZMESA SIN INVENTARIO', 'is_storable': False})
        tamano = cls.env['product.attribute'].create({
            'name': 'Zztamaño ficha', 'create_variant': 'always',
            'value_ids': [Command.create({'name': 'Zzqueen'}), Command.create({'name': 'Zzking'})]})
        cls.colchon = Plantilla.create({
            **base, 'name': 'ZZCOLCHÓN CON TAMAÑOS DE PRUEBA',
            'attribute_line_ids': [Command.create({'attribute_id': tamano.id,
                                                   'value_ids': [Command.set(tamano.value_ids.ids)]})]})
        cls.queen = cls.colchon.product_variant_ids.filtered(lambda v: 'Zzqueen' in v.display_name)
        cls.king = cls.colchon.product_variant_ids.filtered(lambda v: 'Zzking' in v.display_name)

        bodega = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.ubicacion = bodega.lot_stock_id
        cls.Quant = cls.env['stock.quant']
        for variante, cantidad in ((cls.muchas.product_variant_id, 12), (cls.pocas.product_variant_id, 3),
                                   (cls.queen, 20), (cls.king, 2)):
            cls.Quant._update_available_quantity(variante, cls.ubicacion, cantidad)

    def _etiqueta(self, plantilla):
        html = self.url_open(plantilla.website_url).text
        hallada = re.search(r'<p[^>]*class="o_dcasa_disponibilidad"[^>]*>.*?</p>', html, re.S)
        self.assertTrue(hallada, f'La ficha de {plantilla.name} no trae la etiqueta de disponibilidad')
        return hallada.group(0)

    def test_tres_etiquetas_y_nunca_el_numero(self):
        for plantilla, estado, texto in ((self.muchas, 'disponible', 'Disponible'),
                                         (self.pocas, 'pocas', 'Quedan pocas'),
                                         (self.agotada, 'agotado', 'Agotado'),
                                         (self.sin_control, 'disponible', 'Disponible')):
            with self.subTest(producto=plantilla.name):
                etiqueta = self._etiqueta(plantilla)
                self.assertIn(f'data-estado="{estado}"', etiqueta)
                self.assertIn(f'>{texto}</span>', etiqueta)
                self.assertNotRegex(re.sub(r'<[^>]+>', '', etiqueta), r'\d', 'Nunca el número de existencias')

    def test_lo_reservado_no_cuenta(self):
        """Lo libre es lo que hay menos lo reservado (como Juan): 9 con 6 apartadas son «pocas»."""
        mesa = self.env['product.template'].create({
            'name': 'ZZMESA RESERVADA DE PRUEBA', 'type': 'consu', 'is_storable': True, 'is_published': True,
            'list_price': 99.99})
        self.Quant._update_available_quantity(mesa.product_variant_id, self.ubicacion, 9)
        self.assertEqual(mesa._dcasa_disponibilidad(), 'disponible')
        self.Quant._update_reserved_quantity(mesa.product_variant_id, self.ubicacion, 6)
        self.env.invalidate_all()   # en la tienda cada visita es una petición nueva
        self.assertEqual(mesa._dcasa_disponibilidad(), 'pocas')

    def test_cada_medida_dice_la_suya(self):
        """La ficha dice la de la medida elegida y la repinta al cambiar (la información que pide el JavaScript)."""
        self.assertEqual(self.colchon._dcasa_disponibilidad(), 'disponible', 'sin medida: todas juntas (22)')
        self.assertEqual(self.colchon._dcasa_disponibilidad(self.queen), 'disponible')
        self.assertEqual(self.colchon._dcasa_disponibilidad(self.king), 'pocas')
        for variante, estado, texto in ((self.queen, 'disponible', 'Disponible'), (self.king, 'pocas', 'Quedan pocas')):
            with self.subTest(medida=variante.display_name):
                info = self.make_jsonrpc_request('/website_sale/get_combination_info', {
                    'product_template_id': self.colchon.id,
                    'product_id': variante.id,
                    'combination': variante.product_template_attribute_value_ids.ids,
                    'add_qty': 1,
                })
                self.assertEqual(info['dcasa_disponibilidad'], estado)
                self.assertEqual(info['dcasa_disponibilidad_texto'], texto)

    def test_un_cambio_de_existencias_cambia_la_ficha(self):
        self.assertIn('data-estado="agotado"', self._etiqueta(self.agotada))
        self.Quant._update_available_quantity(self.agotada.product_variant_id, self.ubicacion, 4)
        self.assertIn('data-estado="pocas"', self._etiqueta(self.agotada))

    def test_agotado_se_sigue_pudiendo_comprar(self):
        """La etiqueta solo informa: lo que deja comprar es lo de siempre (``allow_out_of_stock_order``)."""
        html = self.url_open(self.agotada.website_url).text
        self.assertIn('id="add_to_cart"', html)
        self.assertTrue(self.agotada.product_variant_id._is_add_to_cart_allowed())
