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
        self.assertEqual([v['vendedor'] for v in de_ana['por_vendedor']], [self.ana.name])
        self.assertIn(f'{mia.amount_total:,.2f}', de_ana['total'])
        de_luis = self.resumen(self.luis)
        self.assertEqual(de_luis['ventas'], 1)
        self.assertEqual([v['vendedor'] for v in de_luis['por_vendedor']], [self.luis.name])
        todas = self.resumen(self.gerente)
        nombres = {v['vendedor'] for v in todas['por_vendedor']}
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
