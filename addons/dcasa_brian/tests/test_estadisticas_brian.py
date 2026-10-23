"""Brian «ventas_por_dia» y «movimientos_de_producto»: lo mismo que Por día y Movimientos (2026-10-22)."""
from datetime import date

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEstadisticasBrian(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def usuario(login, grupo):
            return cls.env['res.users'].create({
                'name': login.replace('_', ' ').title(), 'login': login, 'tz': 'America/Panama',
                'group_ids': [Command.set([cls.env.ref('base.group_user').id, cls.env.ref(grupo).id])]})
        cls.gerencia = usuario('brian_dia_gerencia', 'dcasa_base.group_gerencia')
        cls.vendedora = usuario('brian_dia_vendedora', 'dcasa_base.group_vendedora')
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA BRIAN DIA'})
        cls.mesa = cls.env['product.product'].create({
            'name': 'Mesa Brian por día', 'default_code': 'BR-DIA-1', 'is_storable': True, 'list_price': 400.0,
            'taxes_id': [Command.clear()]})
        cls.hoy = cls.env['dcasa.tablero']._ahora_en_panama().date()
        cls.factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.cliente.id, 'invoice_date': cls.hoy,
            'invoice_user_id': cls.vendedora.id,
            'invoice_line_ids': [Command.create({'product_id': cls.mesa.id, 'quantity': 1, 'price_unit': 400.0})]})
        cls.factura.action_post()
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': cls.mesa.id, 'location_id': almacen.lot_stock_id.id, 'inventory_quantity': 3,
        }).action_apply_inventory()

    def ejecutar(self, usuario, nombre, argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos)

    def test_el_dia_dicho_como_lo_dice_la_gente(self):
        Brian = self.env['brian.herramientas']
        jueves = date(2026, 10, 22)
        self.assertEqual(Brian._b_dia_dicho('el martes', jueves), date(2026, 10, 20))
        self.assertEqual(Brian._b_dia_dicho('el jueves', jueves), jueves, 'el de hoy, si hoy es jueves')
        self.assertEqual(Brian._b_dia_dicho('el jueves pasado', jueves), date(2026, 10, 15))
        self.assertEqual(Brian._b_dia_dicho('miércoles', jueves), date(2026, 10, 21))
        self.assertEqual(Brian._b_dia_dicho('ayer', jueves), date(2026, 10, 21))
        self.assertEqual(Brian._b_dia_dicho('20/10/2026', jueves), date(2026, 10, 20))
        self.assertEqual(Brian._b_mes_dicho('', jueves), '2026-10')
        self.assertEqual(Brian._b_mes_dicho('mes pasado', jueves), '2026-09')
        self.assertEqual(Brian._b_mes_dicho('octubre', jueves), '2026-10', 'el mes en curso, no el del año pasado')
        self.assertEqual(Brian._b_mes_dicho('noviembre', jueves), '2025-11')
        self.assertEqual(Brian._b_mes_dicho('09/2026', jueves), '2026-09')

    def test_un_dia_dice_lo_mismo_que_la_pantalla(self):
        respuesta = self.ejecutar(self.gerencia, 'ventas_por_dia', {'dia': 'hoy', 'vendedora': self.vendedora.name})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        pantalla = self.env['dcasa.tablero'].with_user(self.gerencia).ventas_del_dia(
            str(self.hoy), vendedor=self.vendedora.id)
        self.assertEqual(datos['ventas_sin_itbms'], '$400.00')
        self.assertEqual(datos['facturas'], pantalla['total']['cuantas'])
        self.assertEqual([d['numero'] for d in datos['documentos']], [self.factura.name])
        self.assertEqual(datos['documentos'][0]['cliente'], 'CLIENTE DE PRUEBA BRIAN DIA')
        self.assertTrue(datos['cuenta'].startswith('Facturado'))

    def test_el_mes_dia_por_dia(self):
        respuesta = self.ejecutar(self.gerencia, 'ventas_por_dia', {'vendedora': self.vendedora.name})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        self.assertEqual(datos['total_sin_itbms'], '$400.00')
        self.assertEqual(len(datos['dias']), 1, 'solo los días con ventas')
        self.assertIn(self.hoy.strftime('%d/%m/%Y'), datos['dias'][0]['dia'])
        self.assertIn('contra', datos)
        confirmado = self.ejecutar(self.gerencia, 'ventas_por_dia', {'base': 'confirmado',
                                                                   'vendedora': self.vendedora.name})
        self.assertTrue(confirmado['ok'], confirmado)
        self.assertEqual(confirmado['datos']['pedidos'], 0, 'una factura suelta no es un pedido confirmado')

    def test_completadas_dice_el_dia_que_se_termino_de_pagar(self):
        """La factura de hoy pagada hoy: en «completadas» cuenta hoy y la respuesta lo dice con esas palabras."""
        banco = self.env['account.journal'].create({'name': 'Banco Brian por día', 'type': 'bank', 'code': 'BBPD'})
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=self.factura.ids).create({
                'payment_date': self.hoy, 'amount': self.factura.amount_total, 'journal_id': banco.id,
            })._create_payments()
        respuesta = self.ejecutar(self.gerencia, 'ventas_por_dia', {'dia': 'hoy', 'base': 'completadas',
                                                                   'vendedora': self.vendedora.name})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        self.assertEqual(datos['cuenta'], 'Completadas: pagadas por completo, el día que se terminó de pagar')
        self.assertEqual(([d['numero'] for d in datos['documentos']], datos['ventas_sin_itbms']),
                         ([self.factura.name], '$400.00'))

    def test_movimientos_de_un_producto(self):
        respuesta = self.ejecutar(self.gerencia, 'movimientos_de_producto', {'producto': 'BR-DIA-1'})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        self.assertEqual(datos['hay_hoy'], 3)
        self.assertEqual(datos['movimientos'][0]['que'], 'Ajuste de inventario (+3)')
        self.assertEqual((datos['movimientos'][0]['cantidad'], datos['movimientos'][0]['quedan']), ('+3', 3))
        todos = self.ejecutar(self.gerencia, 'movimientos_de_producto', {'tipo': 'ajuste', 'limite': 3})
        self.assertTrue(todos['ok'], todos)
        self.assertLessEqual(len(todos['datos']['movimientos']), 3)
        self.assertTrue(all('producto' in fila for fila in todos['datos']['movimientos']))

    def test_solo_gerencia(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertNotIn('ventas_por_dia', nombres)
        self.assertNotIn('movimientos_de_producto', nombres)
        self.assertFalse(self.ejecutar(self.vendedora, 'ventas_por_dia', {})['ok'])
        self.assertFalse(self.ejecutar(self.vendedora, 'movimientos_de_producto', {'producto': 'BR-DIA-1'})['ok'])
        todas = self.env['brian.herramientas']._todas()
        self.assertEqual((todas['ventas_por_dia']['nivel'], todas['movimientos_de_producto']['nivel']),
                         ('lectura', 'lectura'))
