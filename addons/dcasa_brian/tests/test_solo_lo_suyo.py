"""Brian con «Cada vendedora ve solo sus documentos» (pedido de la dueña, 2026-10-16 y 2026-10-17).

Brian corre como quien le habla, sin sudo en ventas ni facturas: a la Vendedora A no le encuentra la venta ni la
factura de la Vendedora B, y cuando le da cifras de facturas le dice que son solo las suyas (``alcance``). Los roles
de D'CASA (Vendedora, Caja, Gerencia) se llaman por su nombre, y pasar de Caja a Vendedora le quita «ver todo».
Gerencia o un administrador mueven el interruptor también desde Brian.
"""
from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

TODOS = 'sales_team.group_sale_salesman_all_leads'


@tagged('post_install', '-at_install')
class TestBrianSoloLoSuyo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, *grupos):
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login, 'group_ids': [
                Command.set([cls.env.ref(g).id for g in ('base.group_user', *grupos)])]})

        cls.a = usuario('brian_sls_a', 'dcasa_base.group_vendedora')
        cls.b = usuario('brian_sls_b', 'dcasa_base.group_vendedora')
        cls.caja = usuario('brian_sls_caja', 'dcasa_base.group_caja')
        cls.gerencia = usuario('brian_sls_gerencia', 'dcasa_base.group_gerencia')
        cls.jefe = usuario('brian_sls_jefe', 'base.group_system', 'dcasa_base.group_gerencia')
        cls.cliente = cls.env['res.partner'].create({'name': 'Brianzeta Cliente Solo Lo Suyo'})
        producto = cls.env['product.product'].create({'name': 'Brianzeta Silla Sls', 'list_price': 80.0})
        cls.pedido_b = cls.env['sale.order'].create({
            'partner_id': cls.cliente.id, 'user_id': cls.b.id,
            'order_line': [Command.create({'product_id': producto.id, 'product_uom_qty': 1})]})
        cls.pedido_b.action_confirm()
        cls.factura_b = cls.pedido_b._create_invoices()
        cls.factura_b.action_post()

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def confirmar(self, usuario, respuesta):
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        return self.env['brian.herramientas'].with_user(usuario).confirmar(respuesta['accion_id'])

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def test_los_roles_de_dcasa_por_su_nombre(self):
        Herramientas = self.env['brian.herramientas']
        self.assertEqual(Herramientas._b_rol(self.a), 'Vendedor/a')
        self.assertEqual(Herramientas._b_rol(self.caja), 'Caja')
        self.assertEqual(Herramientas._b_rol(self.gerencia), 'Gerencia')

    def test_de_vendedora_a_caja_y_de_vuelta_sin_ver_todo(self):
        persona = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Brianzeta Rotación', 'login': 'brian_sls_rotacion', 'group_ids': [Command.set([
                self.env.ref('base.group_user').id, self.env.ref('dcasa_base.group_vendedora').id])]})
        todos = self.env.ref(TODOS)
        self.ok(self.confirmar(self.jefe, self.ejecutar(self.jefe, 'cambiar_rol_usuario',
                                                        {'usuario': persona.login, 'rol': 'cajero'})))
        self.assertTrue(persona.has_group('dcasa_base.group_caja'))
        self.assertIn(todos, persona.all_group_ids)
        self.assertEqual(self.env['brian.herramientas']._b_rol(persona), 'Caja')
        self.ok(self.confirmar(self.jefe, self.ejecutar(self.jefe, 'cambiar_rol_usuario',
                                                        {'usuario': persona.login, 'rol': 'vendedor'})))
        self.assertFalse(persona.has_group('dcasa_base.group_caja'))
        self.assertNotIn(todos, persona.all_group_ids, 'de vuelta a Vendedora no se queda viendo todo')
        self.assertTrue(persona._dcasa_solo_lo_suyo())
        self.assertEqual(self.env['brian.herramientas']._b_rol(persona), 'Vendedor/a')

    def test_gerencia_solo_la_da_un_administrador_del_sistema(self):
        gestor = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Brianzeta Gestor', 'login': 'brian_sls_gestor', 'group_ids': [Command.set([
                self.env.ref('base.group_user').id, self.env.ref('base.group_erp_manager').id])]})
        respuesta = self.ejecutar(gestor, 'cambiar_rol_usuario', {'usuario': self.a.login, 'rol': 'gerencia'})
        self.assertFalse(respuesta['ok'])
        self.assertFalse(respuesta.get('requiere_confirmacion'))
        self.assertFalse(self.a.has_group('dcasa_base.group_gerencia'))

    def test_a_no_encuentra_la_venta_ni_la_factura_de_b(self):
        for nombre, argumentos in (('ver_venta', {'venta': self.pedido_b.name}),
                                   ('ver_factura', {'factura': self.factura_b.name})):
            with self.subTest(nombre):
                respuesta = self.ejecutar(self.a, nombre, argumentos)
                self.assertFalse(respuesta['ok'], respuesta)
                self.assertNotIn(str(self.factura_b.amount_total), str(respuesta))
                self.ok(self.ejecutar(self.b, nombre, argumentos))
                self.ok(self.ejecutar(self.caja, nombre, argumentos))

    def test_las_cifras_de_facturas_dicen_que_son_solo_las_suyas(self):
        deben = self.ok(self.ejecutar(self.a, 'clientes_que_deben', {'solo_vencido': False}))
        self.assertIn('solo tus facturas', deben['alcance'])
        self.assertNotIn(self.cliente.display_name, [c['cliente'] for c in deben['clientes']])
        pendientes = self.ok(self.ejecutar(self.a, 'facturas_pendientes', {}))
        self.assertIn('alcance', pendientes)
        self.assertNotIn(self.factura_b.name, str(pendientes))
        de_caja = self.ok(self.ejecutar(self.caja, 'clientes_que_deben', {'solo_vencido': False}))
        self.assertNotIn('alcance', de_caja)
        self.assertIn(self.cliente.display_name, [c['cliente'] for c in de_caja['clientes']])

    def test_gerencia_mueve_el_interruptor_desde_brian(self):
        Users = self.env['res.users']
        self.assertTrue(self.ok(self.ejecutar(self.jefe, 'listar_usuarios'))['cada_vendedora_ve_solo_lo_suyo'])
        datos = self.ok(self.confirmar(self.gerencia, self.ejecutar(
            self.gerencia, 'cambiar_restriccion_vendedoras', {'encender': False})))
        self.assertFalse(datos['cada_vendedora_ve_solo_lo_suyo'])
        self.assertFalse(Users._dcasa_restriccion_activa())
        self.ok(self.ejecutar(self.a, 'ver_factura', {'factura': self.factura_b.name}))
        self.ok(self.confirmar(self.gerencia, self.ejecutar(
            self.gerencia, 'cambiar_restriccion_vendedoras', {'encender': True})))
        self.assertTrue(Users._dcasa_restriccion_activa())
        self.assertFalse(self.ejecutar(self.a, 'ver_factura', {'factura': self.factura_b.name})['ok'])

    def test_vendedora_y_caja_no_mueven_el_interruptor(self):
        for usuario in (self.a, self.caja):
            with self.subTest(usuario.login):
                respuesta = self.ejecutar(usuario, 'cambiar_restriccion_vendedoras', {'encender': False})
                self.assertFalse(respuesta['ok'])
                self.assertFalse(respuesta.get('requiere_confirmacion'))
        self.assertTrue(self.env['res.users']._dcasa_restriccion_activa())
