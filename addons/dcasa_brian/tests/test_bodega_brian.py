"""Brian «entregas_por_despachar»: las mismas entregas del panel de Bodega (dcasa_barras), sin precios."""
import unittest

from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestBrianEntregasPorDespachar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'dcasa.bodega' not in cls.env:
            raise unittest.SkipTest('Sin dcasa_barras (el panel de Bodega) no hay herramienta que probar')
        cls.bodega = new_test_user(cls.env, login='brian_bodega', groups='stock.group_stock_user')
        cls.sin_inventario = new_test_user(cls.env, login='brian_sin_bodega', groups='base.group_user')
        bodega = cls.env.ref('stock.warehouse0').lot_stock_id
        cls.cama = cls.env['product.product'].create({
            'name': 'Zzcama Brian bodega', 'default_code': 'ZZB-CAMA', 'is_storable': True, 'list_price': 321.0})
        cls.env['stock.quant']._update_available_quantity(cls.cama, bodega, 5)
        cliente = cls.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA BRIAN BODEGA'})
        cls.pedido = cls.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [Command.create({'product_id': cls.cama.id, 'product_uom_qty': 2, 'price_unit': 321.0})]})
        cls.pedido.action_confirm()
        cls.entrega = cls.pedido.picking_ids
        # Con un abono (el panel solo muestra pedidos con pago o abono: decisión de la dueña, 2026-10-22).
        factura = cls.pedido._create_invoices()
        factura.action_post()
        cls.env['account.payment.register'].with_context(active_model='account.move', active_ids=factura.ids).create(
            {'amount': factura.currency_id.round(factura.amount_total * 0.6)})._create_payments()
        sin_pago = cls.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [Command.create({'product_id': cls.cama.id, 'product_uom_qty': 1, 'price_unit': 321.0})]})
        sin_pago.action_confirm()
        cls.entrega_sin_pago = sin_pago.picking_ids

    def ejecutar(self, usuario, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar('entregas_por_despachar', argumentos or {})

    def test_dice_cuantas_faltan_y_cuales_sin_precios(self):
        respuesta = self.ejecutar(self.bodega)
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        panel = self.env['dcasa.bodega'].with_user(self.bodega).pendientes()
        self.assertEqual(datos['total_pendientes'], panel['cuantas'])
        fila = next(f for f in datos['entregas'] if f['entrega'] == self.entrega.name)
        self.assertEqual((fila['cliente'], fila['pedido'], fila['estado'], fila['como']),
                         ('CLIENTE DE PRUEBA BRIAN BODEGA', self.pedido.name, 'Lista para salir',
                          'Sin definir: envío o retiro'))
        self.assertEqual(fila['productos'], '2 × Zzcama Brian bodega')
        self.assertEqual(fila['pago'], 'Con abono: le falta una parte por pagar')
        self.assertNotIn(self.entrega_sin_pago.name, [f['entrega'] for f in datos['entregas']], 'sin pago no sale')
        self.assertIn('pago o abono', datos['regla'])
        self.assertEqual(datos['abrir']['url'], '/odoo/bodega')
        self.assertNotIn('321', str(datos), 'nunca precios')
        self.assertGreaterEqual(datos['por_tipo']['sin_definir'], 1)
        self.assertGreaterEqual(datos['listas_para_salir'], 1)

    def test_filtra_por_envio_retiro_y_estado(self):
        retiro = self.ejecutar(self.bodega, {'como': 'retiro'})['datos']
        self.assertNotIn(self.entrega.name, [f['entrega'] for f in retiro['entregas']])
        listas = self.ejecutar(self.bodega, {'estado': 'listas', 'limite': '50'})['datos']
        self.assertIn(self.entrega.name, [f['entrega'] for f in listas['entregas']])
        self.assertLessEqual(len(listas['entregas']), 30)
        self.assertFalse(self.ejecutar(self.bodega, {'como': 'avion'})['ok'])

    def test_quien_no_trabaja_con_inventario_no_la_tiene(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.sin_inventario).catalogo()}
        self.assertNotIn('entregas_por_despachar', nombres)
        self.assertFalse(self.ejecutar(self.sin_inventario)['ok'])
        self.assertEqual(self.env['brian.herramientas']._todas()['entregas_por_despachar']['nivel'], 'lectura')
