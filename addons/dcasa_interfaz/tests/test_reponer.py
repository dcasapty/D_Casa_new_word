"""«Reponer» (Compras › Reponer): vendido (facturas menos notas de crédito), existencia, pedido sin llegar, faltaría.

Fechas de 2024 para no mezclarse con las ventas de otras pruebas.
"""
from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_facturado import FacturadoCommon

DESDE, HASTA = date(2024, 5, 1), date(2024, 5, 31)


@tagged('post_install', '-at_install')
class TestReponer(FacturadoCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Socio = cls.env['res.partner']
        cls.prov_a = Socio.create({'name': 'Proveedor Reponer A'})
        cls.prov_b = Socio.create({'name': 'Proveedor Reponer B'})
        Producto = cls.env['product.product']
        cls.sofa = Producto.create({
            'name': 'Sofá reponer', 'default_code': 'REP-SOFA', 'is_storable': True, 'list_price': 400.0,
            'taxes_id': [Command.clear()]})
        cls.mesa = Producto.create({
            'name': 'Mesa reponer', 'default_code': 'REP-MESA', 'is_storable': True, 'list_price': 150.0,
            'taxes_id': [Command.clear()]})
        Precio = cls.env['product.supplierinfo']
        Precio.create({'partner_id': cls.prov_a.id, 'product_tmpl_id': cls.sofa.product_tmpl_id.id, 'price': 200.0})
        Precio.create({'partner_id': cls.prov_b.id, 'product_tmpl_id': cls.sofa.product_tmpl_id.id, 'price': 190.0,
                       'sequence': 99})                          # segundo de la lista: no es el principal
        Precio.create({'partner_id': cls.prov_b.id, 'product_tmpl_id': cls.mesa.product_tmpl_id.id, 'price': 70.0})
        cls.bodega = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id

    def calcular(self, proveedor=None, usuario=None):
        return self.env['dcasa.reponer'].with_user(usuario or self.gerencia)._calcular(DESDE, HASTA, proveedor)

    def fila(self, filas, producto):
        return next(fila for fila in filas if fila['producto_id'] == producto.id)

    def test_una_venta_de_3_y_una_nota_de_1_dan_vendido_2(self):
        factura = self.suelta(date(2024, 5, 10), lineas=[
            Command.create({'product_id': self.sofa.id, 'quantity': 3, 'price_unit': 400.0}),
            Command.create({'product_id': self.flete.id, 'quantity': 1, 'price_unit': 25.0})])   # servicio: fuera
        nota = self.nota(factura, date(2024, 5, 12), precio=400.0)          # devuelve 1 sofá (su primera línea)
        self.assertEqual(nota.invoice_line_ids.product_id, self.sofa)
        self.suelta(date(2024, 6, 1), self.sofa, cantidad=5)                # fuera del periodo
        filas = self.calcular()
        self.assertEqual(self.fila(filas, self.sofa)['vendido'], 2.0)
        self.assertNotIn(self.flete.id, [fila['producto_id'] for fila in filas])
        # Cuadra con «Lo más vendido» del Inicio (las mismas unidades).
        tablero = self.env['dcasa.tablero']
        unidades = tablero._unidades_por_producto(tablero._filas(DESDE, HASTA, 'facturado'))
        self.assertEqual(unidades[self.sofa][0], 2.0)

    def test_la_existencia_y_lo_pedido_sin_llegar_restan(self):
        self.suelta(date(2024, 5, 10), self.sofa, cantidad=10)
        self.suelta(date(2024, 5, 11), self.mesa, cantidad=1)
        self.env['stock.quant']._update_available_quantity(self.sofa, self.bodega, 3)
        self.env['stock.quant']._update_available_quantity(self.mesa, self.bodega, 4)
        Compra = self.env['purchase.order']
        confirmada = Compra.create({'partner_id': self.prov_a.id, 'order_line': [
            Command.create({'product_id': self.sofa.id, 'product_qty': 5, 'price_unit': 200.0})]})
        confirmada.button_confirm()
        Compra.create({'partner_id': self.prov_a.id, 'order_line': [                 # borrador: no cuenta
            Command.create({'product_id': self.sofa.id, 'product_qty': 7, 'price_unit': 200.0})]})
        filas = self.calcular()
        sofa = self.fila(filas, self.sofa)
        self.assertEqual((sofa['vendido'], sofa['existencia'], sofa['pedido'], sofa['faltaria']),
                         (10.0, 3.0, 5.0, 2.0), 'faltaría = 10 − 3 − 5')
        self.assertEqual((sofa['referencia'], sofa['proveedor']), ('REP-SOFA', 'Proveedor Reponer A'))
        mesa = self.fila(filas, self.mesa)
        self.assertEqual((mesa['vendido'], mesa['existencia'], mesa['faltaria']), (1.0, 4.0, 0.0), 'nunca negativo')
        self.assertEqual([fila['producto_id'] for fila in filas][:2], [self.sofa.id, self.mesa.id],
                         'de más vendido a menos')

    def test_filtro_por_proveedor(self):
        self.suelta(date(2024, 5, 10), self.sofa, cantidad=2)
        self.suelta(date(2024, 5, 10), self.mesa, cantidad=1)
        self.assertEqual([fila['producto_id'] for fila in self.calcular(self.prov_a)], [self.sofa.id])
        self.assertEqual([fila['producto_id'] for fila in self.calcular(self.prov_b)], [self.mesa.id],
                         'el sofá también tiene precio de B, pero su principal es A')

    def test_la_pantalla_llena_la_lista(self):
        self.suelta(date(2024, 5, 10), self.sofa, cantidad=2)
        self.suelta(date(2024, 5, 10), self.mesa, cantidad=1)
        asistente = self.env['dcasa.reponer'].with_user(self.gerencia).create(
            {'fecha_desde': DESDE, 'fecha_hasta': HASTA})
        accion = asistente.action_ver()
        lineas = self.env['dcasa.reponer.linea'].with_user(self.gerencia).search(accion['domain'])
        self.assertEqual(accion['res_model'], 'dcasa.reponer.linea')
        self.assertEqual(lineas.mapped('product_id')[:2], self.sofa | self.mesa)
        self.assertEqual(lineas.filtered(lambda linea: linea.product_id == self.sofa).proveedor_id, self.prov_a)
        grupos = self.env['dcasa.reponer.linea'].with_user(self.gerencia)._read_group(
            accion['domain'], ['proveedor_id'], ['vendido:sum'])
        self.assertIn((self.prov_a, 2.0), grupos, 'se agrupa por proveedor')
        # Por defecto, los últimos 30 días.
        nuevo = self.env['dcasa.reponer'].with_user(self.gerencia).create({})
        self.assertEqual((nuevo.fecha_hasta - nuevo.fecha_desde).days, 29)

    def test_la_vendedora_no_tiene_acceso(self):
        menu = self.env.ref('dcasa_interfaz.menu_dcasa_reponer')
        self.assertIn(menu.id, self.env['ir.ui.menu'].with_user(self.gerencia)._visible_menu_ids())
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(self.vendedora)._visible_menu_ids())
        for modelo in ('dcasa.reponer', 'dcasa.reponer.linea'):
            self.assertFalse(self.env[modelo].with_user(self.vendedora).has_access('read'), modelo)
            self.assertTrue(self.env[modelo].with_user(self.gerencia).has_access('create'), modelo)
        with self.assertRaises(AccessError):
            self.calcular(usuario=self.vendedora)
