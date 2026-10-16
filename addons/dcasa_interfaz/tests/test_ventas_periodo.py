"""Ventas del Inicio por periodo (Hoy · semana · mes · rango), ITBMS claro, ganancia y las listas de Gerencia."""
from datetime import date, timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_inicio_por_rol import VentasCommon


@tagged('post_install', '-at_install')
class TestVentasPorPeriodo(VentasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.itbms = cls.env['account.tax'].create({
            'name': 'ITBMS periodo 7%', 'amount': 7.0, 'amount_type': 'percent', 'type_tax_use': 'sale',
            'company_id': cls.env.company.id})
        cls.cama = cls.env['product.product'].create({
            'name': 'Cama periodo', 'list_price': 200.0, 'standard_price': 120.0,
            'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.sin_costo = cls.env['product.product'].create({
            'name': 'Silla periodo sin costo', 'list_price': 50.0, 'standard_price': 0.0,
            'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.tablero = cls.env['dcasa.tablero']

    def _venta(self, dias_atras=0, producto=None, vendedor=None):
        orden = self.pedido(vendedor=vendedor, producto=producto or self.cama)
        self.facturar(orden, fecha=self.hoy - timedelta(days=dias_atras))
        return orden

    def _ventas(self, usuario, periodo='hoy', desde=None, hasta=None):
        return self.tablero.with_user(usuario).ventas_del_periodo(periodo, desde, hasta)

    # --- Los periodos -------------------------------------------------------------------------

    def test_los_rangos_de_cada_periodo_y_con_que_se_comparan(self):
        rango = self.tablero._rango_del_periodo
        miercoles = date(2026, 10, 14)
        self.assertEqual(miercoles.weekday(), 2)
        hoy = rango('hoy', hoy=miercoles)
        self.assertEqual((hoy['desde'], hoy['hasta']), (miercoles, miercoles))
        self.assertEqual((hoy['anterior_desde'], hoy['anterior_hasta']), (date(2026, 10, 13),) * 2)
        semana = rango('semana', hoy=miercoles)
        self.assertEqual((semana['desde'], semana['hasta']), (date(2026, 10, 12), miercoles))
        self.assertEqual((semana['anterior_desde'], semana['anterior_hasta']), (date(2026, 10, 5), date(2026, 10, 7)))
        mes = rango('mes', hoy=miercoles)
        self.assertEqual((mes['desde'], mes['hasta']), (date(2026, 10, 1), miercoles))
        self.assertEqual((mes['anterior_desde'], mes['anterior_hasta']), (date(2026, 9, 1), date(2026, 9, 14)))
        # el 31 de octubre contra septiembre, que tiene 30 días
        fin = rango('mes', hoy=date(2026, 10, 31))
        self.assertEqual((fin['anterior_desde'], fin['anterior_hasta']), (date(2026, 9, 1), date(2026, 9, 30)))
        libre = rango('rango', '2026-10-01', '2026-10-10', hoy=miercoles)
        self.assertEqual((libre['desde'], libre['hasta']), (date(2026, 10, 1), date(2026, 10, 10)))
        self.assertEqual((libre['anterior_desde'], libre['anterior_hasta']), (date(2026, 9, 21), date(2026, 9, 30)))

    def test_un_rango_invalido_se_rechaza_con_un_mensaje_claro(self):
        for desde, hasta in (('2026-10-10', '2026-10-01'), (None, None), ('2024-01-01', '2026-10-01')):
            with self.subTest(desde=desde, hasta=hasta), self.assertRaises(UserError):
                self._ventas(self.gerencia, 'rango', desde, hasta)
        with self.assertRaises(UserError):
            self._ventas(self.gerencia, 'siempre')

    def test_hoy_semana_y_mes_suman_las_ventas_de_su_dia(self):
        base = self._ventas(self.gerencia, 'hoy')['actual']['sin_itbms']
        hoy = self._venta(0)
        self._venta(1)
        lunes_pasado = self.hoy - timedelta(days=self.hoy.weekday() + 7)
        pasada = self.pedido()
        self.facturar(pasada, fecha=lunes_pasado)
        datos = self._ventas(self.gerencia, 'hoy')
        self.assertAlmostEqual(datos['actual']['sin_itbms'] - base, hoy.amount_untaxed, places=2)
        semana = self._ventas(self.gerencia, 'semana')
        self.assertNotIn(pasada, self.env['sale.order'].search(semana['accion']['domain']),
                         'la venta de la semana pasada no entra en «esta semana»')
        self.assertIn(hoy, self.env['sale.order'].search(semana['accion']['domain']))
        mes = self._ventas(self.gerencia, 'mes')
        self.assertIn(hoy, self.env['sale.order'].search(mes['accion']['domain']))

    # --- ITBMS claro --------------------------------------------------------------------------

    def test_cada_cifra_trae_sin_itbms_itbms_y_total_que_cuadran(self):
        antes = self._ventas(self.gerencia, 'hoy')['actual']
        orden = self._venta(0)
        actual = self._ventas(self.gerencia, 'hoy')['actual']
        self.assertAlmostEqual(actual['sin_itbms'] - antes['sin_itbms'], 200.0, places=2)
        self.assertAlmostEqual(actual['itbms'] - antes['itbms'], 14.0, places=2)
        self.assertAlmostEqual(actual['total'] - antes['total'], 214.0, places=2)
        self.assertAlmostEqual(orden.amount_untaxed + orden.amount_tax, orden.amount_total, places=2)

    # --- Ganancia (solo Gerencia) ------------------------------------------------------------

    def test_la_ganancia_es_venta_sin_itbms_menos_costo(self):
        antes = self._ventas(self.gerencia, 'hoy')['actual']['ganancia']
        self._venta(0)
        ganancia = self._ventas(self.gerencia, 'hoy')['actual']['ganancia']
        self.assertAlmostEqual(ganancia['valor'] - antes['valor'], 80.0, places=2, msg='200 − 120, sin ITBMS')
        self.assertEqual(ganancia['ventas_con_costo'] - antes['ventas_con_costo'], 1)

    def test_una_venta_con_mercancia_sin_costo_no_cuenta_y_se_avisa(self):
        antes = self._ventas(self.gerencia, 'hoy')['actual']['ganancia']
        self._venta(0, producto=self.sin_costo)
        ganancia = self._ventas(self.gerencia, 'hoy')['actual']['ganancia']
        self.assertEqual(ganancia['ventas_sin_costo'] - antes['ventas_sin_costo'], 1)
        self.assertAlmostEqual(ganancia['valor'], antes['valor'], places=2)

    def test_la_vendedora_no_ve_ganancia_ni_ventas_ajenas(self):
        mia, ajena = self._venta(0, vendedor=self.vendedora), self._venta(0, vendedor=self.otra)
        datos = self._ventas(self.vendedora, 'hoy')
        self.assertIsNone(datos['actual']['ganancia'], 'los costos son de Gerencia')
        self.assertIsNone(datos['anterior']['ganancia'])
        lista = self.env['sale.order'].search(datos['accion']['domain'])
        self.assertIn(mia, lista)
        self.assertNotIn(ajena, lista)
        self.assertFalse(self.tablero.with_user(self.vendedora).obtener_datos()['ve_utilidad'])

    def test_contabilidad_ve_las_ventas_pero_no_la_ganancia(self):
        contador = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Contador utilidad', 'login': 'contador_utilidad', 'tz': 'America/Panama',
            'group_ids': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('account.group_account_user').id,
                                       self.env.ref('sales_team.group_sale_salesman').id])]})
        self._venta(0)
        datos = self._ventas(contador, 'hoy')
        self.assertIsNone(datos['actual']['ganancia'])
        self.assertFalse(self.tablero.with_user(contador).obtener_datos()['ve_utilidad'])

    def test_la_comparacion_con_el_periodo_anterior(self):
        self._venta(0)
        ayer = self._ventas(self.gerencia, 'hoy')['anterior']['sin_itbms']
        for _ in range(2):
            self._venta(1)
        datos = self._ventas(self.gerencia, 'hoy')
        self.assertEqual(datos['anterior']['etiqueta'], 'Ayer')
        self.assertAlmostEqual(datos['anterior']['sin_itbms'] - ayer, 400.0, places=2)
        if datos['anterior']['sin_itbms']:
            esperado = (datos['actual']['sin_itbms'] - datos['anterior']['sin_itbms']) / datos['anterior']['sin_itbms']
            self.assertAlmostEqual(datos['variacion_pct'], round(esperado * 100, 1), places=1)

    # --- Las listas de cotizaciones y entregas, y los avisos -----------------------------------

    def test_cotizaciones_abiertas_y_entregas_pendientes_van_en_listas(self):
        cotizacion = self.pedido(confirmar=False, producto=self.cama)
        despachar = self.pedido(producto=self.cama)       # confirmada: su entrega queda pendiente
        datos = self.tablero.with_user(self.gerencia).obtener_datos()
        self.assertIn(cotizacion.name, [f['nombre'] for f in datos['cotizaciones']['filas']])
        self.assertGreaterEqual(datos['cotizaciones']['cantidad'], 1)
        self.assertAlmostEqual(
            datos['cotizaciones']['total'] - datos['cotizaciones']['sin_itbms'],
            sum(self.env['sale.order'].search(datos['cotizaciones']['accion']['domain']).mapped('amount_tax')),
            places=2)
        if despachar.picking_ids:
            self.assertIn(despachar.picking_ids[0].name, [f['nombre'] for f in datos['entregas']['filas']])
        self.assertLessEqual(len(datos['cotizaciones']['filas']), 5)
        self.assertLessEqual(len(datos['entregas']['filas']), 5)

    def test_la_lista_pone_primero_la_cotizacion_mas_antigua(self):
        vieja = self.pedido(confirmar=False, producto=self.cama)
        vieja.date_order = vieja.date_order - timedelta(days=9)
        nueva = self.pedido(confirmar=False, producto=self.cama)
        filas = self.tablero.with_user(self.gerencia).obtener_datos()['cotizaciones']['filas']
        nombres = [f['nombre'] for f in filas]
        self.assertLess(nombres.index(vieja.name), nombres.index(nueva.name) if nueva.name in nombres else 99)
        self.assertEqual(next(f for f in filas if f['nombre'] == vieja.name)['dias'], 9)

    def test_avisos_de_stock_bajo_y_de_productos_sin_costo(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa.stock_bajo_umbral', '5')
        escaso = self.env['product.product'].create({
            'name': 'Mesa por agotarse', 'is_storable': True, 'list_price': 90.0, 'standard_price': 40.0})
        almacen = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        self.env['stock.quant']._update_available_quantity(escaso, almacen.lot_stock_id, 3.0)
        sin_costo = self.env['product.product'].create({
            'name': 'Banco sin costo cargado', 'is_storable': True, 'list_price': 70.0, 'standard_price': 0.0})
        avisos = {a['clave']: a for a in self.tablero.with_user(self.gerencia).obtener_datos()['atencion']}
        self.assertIn('stock_bajo', avisos)
        self.assertIn(escaso, self.env['product.product'].search(avisos['stock_bajo']['accion']['domain']))
        self.assertIn('productos_sin_costo', avisos)
        self.assertIn(sin_costo, self.env['product.product'].search(avisos['productos_sin_costo']['accion']['domain']))
        # la vendedora no tiene panel completo: ni avisos ni costos
        self.assertFalse(self.tablero.with_user(self.vendedora).obtener_datos()['atencion'])
