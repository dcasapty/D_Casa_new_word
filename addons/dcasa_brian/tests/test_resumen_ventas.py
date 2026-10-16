"""«Vendido» en Brian es lo mismo que en el Inicio: pedidos facturados por completo, el día de su última factura.

``resumen_ventas`` ya no cuenta cotizaciones, pedidos «por facturar» ni facturas en borrador, y quien vende sin
controlar la tienda (la Vendedora) ve solo lo suyo, como su tarjeta del Inicio."""
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestResumenVentasFacturadas(TransactionCase):

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

    def test_solo_cuentan_los_pedidos_facturados_por_completo(self):
        antes = self.resumen(self.gerente)['ventas']
        self.pedido(self.ana, confirmar=False)                          # cotización
        self.pedido(self.ana)                                           # por facturar (apartado)
        self.pedido(self.ana, facturar=True, publicar=False)            # factura en borrador
        vendido = self.pedido(self.ana, cantidad=2, facturar=True)      # esta sí
        datos = self.resumen(self.gerente)
        self.assertEqual(datos['ventas'], antes + 1)
        self.assertGreater(vendido.amount_total, 0)

    def test_el_dia_es_el_de_la_factura_no_el_del_pedido(self):
        """Un apartado de hace días que se factura hoy se vendió hoy."""
        antes = self.resumen(self.gerente)['ventas']
        orden = self.pedido(self.ana)
        orden.date_order = fields.Datetime.now() - timedelta(days=6)
        self.assertEqual(self.resumen(self.gerente)['ventas'], antes)
        orden._create_invoices().action_post()
        self.assertEqual(self.resumen(self.gerente)['ventas'], antes + 1)

    def test_la_vendedora_ve_solo_lo_suyo_y_gerencia_todo(self):
        mia = self.pedido(self.ana, cantidad=2, facturar=True)
        ajena = self.pedido(self.luis, cantidad=3, facturar=True)
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
        venta = self.pedido(self.ana, cantidad=2, facturar=True)
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
        ganancia = self.resumen(self.gerente)['ganancia_sin_itbms']
        self.assertIn('aviso', ganancia, 'una venta sin costo no inventa ganancia: se avisa')

    def test_el_reporte_del_dia_explica_el_itbms_de_lo_vendido_hoy(self):
        venta = self.pedido(self.ana, facturar=True)
        reporte = self.env['brian.herramientas'].with_user(self.gerente).ejecutar('reporte_del_dia', {})
        fila = next(f for f in reporte['datos']['cifras'] if f['titulo'] == 'Vendido hoy')
        self.assertEqual(fila['nota'], 'sin ITBMS')
        self.assertIn('itbms', fila)
        self.assertIn('total_con_itbms', fila)
        self.assertGreater(venta.amount_tax, 0)
