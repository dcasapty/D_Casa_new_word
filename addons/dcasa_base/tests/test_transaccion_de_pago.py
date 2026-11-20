"""R7-1 (revisión RV7): la transacción de un pago en línea la mueve el sistema o Caja, nunca la Vendedora.

El permiso de fábrica de Odoo deja a Facturación (que la Vendedora trae implícita) leer, escribir y crear
``payment.transaction``. Con un ``write(state='done')`` la Vendedora dejaba una transacción de Yappy (o de cualquier
proveedor) «hecha»: el cron confirmaba el pedido y creaba el cobro en el diario, sin dinero y sin pasar por Caja (A5).
``models/cobros.py`` ahora le niega el estado, el monto, el entorno, el proveedor, el cobro, los pedidos y facturas
ligados y todo campo ``dcasa_*`` a quien no cobra. Lo que escribe el propio sistema (la pasarela, el aviso del
proveedor, el cron: todo con ``sudo`` o como superusuario) no cambia. Datos inventados; ninguna prueba toca la red.
"""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.cobros import CAMPOS_DEL_DINERO_DE_UNA_TRANSACCION
from .test_roles import crear_usuario

QUIEN_COBRA = {
    'caja': 'dcasa_base.group_caja',
    'gerencia': 'dcasa_base.group_gerencia',
    'contabilidad': 'account.group_account_user',
    'administrador': 'base.group_system',
}
QUIEN_NO_COBRA = {
    'vendedora': 'dcasa_base.group_vendedora',
    'facturacion': 'account.group_account_invoice',
}


@tagged('post_install', '-at_install')
class TestLaTransaccionDePagoNoLaTocaQuienNoCobra(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.usuarios = {
            nombre: crear_usuario(env, f'r71_{nombre}', grupo)
            for nombre, grupo in {**QUIEN_COBRA, **QUIEN_NO_COBRA}.items()}
        cls.cliente = env['res.partner'].create({
            'name': 'Cliente de prueba R7-1', 'phone': '+507 6000-0071', 'email': 'cliente.r71@example.com'})
        cls.producto = env['product.product'].create({'name': 'Mueble de prueba R7-1', 'list_price': 50.0})
        # Un proveedor cualquiera (la regla es general: no depende de Yappy ni de Tilopay).
        cls.proveedor = env['payment.provider'].create({'name': 'Proveedor de prueba R7-1', 'code': 'none'})
        cls.metodo = env.ref('payment.payment_method_card')

    def pedido_con_transaccion(self):
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        tx = self.env['payment.transaction'].create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': pedido.amount_total,
            'currency_id': pedido.currency_id.id, 'partner_id': self.cliente.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(pedido.ids)]})
        tx._set_pending()
        return pedido, tx

    def test_la_vendedora_no_deja_pagado_un_pedido_con_un_write(self):
        """La prueba del revisor (RV7 a12): ``write(state='done')`` y después el cron = pedido confirmado y cobro creado
        sin dinero. Ahora el write se niega y la transacción sigue como estaba (el cron no tiene nada que cerrar; la
        cadena completa con Yappy está en ``dcasa_pago_yappy/tests/test_rv7.py``)."""
        pedido, tx = self.pedido_con_transaccion()
        with self.assertRaises(AccessError):
            tx.with_user(self.usuarios['vendedora']).write({'state': 'done'})
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'pending')
        self.assertFalse(tx.payment_id, 'no hay cobro contable')
        self.assertEqual(pedido.state, 'draft', 'el pedido no se confirmó')

    def test_quien_no_cobra_no_escribe_ningun_campo_del_dinero(self):
        pedido, tx = self.pedido_con_transaccion()
        valores = {
            'state': 'done', 'amount': 0.01, 'currency_id': self.env.ref('base.EUR').id, 'is_live': True,
            'provider_id': self.proveedor.id, 'provider_reference': 'OTRA', 'reference': 'OTRA-REF',
            'operation': 'online_redirect', 'payment_id': False, 'is_post_processed': True,
            'sale_order_ids': [Command.clear()], 'invoice_ids': [Command.clear()], 'source_transaction_id': False}
        self.assertEqual(
            set(valores), set(CAMPOS_DEL_DINERO_DE_UNA_TRANSACCION), 'la prueba cubre cada campo de la lista')
        for nombre, usuario in ((n, self.usuarios[n]) for n in QUIEN_NO_COBRA):
            for campo, valor in valores.items():
                with self.subTest(usuario=nombre, campo=campo), self.assertRaises(AccessError):
                    tx.with_user(usuario).write({campo: valor})
        tx.invalidate_recordset()
        self.assertEqual((tx.state, tx.amount, tx.sale_order_ids), ('pending', pedido.amount_total, pedido))

    def test_ningun_campo_dcasa_de_la_transaccion_lo_escribe_quien_no_cobra(self):
        """Los campos de Yappy, de Tilopay y los que vengan (``dcasa_*``) son del sistema, de cualquier proveedor."""
        _pedido, tx = self.pedido_con_transaccion()
        for campo in ('dcasa_yappy_revision', 'dcasa_yappy_orden', 'dcasa_tilopay_veredicto', 'dcasa_lo_que_venga'):
            with self.subTest(campo=campo), self.assertRaises(AccessError):
                tx.with_user(self.usuarios['vendedora']).write({campo: 'x'})

    def test_un_write_que_mezcla_un_campo_permitido_con_uno_del_dinero_tambien_se_niega(self):
        _pedido, tx = self.pedido_con_transaccion()
        with self.assertRaises(AccessError):
            tx.with_user(self.usuarios['vendedora']).write({'state_message': 'hola', 'state': 'done'})
        tx.invalidate_recordset()
        self.assertFalse(tx.state_message)

    def test_caja_gerencia_contabilidad_y_el_administrador_siguen_escribiendo(self):
        for nombre in QUIEN_COBRA:
            with self.subTest(usuario=nombre):
                _pedido, tx = self.pedido_con_transaccion()
                tx.with_user(self.usuarios[nombre]).write({'amount': 12.5, 'is_live': True})
                self.assertEqual((tx.amount, tx.is_live), (12.5, True))

    def test_lo_que_escribe_el_sistema_con_sudo_o_como_superusuario_no_se_rompe(self):
        """La pasarela (controlador con ``sudo``), el aviso del proveedor y el cron no pasan por la regla."""
        pedido, tx = self.pedido_con_transaccion()
        tx.sudo()._set_done()
        self.assertEqual(tx.state, 'done')
        tx.sudo().write({'amount': pedido.amount_total, 'is_post_processed': False})
        tx.with_user(self.env.ref('base.user_root')).write({'is_post_processed': True})
        self.assertTrue(tx.is_post_processed)
        # una Vendedora que dispara el flujo por un camino del sistema (sudo) tampoco se bloquea
        _pedido2, tx2 = self.pedido_con_transaccion()
        tx2.with_user(self.usuarios['vendedora']).sudo()._set_done()
        self.assertEqual(tx2.state, 'done')

    def test_el_portal_y_el_publico_tampoco_escriben(self):
        _pedido, tx = self.pedido_con_transaccion()
        portal = new_test_user(self.env, login='r71_portal', groups='base.group_portal')
        for usuario in (portal, self.env.ref('base.public_user')):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                tx.with_user(usuario).write({'state': 'done'})

    def test_la_vendedora_sigue_leyendo_sus_transacciones(self):
        """Solo se cierra la escritura del dinero: leer no cambia (la pantalla del pedido muestra «Cómo pagó»)."""
        _pedido, tx = self.pedido_con_transaccion()
        lectura = tx.with_user(self.usuarios['vendedora']).read(['state', 'amount', 'provider_id'])
        self.assertEqual(lectura[0]['state'], 'pending')

    def test_la_vendedora_no_crea_una_transaccion_ya_hecha(self):
        """El hueco gemelo (crear en vez de escribir) ya estaba cerrado por los permisos del proveedor: se fija aquí
        para que un cambio futuro no lo reabra."""
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        with self.assertRaises(AccessError):
            self.env['payment.transaction'].with_user(self.usuarios['vendedora']).create({
                'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id,
                'amount': pedido.amount_total, 'currency_id': pedido.currency_id.id,
                'partner_id': self.cliente.id, 'operation': 'online_direct',
                'sale_order_ids': [Command.set(pedido.ids)], 'state': 'done'})
