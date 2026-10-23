"""Brian y Compras › Reponer: ``que_reponer`` (ritmo, alcanza para, tarda en llegar, pedir y pedir ya, lo mismo que la
pantalla) y ``poner_tiempo_llegada``. Solo Gerencia y administradores."""
from datetime import timedelta

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestQueReponer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def usuario(login, grupo):
            return cls.env['res.users'].create({
                'name': login, 'login': login, 'tz': 'America/Panama',
                'group_ids': [Command.set([cls.env.ref('base.group_user').id, cls.env.ref(grupo).id])]})
        cls.gerencia = usuario('brian_reponer_gerencia', 'dcasa_base.group_gerencia')
        cls.vendedora = usuario('brian_reponer_vendedora', 'dcasa_base.group_vendedora')
        cls.proveedor = cls.env['res.partner'].create({'name': 'PROVEEDOR DE PRUEBA Brian Reponer',
                                                       'supplier_rank': 1})
        cls.colchon = cls.env['product.product'].create({
            'name': 'Colchón Brian reponer', 'default_code': 'BR-REP-1', 'is_storable': True, 'list_price': 300.0,
            'taxes_id': [Command.clear()],
            'seller_ids': [Command.create({'partner_id': cls.proveedor.id, 'price': 150.0})]})
        hoy = cls.env['dcasa.reponer'].with_user(cls.gerencia)._ventana(5)[1]
        factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'invoice_date': hoy - timedelta(days=10),
            'partner_id': cls.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA Brian reponer'}).id,
            'invoice_line_ids': [Command.create({'product_id': cls.colchon.id, 'quantity': 10, 'price_unit': 300.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()

    def ejecutar(self, usuario, herramienta, argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(herramienta, argumentos)

    def test_devuelve_lo_mismo_que_la_pantalla(self):
        respuesta = self.ejecutar(self.gerencia, 'que_reponer', {'proveedor': 'PROVEEDOR DE PRUEBA Brian Reponer'})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        pantalla = self.env['dcasa.reponer'].with_user(self.gerencia)._calcular(5, 0, self.proveedor)
        self.assertEqual(datos['productos_vendidos'], len(pantalla))
        self.assertIn('(5 meses)', datos['ventana'])
        colchon = datos['productos'][0]
        self.assertEqual(
            (colchon['codigo'], colchon['vendido'], colchon['se_vende_al_mes'], colchon['disponible_hoy'],
             colchon['viene_en_camino'], colchon['tarda_en_llegar'], colchon['pedir'], colchon['pedir_ya']),
            ('BR-REP-1', 10, 2, 0, 0, 'Falta', 'no se calcula: falta el tiempo de llegada', False),
            'sin el tiempo de llegada no inventa cuánto pedir')
        self.assertEqual(datos['sin_tiempo_de_llegada'], 1)

    def test_pone_el_tiempo_de_llegada_y_ya_calcula_cuanto_pedir(self):
        respuesta = self.ejecutar(self.gerencia, 'poner_tiempo_llegada',
                                  {'proveedor': 'PROVEEDOR DE PRUEBA Brian Reponer', 'meses': 3})
        self.assertTrue(respuesta['ok'], respuesta)
        self.assertEqual((respuesta['datos']['dias'], respuesta['datos']['tarda_en_llegar']), (90, '3 meses'))
        self.assertEqual(self.colchon.seller_ids.delay, 90)
        self.assertTrue(self.colchon.seller_ids.dcasa_llegada_puesta)
        datos = self.ejecutar(self.gerencia, 'que_reponer',
                              {'proveedor': 'PROVEEDOR DE PRUEBA Brian Reponer', 'meses': 5, 'reserva': 1})['datos']
        colchon = datos['productos'][0]
        self.assertEqual((colchon['tarda_en_llegar'], colchon['pedir'], colchon['pedir_ya'], colchon['aviso']),
                         ('3 meses', 8, True, 'Pedir ya'), '2 al mes × (3 + 1) − 0 − 0')
        self.assertEqual((datos['pedir_ya'], datos['unidades_a_pedir'], datos['reserva_meses']), (1, 8, 1))
        # En días; y sin decir cuánto, o con un tiempo imposible, no cambia nada.
        self.assertTrue(self.ejecutar(self.gerencia, 'poner_tiempo_llegada',
                                      {'proveedor': 'PROVEEDOR DE PRUEBA Brian Reponer', 'dias': 100})['ok'])
        self.assertEqual(self.colchon.seller_ids.delay, 100)
        for argumentos in ({}, {'dias': 0}, {'meses': 30}, {'dias': 10, 'meses': 1}):
            with self.subTest(argumentos):
                respuesta = self.ejecutar(self.gerencia, 'poner_tiempo_llegada',
                                          dict(argumentos, proveedor='PROVEEDOR DE PRUEBA Brian Reponer'))
                self.assertFalse(respuesta['ok'], respuesta)
        self.assertEqual(self.colchon.seller_ids.delay, 100)

    def test_solo_gerencia_y_administradores(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertNotIn('que_reponer', nombres)
        self.assertNotIn('poner_tiempo_llegada', nombres)
        self.assertFalse(self.ejecutar(self.vendedora, 'que_reponer', {})['ok'])
        self.assertFalse(self.ejecutar(self.vendedora, 'poner_tiempo_llegada',
                                       {'proveedor': 'PROVEEDOR DE PRUEBA Brian Reponer', 'meses': 3})['ok'])
        self.assertEqual(self.colchon.seller_ids.delay, 1, 'la vendedora no cambió nada')
        todas = self.env['brian.herramientas']._todas()
        self.assertEqual((todas['que_reponer']['nivel'], todas['poner_tiempo_llegada']['nivel']),
                         ('lectura', 'construccion'))
