"""Cambiar el precio desde «Contar» del Escáner (pedido de la dueña, 2026-10-16): Gerencia (la misma regla de precios de
Productos), con el precio que se vio, sin variantes y anotado en el producto."""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .comun import BarrasCommon


@tagged('post_install', '-at_install')
class TestPrecioDesdeElEscaner(BarrasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia_ventas = new_test_user(
            cls.env, login='barras_gerencia_ventas', groups='stock.group_stock_user,product.group_product_manager')
        cls.jefe_de_ventas = new_test_user(
            cls.env, login='barras_jefe_ventas', groups='stock.group_stock_user,sales_team.group_sale_manager')

    def cambiar(self, producto, precio, esperado=None, usuario=None):
        esperado = producto.lst_price if esperado is None else esperado
        return self.como(usuario or self.gerencia_ventas).cambiar_precio(producto.id, precio, esperado)

    def test_gerencia_de_ventas_cambia_el_precio_y_queda_anotado(self):
        r = self.cambiar(self.cama, 399.5)
        self.assertEqual((r['cambio'], r['antes'], r['despues']), (True, 349.99, 399.5))
        self.assertEqual(self.cama.list_price, 399.5)
        self.assertEqual(r['ficha']['precio_texto'], '$399.50 + ITBMS')
        nota = self.cama.product_tmpl_id.message_ids[:1]
        self.assertIn('Precio cambiado desde el Escáner', nota.body)
        self.assertIn('$349.99', nota.body)
        self.assertIn('$399.50', nota.body)

    def test_el_mismo_precio_no_cambia_nada(self):
        mensajes = len(self.cama.product_tmpl_id.message_ids)
        r = self.cambiar(self.cama, 349.99)
        self.assertFalse(r['cambio'])
        self.assertEqual(len(self.cama.product_tmpl_id.message_ids), mensajes)

    def test_si_el_precio_cambio_mientras_tanto_no_se_guarda(self):
        with self.assertUserError('Mientras lo revisabas'):
            self.cambiar(self.cama, 399.5, esperado=300.0)
        self.assertEqual(self.cama.list_price, 349.99)

    def test_solo_gerencia(self):
        # La misma regla que en Productos: quien administra Productos. Ni la vendedora, ni quien solo cuenta
        # inventario, ni un jefe de ventas sin Productos.
        for usuario in (self.vendedora, self.solo_inventario, self.jefe_de_ventas):
            with self.subTest(usuario=usuario.login):
                self.assertFalse(self.como(usuario).ficha(self.cama.id)['puede_cambiar_precio'])
                with self.assertRaises(AccessError):
                    self.cambiar(self.cama, 1.0, usuario=usuario)
        for usuario in (self.gerencia_ventas, self.gerencia):
            self.assertTrue(self.como(usuario).ficha(self.cama.id)['puede_cambiar_precio'])
        self.assertEqual(self.cama.list_price, 349.99)

    def test_un_producto_con_variantes_se_cambia_en_productos(self):
        talla = self.env['product.attribute'].create({'name': 'Zztamaño escáner', 'value_ids': [
            Command.create({'name': 'Queen'}), Command.create({'name': 'King'})]})
        plantilla = self.env['product.template'].create({
            'name': 'Zzcama con tamaños', 'list_price': 500.0, 'is_storable': True,
            'attribute_line_ids': [Command.create({
                'attribute_id': talla.id, 'value_ids': [Command.set(talla.value_ids.ids)]})]})
        queen = plantilla.product_variant_ids[0]
        self.assertTrue(self.como(self.gerencia_ventas).ficha(queen.id)['precio_con_variantes'])
        with self.assertUserError('tiene variantes'):
            self.cambiar(queen, 450.0)
        self.assertEqual(plantilla.list_price, 500.0)

    def test_precios_mal_escritos(self):
        for malo in (-1, 1_000_001, True, '399', None, float('nan')):
            with self.subTest(precio=malo), self.assertUserError():
                self.cambiar(self.cama, malo)
        self.assertEqual(self.cama.list_price, 349.99)
