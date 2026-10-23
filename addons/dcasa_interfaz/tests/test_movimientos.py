"""«Movimientos» (Inventario › Movimientos): la historia de un producto en palabras (pedido de la dueña, 2026-10-22).

Una mesa entra por una compra, se ajusta en el conteo, sale por una venta, el cliente la devuelve y se traslada a la
bodega. Cada movimiento dice qué fue, con su signo, quién, cuándo, el documento que lo originó y lo que quedó después.
"""
from datetime import date, datetime, time

import pytz

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from .test_inicio_por_rol import crear_usuario

PANAMA = pytz.timezone('America/Panama')


def en_utc(dia, hora=time(10, 0)):
    return PANAMA.localize(datetime.combine(dia, hora)).astimezone(pytz.utc).replace(tzinfo=None)


class MovimientosCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = crear_usuario(cls.env, 'gerencia_mov', 'dcasa_base.group_gerencia')
        cls.vendedora = crear_usuario(cls.env, 'vendedora_mov', 'dcasa_base.group_vendedora')
        cls.almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.tienda = cls.almacen.lot_stock_id
        cls.bodega = cls.env['stock.location'].create({
            'name': 'Bodega de prueba', 'usage': 'internal', 'location_id': cls.tienda.id})
        cls.proveedor = cls.env['res.partner'].create({'name': 'PROVEEDOR DE PRUEBA'})
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA'})
        cls.mesa = cls.env['product.product'].create({
            'name': 'Mesa de prueba movimientos', 'default_code': 'MOV-MESA-01', 'barcode': '7700000000017',
            'is_storable': True, 'list_price': 300.0, 'standard_price': 150.0, 'taxes_id': [Command.clear()],
            'supplier_taxes_id': [Command.clear()]})
        cls.Mov = cls.env['dcasa.movimientos'].with_user(cls.gerencia)

    def fechar(self, movimientos, dia, hora=time(10, 0)):
        """Pone la fecha del movimiento (y de sus líneas) como si se hubiera hecho ese día a esa hora, sin tocar quién
        lo hizo (``write_uid``)."""
        momento = en_utc(dia, hora)
        self.env.flush_all()
        for registros in (movimientos, movimientos.move_line_ids):
            self.env.cr.execute(f'UPDATE {registros._table} SET date = %s WHERE id IN %s',
                                (momento, tuple(registros.ids)))
            registros.invalidate_recordset(['date'])

    def validar(self, operacion, cantidad, usuario=None):
        for movimiento in operacion.move_ids:
            movimiento.quantity = cantidad
            movimiento.picked = True
        (operacion.with_user(usuario) if usuario else operacion).button_validate()
        self.assertEqual(operacion.state, 'done')
        return operacion

    def historia(self):
        """Compra (+5) el 1, ajuste (+2) el 2, venta (−1) el 3, devolución (+1) el 4 y traslado (2) el 5 de marzo."""
        compra = self.env['purchase.order'].create({
            'partner_id': self.proveedor.id,
            'order_line': [Command.create({'product_id': self.mesa.id, 'product_qty': 5, 'price_unit': 150.0})]})
        compra.button_confirm()
        recepcion = self.validar(compra.picking_ids, 5)
        self.fechar(recepcion.move_ids, date(2025, 3, 1))

        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.mesa.id, 'location_id': self.tienda.id, 'inventory_quantity': 7,
        }).action_apply_inventory()
        ajuste = self.env['stock.move'].search([('product_id', '=', self.mesa.id), ('is_inventory', '=', True)])
        self.fechar(ajuste, date(2025, 3, 2))

        venta = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.mesa.id, 'product_uom_qty': 1})]})
        venta.action_confirm()
        entrega = self.validar(venta.picking_ids, 1, usuario=self.gerencia)
        self.fechar(entrega.move_ids, date(2025, 3, 3))

        asistente = self.env['stock.return.picking'].with_context(
            active_ids=entrega.ids, active_id=entrega.id, active_model='stock.picking').create({})
        asistente.product_return_moves.quantity = 1
        devolucion = self.env['stock.picking'].browse(asistente.action_create_returns()['res_id'])
        self.validar(devolucion, 1)
        self.fechar(devolucion.move_ids, date(2025, 3, 4))

        traslado = self.env['stock.move'].create({
            'product_id': self.mesa.id, 'product_uom_qty': 2, 'product_uom': self.mesa.uom_id.id,
            'location_id': self.tienda.id, 'location_dest_id': self.bodega.id})
        traslado._action_confirm()
        traslado._action_assign()
        traslado.quantity = 2
        traslado.picked = True
        traslado._action_done()
        self.fechar(traslado, date(2025, 3, 5))
        return {'compra': compra, 'recepcion': recepcion, 'ajuste': ajuste, 'venta': venta, 'entrega': entrega,
                'devolucion': devolucion, 'traslado': traslado}


@tagged('post_install', '-at_install')
class TestMovimientos(MovimientosCommon):

    def test_la_historia_de_un_producto_en_palabras(self):
        h = self.historia()
        datos = self.Mov.movimientos(producto_id=self.mesa.id)
        self.assertEqual(datos['existencia'], 7.0)
        self.assertTrue(datos['cuadra'])
        self.assertEqual(datos['total'], 5)
        filas = datos['filas']
        self.assertEqual([f['tipo'] for f in filas], ['traslado', 'devolucion', 'venta', 'ajuste', 'compra'],
                         'lo más nuevo arriba')
        traslado, devolucion, venta, ajuste, compra = filas
        self.assertEqual(compra['texto'], f'Entró por la compra {h["compra"].name} de PROVEEDOR DE PRUEBA')
        self.assertEqual((compra['cantidad_texto'], compra['sentido'], compra['queda']), ('+5', 'entra', 5.0))
        self.assertEqual(compra['documento'], {'modelo': 'purchase.order', 'id': h['compra'].id,
                                               'nombre': h['compra'].name})
        self.assertEqual(compra['operacion'], h['recepcion'].name)
        self.assertEqual(ajuste['texto'], 'Ajuste de inventario (+2)')
        self.assertEqual((ajuste['cantidad_texto'], ajuste['queda']), ('+2', 7.0))
        self.assertIsNone(ajuste['documento'])
        self.assertEqual(venta['texto'], f'Salió por la venta {h["venta"].name} a CLIENTE DE PRUEBA')
        self.assertEqual((venta['cantidad_texto'], venta['sentido'], venta['queda']), ('−1', 'sale', 6.0))
        self.assertEqual(venta['documento']['modelo'], 'sale.order')
        self.assertEqual(venta['quien'], self.gerencia.name, 'quién validó la entrega')
        self.assertEqual(venta['cuando'], '3 mar 2025, 10:00 a. m.', 'en hora de Panamá')
        self.assertEqual(devolucion['texto'], f'Devolución del cliente CLIENTE DE PRUEBA (de {h["venta"].name})')
        self.assertEqual((devolucion['cantidad_texto'], devolucion['queda']), ('+1', 7.0))
        self.assertEqual(traslado['texto'], f'Traslado de {self.almacen.name} a Bodega de prueba')
        self.assertEqual((traslado['cantidad_texto'], traslado['sentido'], traslado['queda']), ('2', 'mueve', 7.0),
                         'un traslado no cambia lo que hay en total')

    def test_filtros_por_fecha_y_tipo_en_un_producto_y_en_todos(self):
        self.historia()
        solo = self.Mov.movimientos(producto_id=self.mesa.id, desde='2025-03-02', hasta='2025-03-03')
        self.assertEqual([f['tipo'] for f in solo['filas']], ['venta', 'ajuste'])
        self.assertEqual([f['queda'] for f in solo['filas']], [6.0, 7.0], 'lo que quedó no cambia con el filtro')
        for tipo in ('compra', 'venta', 'devolucion', 'ajuste', 'traslado', 'otro'):
            with self.subTest(tipo=tipo):
                de_uno = self.Mov.movimientos(producto_id=self.mesa.id, tipo=tipo)['filas']
                de_todos = self.Mov.movimientos(desde='2025-03-01', hasta='2025-03-05', tipo=tipo)['filas']
                de_todos = [f for f in de_todos if f['producto']['id'] == self.mesa.id]
                self.assertEqual([f['id'] for f in de_uno], [f['id'] for f in de_todos],
                                 'el filtro del servidor y el de la lista dicen lo mismo')
                self.assertTrue(all(f['tipo'] == tipo for f in de_uno))
                self.assertEqual(len(de_uno), 0 if tipo == 'otro' else 1)
        todos = self.Mov.movimientos(desde='2025-03-01', hasta='2025-03-05')
        mias = [f for f in todos['filas'] if f['producto']['id'] == self.mesa.id]
        self.assertEqual(len(mias), 5)
        self.assertEqual(mias[0]['producto']['codigo'], 'MOV-MESA-01')
        self.assertIsNone(mias[0]['queda'], 'en la vista de todos no se calcula lo que quedó')

    def test_si_la_historia_no_cuadra_no_se_inventa_lo_que_quedo(self):
        self.historia()
        # Existencias que aparecen sin un movimiento (como una carga directa).
        self.env['stock.quant']._update_available_quantity(self.mesa, self.tienda, 3.0)
        datos = self.Mov.movimientos(producto_id=self.mesa.id)
        self.assertEqual(datos['existencia'], 10.0)
        self.assertFalse(datos['cuadra'])
        self.assertEqual(datos['diferencia'], 3.0)
        self.assertTrue(all(f['queda'] is None for f in datos['filas']))

    def test_paginas(self):
        self.historia()
        primera = self.Mov.movimientos(producto_id=self.mesa.id, por_pagina=2)
        segunda = self.Mov.movimientos(producto_id=self.mesa.id, por_pagina=2, pagina=1)
        tercera = self.Mov.movimientos(producto_id=self.mesa.id, por_pagina=2, pagina=2)
        self.assertEqual((len(primera['filas']), primera['hay_mas']), (2, True))
        self.assertEqual((len(segunda['filas']), segunda['hay_mas']), (2, True))
        self.assertEqual((len(tercera['filas']), tercera['hay_mas']), (1, False))
        self.assertEqual(tercera['filas'][0]['tipo'], 'compra')

    def test_buscar_por_nombre_codigo_o_codigo_de_barras(self):
        for texto in ('mesa de prueba movim', 'MOV-MESA-01', 'mov-mesa', '7700000000017', 'prueba movimientos mesa'):
            with self.subTest(texto=texto):
                encontrados = self.Mov.buscar_productos(texto)
                self.assertIn(self.mesa.id, [p['id'] for p in encontrados])
        exacto = self.Mov.buscar_productos('7700000000017')
        self.assertEqual(exacto[0]['id'], self.mesa.id, 'el código de barras exacto va primero')
        self.assertEqual(exacto[0]['codigo'], 'MOV-MESA-01')
        self.assertEqual(self.Mov.buscar_productos('m'), [], 'con una letra no se busca')

    def test_solo_gerencia_y_administradores(self):
        Mov = self.env['dcasa.movimientos'].with_user(self.vendedora)
        for metodo, argumentos in (('movimientos', ()), ('buscar_productos', ('mesa',)), ('opciones', ())):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                getattr(Mov, metodo)(*argumentos)
        menus = self.env['ir.ui.menu'].with_user(self.vendedora).load_menus(False)
        visibles = {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}
        self.assertNotIn('dcasa_interfaz.menu_dcasa_movimientos', visibles)
        menus = self.env['ir.ui.menu'].with_user(self.gerencia).load_menus(False)
        visibles = {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}
        self.assertIn('dcasa_interfaz.menu_dcasa_movimientos', visibles)
        admin = self.env.ref('base.user_admin')
        self.assertTrue(self.env['dcasa.movimientos'].with_user(admin).opciones()['tipos'])

    def test_el_servidor_valida_cada_dato(self):
        for argumentos in ({'tipo': 'robo'}, {'desde': 'ayer no'}, {'desde': '2025-03-05', 'hasta': '2025-03-01'},
                           {'producto_id': 'mesa'}, {'producto_id': 999999999}, {'pagina': 'dos'}):
            with self.subTest(argumentos=argumentos), self.assertRaises(UserError):
                self.Mov.movimientos(**argumentos)
