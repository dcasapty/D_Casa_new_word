"""Contar con el lector: lo contado reemplaza lo que dice el sistema, con el ajuste de Odoo y sus permisos."""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .comun import BarrasCommon


@tagged('post_install', '-at_install')
class TestContar(BarrasCommon):

    def contar(self, producto, cantidad, ubicacion=None, usuario=None, esperado=None):
        """Cuenta como lo hace la pantalla: manda lo que vio (por defecto, lo que dice el sistema ahora)."""
        ubicacion = ubicacion or self.bodega
        if esperado is None:
            esperado = self.existencia(producto, ubicacion)
        return self.como(usuario or self.gerencia).contar(producto.id, ubicacion.id, cantidad, esperado)

    def test_lo_contado_reemplaza_lo_que_decia_el_sistema(self):
        r = self.contar(self.cama, 20)
        self.assertEqual((r['cambio'], r['antes'], r['despues'], r['diferencia']), (True, 12, 20, 8))
        self.assertEqual(self.existencia(self.cama), 20)
        self.assertEqual(r['ficha']['unidades'], 20)
        # y baja también
        r = self.contar(self.cama, 3)
        self.assertEqual((r['antes'], r['despues'], r['diferencia']), (20, 3, -17))
        self.assertEqual(self.existencia(self.cama), 3)
        self.assertEqual(r['ficha']['etiqueta'], 'pocas')

    def test_dejar_en_cero_y_contar_donde_no_habia_nada(self):
        self.contar(self.cama, 0)
        self.assertEqual(self.existencia(self.cama), 0)
        self.assertEqual(self.contar(self.zapatera, 7)['antes'], 0)
        self.assertEqual(self.existencia(self.zapatera), 7)

    def test_queda_en_el_historial_de_movimientos_con_quien_conto(self):
        self.contar(self.cama, 15)
        movimiento = self.env['stock.move'].search(
            [('product_id', '=', self.cama.id), ('is_inventory', '=', True)], order='id desc', limit=1)
        self.assertEqual(movimiento.product_uom_qty, 3)
        self.assertIn('Conteo con lector', movimiento.inventory_name)
        self.assertIn(self.gerencia.name, movimiento.inventory_name)

    def test_el_stock_del_producto_se_actualiza_solo(self):
        self.contar(self.cama, 40)
        self.assertEqual(self.cama.product_tmpl_id.dcasa_stock, 40)

    def test_si_coincide_no_se_ajusta_nada(self):
        antes = self.env['stock.move'].search_count([('product_id', '=', self.cama.id)])
        r = self.contar(self.cama, 12)
        self.assertEqual((r['cambio'], r['diferencia']), (False, 0))
        self.assertEqual(self.env['stock.move'].search_count([('product_id', '=', self.cama.id)]), antes)

    def test_solo_gerencia_cuenta(self):
        with self.assertRaises(AccessError):
            self.contar(self.cama, 99, usuario=self.vendedora)
        with self.assertRaises(AccessError):
            self.contar(self.cama, 99, usuario=self.sin_inventario)
        self.assertEqual(self.existencia(self.cama), 12)
        self.assertTrue(self.como(self.gerencia).ficha(self.cama.id)['puede_contar'])
        self.assertFalse(self.como(self.vendedora).ficha(self.cama.id)['puede_contar'])

    def test_cantidades_que_no_son_un_conteo(self):
        for mala in (-1, -0.5, 100001, float('nan'), float('inf'), '5', 'abc', None, True, [3]):
            with self.assertUserError():
                self.contar(self.cama, mala, esperado=12)
        self.assertEqual(self.existencia(self.cama), 12)

    def test_lo_que_no_controla_inventario_o_va_por_lotes_no_se_cuenta_aqui(self):
        servicio = self.env['product.product'].create(
            {'name': 'Flete', 'type': 'service', 'list_price': 3, 'default_code': 'FLETE-2'})
        con_lote = self.producto('Con lote', 'LOTE-1', tracking='lot')
        for producto in (servicio, con_lote):
            with self.assertUserError():
                self.contar(producto, 4)
        self.assertFalse(self.como(self.gerencia).ficha(con_lote.id)['puede_contar'])

    def test_la_ubicacion_debe_ser_de_bodega_o_tienda(self):
        clientes = self.env.ref('stock.stock_location_customers')
        for mala in (clientes.id, True, None, 'x', 987654321):
            with self.assertUserError():
                self.como(self.gerencia).contar(self.cama.id, mala, 5, 12)
        self.assertEqual(self.existencia(self.cama), 12)

    def test_producto_que_no_existe(self):
        for malo in (True, None, 'x', 987654321):
            with self.assertUserError():
                self.como(self.gerencia).contar(malo, self.bodega.id, 5, 12)

    def test_se_cuenta_por_ubicacion(self):
        tienda = self.env['stock.location'].create({
            'name': 'Tienda de prueba', 'usage': 'internal', 'location_id': self.almacen.view_location_id.id})
        self.Quant._update_available_quantity(self.cama, tienda, 4)
        ficha = self.como(self.gerencia).ficha(self.cama.id)
        self.assertEqual(ficha['unidades'], 16)
        self.assertEqual(len(ficha['ubicaciones']), 2)
        self.assertIn(tienda.id, [u['id'] for u in ficha['lugares_para_contar']])
        r = self.contar(self.cama, 9, ubicacion=tienda)
        self.assertEqual((r['antes'], r['despues']), (4, 9))
        self.assertEqual(self.existencia(self.cama), 12, 'la bodega no se tocó')
        self.assertEqual(r['ficha']['unidades'], 21)

    def test_la_unidad_de_medida_manda_sin_decimales_en_unidades_enteras(self):
        """12.6 no se guarda como 13 ni 12.004 como un movimiento de cero: se rechaza."""
        for decimal in (12.6, 3.3, 12.004, 0.5):
            with self.assertUserError('enteras'):
                self.contar(self.cama, decimal)
        self.assertEqual(self.existencia(self.cama), 12)
        self.assertEqual(self.contar(self.cama, 12.0)['cambio'], False, '12.0 es 12')
        self.assertEqual(self.contar(self.cama, 20.0)['despues'], 20)
        ficha = self.como(self.gerencia).ficha(self.cama.id)
        self.assertFalse(ficha['admite_decimales'])
        self.assertTrue(ficha['unidad'])

    def test_si_el_sistema_cambio_mientras_se_contaba_no_se_guarda(self):
        """La pantalla mostraba 12; una venta lo bajó a 9; contar «12» encima dejaría el stock 3 de más."""
        self.Quant._update_available_quantity(self.cama, self.bodega, -3)     # la venta
        with self.assertUserError('cambió de 12 a 9'):
            self.contar(self.cama, 12, esperado=12)
        self.assertEqual(self.existencia(self.cama), 9, 'no se tocó')
        self.assertEqual(self.contar(self.cama, 12, esperado=9)['despues'], 12, 'con lo que ve ahora, sí')

    def test_el_esperado_tambien_debe_ser_un_numero(self):
        for malo in (None, 'x', True, float('nan')):
            with self.assertUserError():
                self.como(self.gerencia).contar(self.cama.id, self.bodega.id, 5, malo)

    def test_varias_lineas_de_existencia_en_la_misma_ubicacion_no_se_cuentan_aqui(self):
        """Odoo ajustaría solo una de las líneas y el total no quedaría en lo contado."""
        dueno = self.env['res.partner'].create({'name': 'Dueño de prueba'})
        self.Quant._update_available_quantity(self.cama, self.bodega, 4, owner_id=dueno)
        self.assertEqual(self.Quant.search_count(
            [('product_id', '=', self.cama.id), ('location_id', '=', self.bodega.id)]), 2)
        with self.assertUserError('Inventario físico'):
            self.contar(self.cama, 20, esperado=16)
        self.assertEqual(self.existencia(self.cama), 16)

    def test_otra_compania_no_se_ve_ni_se_cuenta(self):
        otra = self.env['res.company'].create({'name': 'Otra empresa de prueba'})
        ajena = self.env['stock.location'].create({
            'name': 'Bodega ajena', 'usage': 'internal', 'company_id': otra.id})
        ficha = self.como(self.gerencia).ficha(self.cama.id)
        self.assertNotIn(ajena.id, [u['id'] for u in ficha['lugares_para_contar']])
        with self.assertUserError('bodega ni de tienda'):
            self.contar(self.cama, 5, ubicacion=ajena, esperado=0)
