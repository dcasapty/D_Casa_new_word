"""Las ventas en Brian son las mismas del Inicio.

``resumen_ventas`` no cuenta cotizaciones, pedidos «por facturar» ni facturas en borrador. Quien vende sin controlar la
tienda (la Vendedora) ve solo lo suyo, facturado por completo y el día de su última factura, como su tarjeta del Inicio.
Gerencia cuenta como su Inicio, sobre las facturas (2026-10-17): «facturado» por defecto (todas las publicadas, por su
fecha, igual que Contabilidad), «con_abonos» o «completadas», y puede pedir una vendedora. ``comparar_ventas`` da las
cifras del bloque «Comparar»."""
from datetime import date, timedelta

from odoo import Command, fields
from odoo.addons.dcasa_brian.models.herramientas_comun import fecha as c_fecha
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


class ResumenVentasCommon(TransactionCase):
    """Vendedoras, Gerencia, un cliente y un producto; pedidos que se facturan y se pagan a pedido."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            return Usuarios.create({
                'name': login.replace('_', ' ').title(), 'login': login, 'tz': 'America/Panama',
                'group_ids': [Command.set([cls.env.ref(g).id for g in ('base.group_user', *grupos)])]})

        cls.ana = usuario('brian_rv_ana', ('dcasa_base.group_vendedora',))
        cls.luis = usuario('brian_rv_luis', ('dcasa_base.group_vendedora',))
        cls.gerente = usuario('brian_rv_gerente', ('dcasa_base.group_gerencia',))
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente resumen de ventas'})
        cls.producto = cls.env['product.product'].create({'name': 'Zzsilla resumen', 'list_price': 80.0})
        cls.banco = cls.env['account.journal'].create({'name': 'Banco resumen', 'type': 'bank', 'code': 'BRSM'})

    def pagar(self, orden, monto=None, fecha=None):
        """Paga las facturas del pedido (todo, o ``monto``)."""
        for factura in orden.invoice_ids.filtered(lambda f: f.state == 'posted'):
            valores = {'payment_date': fecha or factura.invoice_date, 'journal_id': self.banco.id}
            if monto is not None:
                valores['amount'] = monto
            self.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=factura.ids).create(valores)._create_payments()
        return orden

    def pedido(self, vendedor, cantidad=1, confirmar=True, facturar=False, publicar=True):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': vendedor.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': cantidad})]})
        if confirmar:
            orden.action_confirm()
        if facturar:
            factura = orden._create_invoices()
            if publicar:
                factura.action_post()
        return orden

    def resumen(self, usuario, **argumentos):
        respuesta = self.env['brian.herramientas'].with_user(usuario).ejecutar(
            'resumen_ventas', {'periodo': 'hoy', **argumentos})
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']


@tagged('post_install', '-at_install')
class TestResumenVentasFacturadas(ResumenVentasCommon):

    def test_solo_cuentan_los_pedidos_facturados_por_completo(self):
        antes = self.resumen(self.gerente)['ventas']
        completadas_antes = self.resumen(self.gerente, base='completadas')['ventas']
        self.pedido(self.ana, confirmar=False)                          # cotización
        self.pedido(self.ana)                                           # por facturar (apartado)
        self.pedido(self.ana, facturar=True, publicar=False)            # factura en borrador
        sin_pago = self.pedido(self.ana, facturar=True)                 # facturada sin pago: no es «completada»
        vendido = self.pagar(self.pedido(self.ana, cantidad=2, facturar=True))      # esta sí
        datos = self.resumen(self.gerente)
        self.assertEqual(datos['ventas'], antes + 2, '«Facturado»: las dos facturas publicadas')
        self.assertEqual(datos['cuenta'], 'Facturado: todas las facturas, igual que Contabilidad')
        self.assertEqual(datos['de_un_pedido'], f'{datos["ventas"]} de {datos["ventas"]} salieron de un pedido de una '
                                                'vendedora')
        completadas = self.resumen(self.gerente, base='completadas')
        self.assertEqual(completadas['ventas'], completadas_antes + 1)
        self.assertEqual(completadas['cuenta'], 'Completadas: pagadas al 100 %, el día del último pago')
        self.assertNotIn('de_un_pedido', completadas)
        self.assertGreater(vendido.amount_total, 0)
        # La vendedora sigue contando lo facturado por completo (también lo que no tiene pago).
        self.assertEqual(self.resumen(self.ana)['ventas'], 2)
        self.assertNotIn('cuenta', self.resumen(self.ana))
        self.assertTrue(sin_pago)

    def test_el_dia_es_el_de_la_factura_no_el_del_pedido(self):
        """Un apartado de hace días que se factura hoy se vendió hoy (lo de la vendedora)."""
        antes = self.resumen(self.ana)['ventas']
        orden = self.pedido(self.ana)
        orden.date_order = fields.Datetime.now() - timedelta(days=6)
        self.assertEqual(self.resumen(self.ana)['ventas'], antes)
        orden._create_invoices().action_post()
        self.assertEqual(self.resumen(self.ana)['ventas'], antes + 1)

    def test_la_vendedora_ve_solo_lo_suyo_y_gerencia_todo(self):
        mia = self.pagar(self.pedido(self.ana, cantidad=2, facturar=True))
        ajena = self.pagar(self.pedido(self.luis, cantidad=3, facturar=True))
        self.pedido(self.ana)                                           # por facturar: no cuenta
        de_ana = self.resumen(self.ana)
        self.assertEqual(de_ana['ventas'], 1)
        self.assertEqual([v['vendedor'] for v in de_ana['por_vendedor_sin_itbms']], [self.ana.name])
        self.assertIn(f'{mia.amount_untaxed:,.2f}', de_ana['ventas_sin_itbms'])
        de_luis = self.resumen(self.luis)
        self.assertEqual(de_luis['ventas'], 1)
        self.assertEqual([v['vendedor'] for v in de_luis['por_vendedor_sin_itbms']], [self.luis.name])
        todas = self.resumen(self.gerente)
        nombres = {v['vendedor'] for v in todas['por_vendedor_sin_itbms']}
        self.assertTrue({self.ana.name, self.luis.name} <= nombres)
        self.assertGreaterEqual(todas['ventas'], 2)
        self.assertGreater(ajena.amount_total, mia.amount_total)

    def test_el_resumen_del_dia_de_brian_es_el_del_inicio(self):
        """«¿Cómo vamos hoy?» usa el tablero: la vendedora recibe su panel propio, sin cobros ni totales."""
        self.pedido(self.ana, facturar=True)
        self.pedido(self.luis, facturar=True)
        datos = self.env['brian.herramientas'].with_user(self.ana).ejecutar('reporte_del_dia', {})
        self.assertTrue(datos.get('ok'), datos)
        titulos = {c['titulo'] for c in datos['datos']['cifras']}
        self.assertEqual(titulos, {'Vendido hoy', 'Mis cotizaciones'})

    # --- ITBMS claro y ganancia (criterio contable del 2026-10-16) ----------------------------------------

    def test_las_ventas_van_sin_itbms_y_el_itbms_y_el_total_aparte(self):
        venta = self.pedido(self.ana, cantidad=2, facturar=True)
        datos = self.resumen(self.ana)
        self.assertEqual(datos['ventas_sin_itbms'], f'${venta.amount_untaxed:,.2f}')
        self.assertEqual(datos['itbms'], f'${venta.amount_tax:,.2f}')
        self.assertEqual(datos['total_con_itbms'], f'${venta.amount_total:,.2f}')
        self.assertEqual(datos['ticket_promedio_sin_itbms'], f'${venta.amount_untaxed:,.2f}')
        self.assertNotIn('total', datos, 'una llave «total» sin decir si lleva ITBMS confunde')
        self.assertIn(f'${venta.amount_untaxed:,.2f}', {p['total_sin_itbms'] for p in datos['productos_mas_vendidos']})

    def test_la_ganancia_la_recibe_solo_gerencia(self):
        self.producto.standard_price = 50.0
        venta = self.pagar(self.pedido(self.ana, cantidad=2, facturar=True))
        self.assertEqual(venta.dcasa_utilidad, 2 * (80.0 - 50.0))
        de_gerencia = self.resumen(self.gerente)
        self.assertIn('ganancia_sin_itbms', de_gerencia)
        self.assertGreaterEqual(de_gerencia['ganancia_sin_itbms']['ventas_con_costo'], 1)
        self.assertNotIn('ganancia_sin_itbms', self.resumen(self.ana), 'la vendedora no ve costos ni ganancia')
        # el reporte del día: lo mismo
        reporte = self.env['brian.herramientas'].with_user(self.gerente).ejecutar('reporte_del_dia', {})
        self.assertTrue(reporte.get('ok'), reporte)
        self.assertIn('ganancia_de_hoy_sin_itbms', reporte['datos'])
        reporte = self.env['brian.herramientas'].with_user(self.ana).ejecutar('reporte_del_dia', {})
        self.assertNotIn('ganancia_de_hoy_sin_itbms', reporte['datos'])

    def test_la_ganancia_avisa_de_lo_que_no_tiene_costo(self):
        sin_costo = self.env['product.product'].create({'name': 'Zzsilla sin costo', 'list_price': 60.0})
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': self.ana.id,
            'order_line': [Command.create({'product_id': sin_costo.id, 'product_uom_qty': 1})]})
        orden.action_confirm()
        orden._create_invoices().action_post()
        self.pagar(orden)
        ganancia = self.resumen(self.gerente)['ganancia_sin_itbms']
        self.assertIn('aviso', ganancia, 'una venta sin costo no inventa ganancia: se avisa')

    def test_el_reporte_del_dia_explica_el_itbms_de_lo_vendido_hoy(self):
        venta = self.pedido(self.ana, facturar=True)
        # La vendedora: «Vendido hoy», sin ITBMS, con el ITBMS y el total aparte.
        reporte = self.env['brian.herramientas'].with_user(self.ana).ejecutar('reporte_del_dia', {})
        fila = next(f for f in reporte['datos']['cifras'] if f['titulo'] == 'Vendido hoy')
        self.assertEqual(fila['nota'], 'sin ITBMS')
        self.assertIn('itbms', fila)
        self.assertIn('total_con_itbms', fila)
        self.assertGreater(venta.amount_tax, 0)
        # Gerencia: las ventas de hoy como su Inicio («Facturado»), con las mismas palabras del interruptor.
        reporte = self.env['brian.herramientas'].with_user(self.gerente).ejecutar('reporte_del_dia', {})
        self.assertNotIn('Vendido hoy', {f['titulo'] for f in reporte['datos']['cifras']})
        hoy = reporte['datos']['ventas_de_hoy']
        self.assertEqual(hoy['cuenta'], 'Facturado: todas las facturas, igual que Contabilidad')
        self.assertTrue(hoy['de_un_pedido'].endswith('de un pedido de una vendedora'))
        # Lo más vendido de Brian es el del Inicio de Gerencia.
        inicio_completo = self.env['dcasa.tablero'].with_user(self.gerente).obtener_datos()
        self.assertEqual(reporte['datos']['mas_vendidos_30_dias'],
                         [{'producto': t['nombre'], 'unidades': t['cantidad']} for t in inicio_completo['top']])
        inicio = self.env['dcasa.tablero'].with_user(self.gerente).ventas_del_periodo('hoy')['actual']
        self.assertEqual(hoy['ventas_sin_itbms'], f'${inicio["sin_itbms"]:,.2f}')
        self.assertEqual(hoy['ventas'], inicio['cuantas'])

    def test_los_mas_vendidos_de_brian_no_cuentan_el_flete_ni_los_descuentos(self):
        flete = self.env['product.product'].create({'name': 'Zzflete resumen', 'type': 'service', 'list_price': 25.0})
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': self.ana.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1}),
                           Command.create({'product_id': flete.id, 'product_uom_qty': 5})]})
        orden.action_confirm()
        orden._create_invoices().action_post()
        nombres = {p['producto'] for p in self.resumen(self.ana)['productos_mas_vendidos']}
        self.assertIn(self.producto.display_name, nombres)
        self.assertNotIn(flete.display_name, nombres, 'el flete es un servicio, no un producto vendido')

    def test_el_por_cobrar_de_las_cotizaciones_dice_que_es_con_itbms(self):
        self.pedido(self.ana, confirmar=False)
        reporte = self.env['brian.herramientas'].with_user(self.ana).ejecutar('reporte_del_dia', {})
        detalle = next(f['detalle'] for f in reporte['datos']['cifras'] if f['titulo'] == 'Mis cotizaciones')
        self.assertIn('con ITBMS', detalle)


@tagged('post_install', '-at_install')
class TestCompararVentasBrian(ResumenVentasCommon):
    """«¿Cómo vamos contra septiembre?»: Brian da las mismas cifras del bloque «Comparar» del Inicio de Gerencia."""

    def comparar(self, usuario, **argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar('comparar_ventas', argumentos)

    def test_las_mismas_cifras_del_inicio(self):
        self.pagar(self.pedido(self.ana, cantidad=2, facturar=True))
        respuesta = self.comparar(self.gerente, comparacion='mes', b='septiembre')
        self.assertTrue(respuesta.get('ok'), respuesta)
        datos = respuesta['datos']
        septiembre = self.env['brian.herramientas'].with_user(self.gerente)._b_mes_completo('septiembre')
        inicio = self.env['dcasa.tablero'].with_user(self.gerente).comparar_ventas('mes', mes=septiembre)
        self.assertTrue(datos['llevas'].startswith('Llevas '))
        self.assertIn(' de septiembre', datos['llevas'])
        self.assertEqual(datos['cuenta'], 'Facturado: todas las facturas, igual que Contabilidad')
        ventas = next(f for f in datos['filas'] if f['cifra'] == 'Ventas (sin ITBMS)')
        self.assertEqual(ventas['a'], f'${next(f for f in inicio["filas"] if f["clave"] == "ventas")["a"]:,.2f}')
        self.assertEqual([f['cifra'] for f in datos['filas']][:4],
                         ['Ventas (sin ITBMS)', 'Ganancia (sin ITBMS)', 'Margen', 'N.º de ventas'])
        self.assertIn('hasta_la_hora', datos, 'hoy cuenta hasta la hora actual')

    def test_con_abonos_y_por_vendedora(self):
        self.pagar(self.pedido(self.ana, cantidad=2, facturar=True), monto=10.0)
        self.pagar(self.pedido(self.luis, cantidad=1, facturar=True))
        datos = self.comparar(self.gerente, comparacion='ayer', base='con_abonos', vendedora=self.ana.name)['datos']
        self.assertEqual(datos['vendedora'], self.ana.name)
        filas = {f['cifra']: f for f in datos['filas']}
        self.assertIn('Falta por cobrar (con ITBMS)', filas)
        self.assertEqual(filas['Ventas (sin ITBMS)']['a'], '$160.00', 'solo lo de Ana')
        self.assertEqual(filas['Ventas (sin ITBMS)']['cambio'], '—', 'contra $0 no hay porcentaje')
        lista = self.comparar(self.gerente, comparacion='ayer', base='con_abonos', vendedora='por vendedora')['datos']
        self.assertNotIn('vendedora', lista, 'la tabla es de todo el equipo')
        nombres = [f['vendedora'] for f in lista['por_vendedora']]
        self.assertLess(nombres.index(self.ana.name), nombres.index(self.luis.name), 'de mayor a menor')
        sin = self.comparar(self.gerente, comparacion='ayer', vendedora='sin vendedora')['datos']
        self.assertEqual(sin['vendedora'], 'Sin vendedora')

    def test_un_rango_de_otro_largo_va_por_dia(self):
        hoy = fields.Date.context_today(self.env['dcasa.tablero'].with_user(self.gerente))
        a0, b0 = hoy - timedelta(days=6), hoy - timedelta(days=40)
        a = f'{a0:%d/%m/%Y}-{hoy:%d/%m/%Y}'
        datos = self.comparar(self.gerente, comparacion='rango', a=a,
                              b=f'del {b0:%d/%m/%Y} al {b0 + timedelta(days=13):%d/%m/%Y}')['datos']
        self.assertIn('por_dia', datos)
        mismo = self.comparar(self.gerente, comparacion='rango', a=a, b=f'{b0:%d/%m/%Y}')['datos']
        self.assertNotIn('por_dia', mismo)
        self.assertIn(c_fecha(b0 + timedelta(days=6)), mismo['b'], 'B del mismo largo que A')

    def test_el_mes_se_entiende_como_lo_dice_la_gente(self):
        herramientas = self.env['brian.herramientas'].with_user(self.gerente)
        hoy = herramientas._b_hoy()
        anterior = date(hoy.year if hoy.month > 9 else hoy.year - 1, 9, 1).strftime('%Y-%m')
        self.assertEqual(herramientas._b_mes_completo('septiembre'), anterior)
        self.assertEqual(herramientas._b_mes_completo('Septiembre 2025'), '2025-09')
        self.assertEqual(herramientas._b_mes_completo('09/2025'), '2025-09')
        self.assertEqual(herramientas._b_mes_completo('2025-09'), '2025-09')
        self.assertEqual(herramientas._b_mes_completo('sep'), anterior)

    def test_un_rango_mal_escrito_se_explica(self):
        respuesta = self.comparar(self.gerente, comparacion='rango', a='la semana pasada', b='01/09/2026')
        self.assertFalse(respuesta['ok'])
        self.assertIn('01/10/2026-07/10/2026', respuesta['error'])
        respuesta = self.comparar(self.gerente, comparacion='rango', a='01/10/2026')
        self.assertFalse(respuesta['ok'])
        respuesta = self.comparar(self.gerente, comparacion='mes', b='el mes del cumpleaños')
        self.assertFalse(respuesta['ok'])

    def test_solo_gerencia_y_la_vendedora_no_ve_lo_de_otras(self):
        respuesta = self.comparar(self.ana, comparacion='ayer')
        self.assertFalse(respuesta['ok'])
        self.assertIn('no tienes permiso', respuesta['error'])
        # resumen_ventas: la vendedora no puede pedir otra vendedora (el servidor del Inicio lo rechaza).
        respuesta = self.env['brian.herramientas'].with_user(self.ana).ejecutar(
            'resumen_ventas', {'periodo': 'hoy', 'vendedora': self.luis.name})
        self.assertFalse(respuesta['ok'])
        self.assertIn('Gerencia', respuesta['error'])
        propia = self.resumen(self.ana, vendedora=self.ana.name, base='con_abonos')
        self.assertNotIn('falta_por_cobrar_con_itbms', propia, 'su Inicio no tiene interruptor')

    def test_resumen_de_gerencia_con_abonos_y_vendedora(self):
        self.pagar(self.pedido(self.ana, cantidad=2, facturar=True), monto=50.0)
        self.pagar(self.pedido(self.luis, cantidad=1, facturar=True))
        datos = self.resumen(self.gerente, base='con_abonos', vendedora=self.ana.name)
        self.assertEqual(datos['ventas'], 1)
        self.assertEqual(datos['vendedora'], self.ana.name)
        self.assertEqual(datos['cuenta'], 'Con abonos: con al menos un abono, por su valor total')
        self.assertIn('falta_por_cobrar_con_itbms', datos)
        self.assertEqual(self.resumen(self.gerente, vendedora=self.ana.name, base='completadas')['ventas'], 0,
                         'en «completadas» todavía no: falta pagarla')
        self.assertEqual(self.resumen(self.gerente, vendedora=self.ana.name)['ventas'], 1,
                         'en «facturado» sí: la factura está publicada')
