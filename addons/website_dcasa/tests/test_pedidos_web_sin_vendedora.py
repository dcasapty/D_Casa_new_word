"""Los pedidos de la página web entran SIN vendedora (decisión de la dueña, 2026-10-17; models/pedido_web.py).

Con «Cada vendedora ve solo sus documentos» encendido, un pedido web nuevo lo ven todas; la vendedora que lo confirma
se lo queda. Caja o Gerencia lo confirman y sigue sin vendedora. La tienda sola (pago en línea, sudo) no le pone
vendedora, aunque la ficha del cliente diga una. El vendedor del programa (link /v/CÓDIGO) no se toca.
"""
import importlib.util
from contextlib import contextmanager

from odoo import Command
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path


@contextmanager
def negado(prueba, excepcion, texto):
    """``assertRaisesRegex`` con el savepoint de Odoo (``assertRaises``): lo que se escribió antes del error se deshace,
    como en una llamada real."""
    with prueba.assertRaises(excepcion) as contexto:
        yield contexto
    prueba.assertRegex(str(contexto.exception), texto)


@tagged('post_install', '-at_install')
class TestPedidosWebSinVendedora(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.website = env.ref('website.default_website')
        cls.a = crear_usuario(env, 'web_vendedora_a', 'dcasa_base.group_vendedora')
        cls.b = crear_usuario(env, 'web_vendedora_b', 'dcasa_base.group_vendedora')
        cls.caja = crear_usuario(env, 'web_caja', 'dcasa_base.group_caja')
        cls.cliente = env['res.partner'].create({
            'name': 'Cliente de la web', 'phone': '+507 6555-0601', 'email': 'cliente.web@example.com'})
        cls.cliente_de_b = env['res.partner'].create({
            'name': 'Cliente web con ficha de B', 'phone': '+507 6555-0602', 'email': 'ficha.b@example.com',
            'user_id': cls.b.id})
        cls.programa = env['res.partner'].create({'name': 'Vendedor del programa (link /v/)'})
        cls.producto = env['product.product'].create({
            'name': 'Mesa de la web', 'type': 'consu', 'list_price': 100.0, 'taxes_id': [Command.clear()]})

    def _pedido_web(self, cliente=None, **valores):
        """Como lo arma la tienda: con sudo, del sitio web, sin tocar la vendedora."""
        return self.env['sale.order'].sudo().create({
            'partner_id': (cliente or self.cliente).id, 'website_id': self.website.id, **valores,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})

    def _ve(self, usuario, pedido):
        return bool(self.env['sale.order'].with_user(usuario).search([('id', '=', pedido.id)]))

    def test_el_sitio_no_trae_vendedor(self):
        self.assertFalse(self.website.salesperson_id)
        self.assertTrue(self.env['res.users']._dcasa_restriccion_activa(), 'el interruptor viene encendido')

    def test_un_pedido_web_nuevo_lo_ven_todas_y_quien_confirma_se_lo_queda(self):
        pedido = self._pedido_web(dcasa_vendedor_id=self.programa.id)
        pedido.action_quotation_sent()   # pago pendiente (transferencia, Yappy, en la tienda)
        self.assertFalse(pedido.user_id)
        for usuario in (self.a, self.b, self.caja):
            self.assertTrue(self._ve(usuario, pedido), usuario.login)
        pedido.with_user(self.a).action_confirm()
        self.assertEqual(pedido.user_id, self.a, 'la que lo confirma se lo queda')
        self.assertTrue(self._ve(self.a, pedido))
        self.assertFalse(self._ve(self.b, pedido), 'ya es de A')
        with self.assertRaises(AccessError):
            pedido.with_user(self.b).read(['name'])
        # El vendedor del programa (link /v/CÓDIGO) sigue igual y pasa a la factura (su comisión).
        self.assertEqual(pedido.dcasa_vendedor_id, self.programa)
        factura = pedido.with_user(self.a)._create_invoices()
        self.assertEqual((factura.invoice_user_id, factura.dcasa_vendedor_id), (self.a, self.programa))

    def test_la_ficha_del_cliente_no_le_pone_vendedora(self):
        pedido = self._pedido_web(cliente=self.cliente_de_b)
        pedido.action_confirm()   # la tienda sola (pago en línea o al recibir), como superusuario
        self.assertFalse(pedido.user_id, 'aunque la ficha diga B, el pedido web entra sin vendedora')
        self.assertTrue(self._ve(self.a, pedido))
        pedido.with_context(force_user_recomputation=True)._compute_user_id()
        self.assertFalse(pedido.user_id)

    def test_si_lo_confirma_caja_sigue_sin_vendedora(self):
        pedido = self._pedido_web()
        pedido.action_quotation_sent()
        pedido.with_user(self.caja).action_confirm()
        self.assertFalse(pedido.user_id)
        for usuario in (self.a, self.b):
            self.assertTrue(self._ve(usuario, pedido), usuario.login)

    def test_con_el_interruptor_apagado_tambien_se_lo_queda_quien_confirma(self):
        self.env['res.users']._dcasa_poner_restriccion(False)
        pedido = self._pedido_web()
        pedido.action_quotation_sent()
        pedido.with_user(self.b).action_confirm()
        self.assertEqual(pedido.user_id, self.b)

    def test_un_vendedor_del_sitio_puesto_a_mano_se_respeta(self):
        self.website.salesperson_id = self.b
        pedido = self._pedido_web()
        pedido.action_confirm()
        self.assertEqual(pedido.user_id, self.b, 'si un administrador lo pone, Odoo vuelve a usarlo')

    def test_la_vendedora_factura_un_pedido_ya_pagado_en_linea(self):
        """Al publicar la factura de un pedido pagado en la web, Odoo cruza solo ese pago con la factura (sale
        ``_post``): eso no es «registrar un cobro» y la vendedora sigue pudiendo facturar. (Con el interruptor
        apagado: encendido, la vendedora no ve ese pago, la factura se publica por cobrar y Caja le aplica el cobro;
        ver docs/PERMISOS.md.)"""
        self.env['res.users']._dcasa_poner_restriccion(False)
        pedido = self._pedido_web()
        pedido.action_quotation_sent()
        proveedor = self.env['payment.provider'].search([('code', '=', 'custom')], limit=1)
        transaccion = self.env['payment.transaction'].create({
            'provider_id': proveedor.id, 'payment_method_id': proveedor.payment_method_ids[:1].id,
            'amount': pedido.amount_total, 'currency_id': pedido.currency_id.id, 'partner_id': self.cliente.id,
            'reference': 'PRUEBA-WEB-PAGADO', 'sale_order_ids': [Command.set(pedido.ids)]})
        banco = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
        pago = self.env['account.payment'].create({   # lo que hace la tienda sola (sudo) con el pago en línea
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
            'amount': pedido.amount_total, 'journal_id': banco.id})
        pago.action_post()
        transaccion.write({'state': 'done', 'payment_id': pago.id})   # pagado en línea (lo hace la tienda sola)
        pedido.with_user(self.a).action_confirm()
        factura = pedido.with_user(self.a)._create_invoices()
        self.assertIn(transaccion, factura.transaction_ids)
        factura.with_user(self.a).action_post()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        # Pero cruzar a mano un cobro que no es de esa transacción sigue siendo de Caja.
        otro = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
            'amount': 10.0, 'journal_id': banco.id})
        otro.action_post()
        segundo = self._pedido_web()
        segundo.with_user(self.a).action_confirm()
        factura_2 = segundo.with_user(self.a)._create_invoices()
        factura_2.with_user(self.a).action_post()
        linea = otro.move_id.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        with negado(self, AccessError, 'Los cobros los registra Caja'):
            factura_2.with_user(self.a).js_assign_outstanding_line(linea.id)

    def test_la_migracion_vacia_el_vendedor_del_sitio(self):
        self.website.salesperson_id = self.env.ref('base.user_admin')
        spec = importlib.util.spec_from_file_location(
            'mig_pedidos_web', file_path('website_dcasa/migrations/19.0.1.15.0/post-migrate.py'))
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        migracion.migrate(self.env.cr, '19.0.1.14.0')
        self.assertFalse(self.website.salesperson_id)
        pedido = self._pedido_web()
        pedido.action_confirm()
        self.assertFalse(pedido.user_id)
