"""Brian «que_reponer»: lo mismo que Compras › Reponer, solo para Gerencia y administradores."""
from datetime import date

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
        cls.proveedor = cls.env['res.partner'].create({'name': 'Proveedor Brian Reponer'})
        cls.colchon = cls.env['product.product'].create({
            'name': 'Colchón Brian reponer', 'default_code': 'BR-REP-1', 'is_storable': True, 'list_price': 300.0,
            'taxes_id': [Command.clear()],
            'seller_ids': [Command.create({'partner_id': cls.proveedor.id, 'price': 150.0})]})
        factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.env['res.partner'].create({'name': 'Cliente BR'}).id,
            'invoice_date': date(2024, 4, 10), 'invoice_line_ids': [
                Command.create({'product_id': cls.colchon.id, 'quantity': 4, 'price_unit': 300.0})]})
        factura.action_post()

    def ejecutar(self, usuario, argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar('que_reponer', argumentos)

    def test_devuelve_lo_mismo_que_la_pantalla(self):
        respuesta = self.ejecutar(self.gerencia, {'proveedor': 'Proveedor Brian Reponer',
                                                  'desde': '01/04/2024', 'hasta': '30/04/2024'})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        pantalla = self.env['dcasa.reponer'].with_user(self.gerencia)._calcular(
            date(2024, 4, 1), date(2024, 4, 30), self.proveedor)
        self.assertEqual(datos['productos_vendidos'], len(pantalla))
        self.assertEqual(datos['productos'], [{
            'producto': fila['producto'], 'codigo': fila['referencia'], 'proveedor': fila['proveedor'],
            'vendido': fila['vendido'], 'en_existencia': fila['existencia'], 'pedido_sin_llegar': fila['pedido'],
            'faltaria': fila['faltaria']} for fila in pantalla])
        self.assertEqual((datos['productos'][0]['codigo'], datos['productos'][0]['faltaria']), ('BR-REP-1', 4))

    def test_solo_gerencia_y_administradores(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertNotIn('que_reponer', nombres)
        self.assertFalse(self.ejecutar(self.vendedora, {})['ok'])
        self.assertEqual(self.env['brian.herramientas']._todas()['que_reponer']['nivel'], 'lectura')
