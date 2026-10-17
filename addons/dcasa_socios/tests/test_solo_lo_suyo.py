"""Socios y vendedores con «Cada vendedora ve solo sus documentos» (pedido de la dueña, 2026-10-16).

Las compras que dieron puntos y las comisiones dicen de qué factura vienen y cuánto se vendió: la Vendedora A no ve
las de la Vendedora B; B sí ve las suyas; Caja y Gerencia, todas. Los saldos y los procesos corren con sudo: A le
cobra igual un premio a un socio que compró con B. Apagado el interruptor, A vuelve a ver todo, como antes.
Reglas: security/dcasa_reglas_socios.xml.
"""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_vendedores import VendedoresCommon


@tagged('post_install', '-at_install')
class TestSociosSoloLoSuyo(VendedoresCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupo):
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login, 'group_ids': [
                Command.set([cls.env.ref('base.group_user').id, cls.env.ref(grupo).id])]})

        cls.a = usuario('socios_sls_a', 'dcasa_base.group_vendedora')
        cls.b = usuario('socios_sls_b', 'dcasa_base.group_vendedora')
        cls.caja = usuario('socios_sls_caja', 'dcasa_base.group_caja')
        cls.gerencia = usuario('socios_sls_gerencia', 'dcasa_base.group_gerencia')

    def _cerrado(self, registros, usuario):
        self.assertTrue(registros)
        Modelo = registros.browse().with_user(usuario)
        dominio = [('id', 'in', registros.ids)]
        self.assertFalse(Modelo.search(dominio))
        self.assertEqual(Modelo.search_count(dominio), 0)
        self.assertEqual(Modelo._read_group(dominio, [], ['__count']), [(0,)])
        with self.assertRaises(AccessError):
            registros.with_user(usuario).read(['display_name'])

    def _visible(self, registros, usuario):
        self.assertEqual(registros.browse().with_user(usuario).search([('id', 'in', registros.ids)]), registros,
                         usuario.login)

    def test_la_compra_y_la_comision_de_b_no_las_ve_a(self):
        factura = self.factura(vendedor=self.ana, vendedora=self.b)
        compra = factura.dcasa_compra_ids
        comision = factura.dcasa_vend_comision_ids
        self.assertEqual(compra.vendedor_id, self.b)
        self.assertTrue(comision, 'la venta con código da comisión')
        self._cerrado(compra, self.a)
        self._cerrado(comision, self.a)
        for usuario in (self.b, self.caja, self.gerencia):
            with self.subTest(usuario.login):
                self._visible(compra, usuario)
                self._visible(comision, usuario)

    def test_a_cobra_un_premio_a_un_socio_que_compro_con_b(self):
        compra = self.factura(partner=self.padrino, precio=300.0, vendedora=self.b).dcasa_compra_ids
        self.assertEqual(compra.vendedor_id, self.b)
        self._cerrado(compra, self.a)
        self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_10'))
        orden = self.env['sale.order'].with_user(self.a).create({
            'partner_id': self.padrino.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})],
        })
        self.env['dcasa.cobrar.premio.wizard'].with_user(self.a).create({
            'order_id': orden.id, 'codigo': canje.codigo}).action_confirmar()
        self.assertTrue(orden.order_line.filtered('dcasa_canje_id'))
        self.assertEqual(orden.user_id, self.a)

    def test_con_el_interruptor_apagado_a_ve_todo_como_antes(self):
        factura = self.factura(vendedor=self.ana, vendedora=self.b)
        self.env['res.users']._dcasa_poner_restriccion(False)
        self._visible(factura.dcasa_compra_ids, self.a)
        self._visible(factura.dcasa_vend_comision_ids, self.a)
        self.env['res.users']._dcasa_poner_restriccion(True)
        self._cerrado(factura.dcasa_compra_ids, self.a)
