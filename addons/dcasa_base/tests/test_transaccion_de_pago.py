"""R7-1, R8-1, R8-2 y R8-6 (revisiones RV7 y RV8): el pago en línea lo mueve el sistema o Caja, nunca la Vendedora.

El permiso de fábrica de Odoo deja a Facturación (que la Vendedora trae implícita) leer, escribir y crear
``payment.transaction``. Con un ``write(state='done')`` la Vendedora dejaba una transacción de Yappy (o de cualquier
proveedor) «hecha»: el cron confirmaba el pedido y creaba el cobro en el diario, sin dinero y sin pasar por Caja (A5).
``models/cobros.py`` cierra las dos mitades de esa relación:

* la transacción: quien no cobra no escribe NADA ni crea (lista blanca vacía: ningún flujo legítimo lo hace, todo lo del
  sistema corre con ``sudo``; una lista negra de campos dejaba abiertos ``partner_id``, ``landing_route``,
  ``state_message``…);
* el otro lado: ``sale.order.transaction_ids`` (``write`` y ``create``) y ``account.move.transaction_ids`` (``write``):
  ligar un cobro ajeno a un pedido o a una factura.

Lo que escribe el propio sistema (la pasarela, el aviso del proveedor, el cron, ``sale._create_invoices``) corre con
``sudo`` o como superusuario y no cambia. Datos inventados; ninguna prueba toca la red.

TRAMPA DE ESTAS PRUEBAS: antes de cada intento del usuario sin permiso se baja la caché (``flush_all`` +
``invalidate_all``). Con la caché «tibia» (el proveedor ya leído por otro usuario en la misma transacción) el ORM no
vuelve a revisar el permiso del comodelo y un ``create`` prohibido pasa por casualidad. ``assertRaises(AccessError)``
de Odoo ya limpia la caché por su cuenta; con ``try/except`` (o ``assertRaises(UserError)``) hay que hacerlo a mano.
"""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

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


class BaseTransaccion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.usuarios = {
            nombre: crear_usuario(env, f'r71_{nombre}', grupo)
            for nombre, grupo in {**QUIEN_COBRA, **QUIEN_NO_COBRA}.items()}
        cls.cliente = env['res.partner'].create({
            'name': 'Cliente de prueba R7-1', 'phone': '+507 6000-0071', 'email': 'cliente.r71@example.com'})
        cls.otro_cliente = env['res.partner'].create({
            'name': 'Otro cliente de prueba R8-1', 'phone': '+507 6000-0081', 'email': 'cliente.r81@example.com'})
        cls.producto = env['product.product'].create({'name': 'Mueble de prueba R7-1', 'list_price': 50.0})
        # Un proveedor cualquiera (la regla es general: no depende de Yappy ni de Tilopay).
        cls.proveedor = env['payment.provider'].create({'name': 'Proveedor de prueba R7-1', 'code': 'none'})
        cls.metodo = env.ref('payment.payment_method_card')

    def frio(self):
        """Baja la caché (ver la trampa en el encabezado)."""
        self.env.flush_all()
        self.env.invalidate_all()

    def pedido_de(self, cliente=None, vendedora=None):
        valores = {
            'partner_id': (cliente or self.cliente).id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]}
        if vendedora:
            valores['user_id'] = vendedora.id
        return self.env['sale.order'].create(valores)

    def transaccion_de(self, pedido, estado=None):
        tx = self.env['payment.transaction'].create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': pedido.amount_total,
            'currency_id': pedido.currency_id.id, 'partner_id': pedido.partner_id.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(pedido.ids)]})
        if estado == 'done':
            tx._set_done()
        else:
            tx._set_pending()
        return tx

    def pedido_con_transaccion(self):
        pedido = self.pedido_de()
        return pedido, self.transaccion_de(pedido)


@tagged('post_install', '-at_install')
class TestLaTransaccionDePagoNoLaTocaQuienNoCobra(BaseTransaccion):

    def test_la_vendedora_no_deja_pagado_un_pedido_con_un_write(self):
        """La prueba del revisor (RV7 a12): ``write(state='done')`` y después el cron = pedido confirmado y cobro creado
        sin dinero. Ahora el write se niega y la transacción sigue como estaba (el cron no tiene nada que cerrar; la
        cadena completa con Yappy está en ``dcasa_pago_yappy/tests/test_rv7.py``)."""
        pedido, tx = self.pedido_con_transaccion()
        self.frio()
        with self.assertRaises(AccessError):
            tx.with_user(self.usuarios['vendedora']).write({'state': 'done'})
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'pending')
        self.assertFalse(tx.payment_id, 'no hay cobro contable')
        self.assertEqual(pedido.state, 'draft', 'el pedido no se confirmó')

    def test_quien_no_cobra_no_escribe_ningun_campo(self):
        """R8-2: lista BLANCA vacía. Los de dinero (R7-1) y también los que la lista negra dejaba abiertos: a quién se
        le acredita el dinero, la ruta a la que se manda el navegador de la clienta (``javascript:…``), el mensaje
        que ella lee, la compañía, el método y el medio guardado."""
        pedido, tx = self.pedido_con_transaccion()
        valores = {
            'state': 'done', 'amount': 0.01, 'currency_id': self.env.ref('base.EUR').id, 'is_live': True,
            'provider_id': self.proveedor.id, 'provider_reference': 'OTRA', 'reference': 'OTRA-REF',
            'operation': 'online_redirect', 'payment_id': False, 'is_post_processed': True,
            'sale_order_ids': [Command.clear()], 'invoice_ids': [Command.clear()], 'source_transaction_id': False,
            # lo que la lista negra dejaba abierto (RV8, R8-2):
            'partner_id': self.otro_cliente.id, 'landing_route': "javascript:alert('rv8')",
            'state_message': 'Llama al +507 0000-0000', 'company_id': self.env.company.id,
            'payment_method_id': self.metodo.id, 'token_id': False, 'tokenize': True,
            'last_state_change': '2026-01-01 00:00:00', 'partner_name': 'Nombre', 'partner_email': 'x@example.com',
            'partner_phone': '1', 'partner_address': 'calle', 'partner_city': 'ciudad', 'partner_zip': '0',
            'partner_state_id': False, 'partner_country_id': False, 'child_transaction_ids': [Command.clear()]}
        for nombre, usuario in ((n, self.usuarios[n]) for n in QUIEN_NO_COBRA):
            for campo, valor in valores.items():
                self.frio()
                with self.subTest(usuario=nombre, campo=campo), self.assertRaises(AccessError):
                    tx.with_user(usuario).write({campo: valor})
        tx.invalidate_recordset()
        self.assertEqual((tx.state, tx.amount, tx.sale_order_ids), ('pending', pedido.amount_total, pedido))
        self.assertNotEqual(tx.landing_route, "javascript:alert('rv8')")

    def test_ningun_campo_dcasa_de_la_transaccion_lo_escribe_quien_no_cobra(self):
        """Los campos de Yappy, de Tilopay y los que vengan (``dcasa_*``) son del sistema, de cualquier proveedor."""
        _pedido, tx = self.pedido_con_transaccion()
        for campo in ('dcasa_yappy_revision', 'dcasa_yappy_orden', 'dcasa_tilopay_veredicto', 'dcasa_lo_que_venga'):
            self.frio()
            with self.subTest(campo=campo), self.assertRaises(AccessError):
                tx.with_user(self.usuarios['vendedora']).write({campo: 'x'})

    def test_un_write_que_mezcla_un_campo_cualquiera_con_uno_del_dinero_tambien_se_niega(self):
        _pedido, tx = self.pedido_con_transaccion()
        self.frio()
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
        tx.sudo().write({'amount': pedido.amount_total, 'is_post_processed': False, 'state_message': 'del sistema'})
        tx.with_user(self.env.ref('base.user_root')).write({'is_post_processed': True})
        self.assertTrue(tx.is_post_processed)
        # una Vendedora que dispara el flujo por un camino del sistema (sudo) tampoco se bloquea
        _pedido2, tx2 = self.pedido_con_transaccion()
        tx2.with_user(self.usuarios['vendedora']).sudo()._set_done()
        self.assertEqual(tx2.state, 'done')
        # ni al crear (la tienda crea la transacción con ``sudo`` aunque quien compra sea la propia vendedora)
        pedido3 = self.pedido_de()
        creada = self.env['payment.transaction'].with_user(self.usuarios['vendedora']).sudo().create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': pedido3.amount_total,
            'currency_id': pedido3.currency_id.id, 'partner_id': self.cliente.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(pedido3.ids)]})
        self.assertTrue(creada)

    def test_el_portal_y_el_publico_tampoco_escriben(self):
        _pedido, tx = self.pedido_con_transaccion()
        portal = new_test_user(self.env, login='r71_portal', groups='base.group_portal')
        for usuario in (portal, self.env.ref('base.public_user')):
            self.frio()
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                tx.with_user(usuario).write({'state': 'done'})

    def test_la_vendedora_sigue_leyendo_sus_transacciones(self):
        """Solo se cierra la escritura: leer no cambia (la pantalla del pedido muestra «Cómo pagó»)."""
        _pedido, tx = self.pedido_con_transaccion()
        lectura = tx.with_user(self.usuarios['vendedora']).read(['state', 'amount', 'provider_id'])
        self.assertEqual(lectura[0]['state'], 'pending')


@tagged('post_install', '-at_install')
class TestLaVendedoraNoCreaTransacciones(BaseTransaccion):
    """R8-6: antes el ``create`` solo se negaba por casualidad (leer el proveedor es de administrador); con la caché
    «tibia» de un proveedor ya leído el mismo ``create`` pasaba. Ahora lo niega la propia regla."""

    def valores(self, pedido, **extra):
        """Sin ``sale_order_ids`` a propósito: ligar un pedido que no es de la vendedora ya da un AccessError por sí
        solo (reglas de Ventas), y la prueba tiene que medir el ``create`` de la transacción y nada más."""
        return {'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id,
                'amount': pedido.amount_total, 'currency_id': pedido.currency_id.id,
                'partner_id': self.cliente.id, 'operation': 'online_direct', **extra}

    def test_la_vendedora_no_crea_una_transaccion_ya_hecha_ni_con_la_cache_fria_ni_con_la_tibia(self):
        """Con la caché «tibia» (el proveedor ya leído, todos sus campos, por el superusuario en esta misma transacción)
        el ``create`` de la Vendedora PASABA (RV8, R8-6): lo frenaba solo el permiso de leer el proveedor del core. Se
        mide con ``try/except`` y sin ``assertRaises(AccessError)``, porque este último limpia la caché por su cuenta
        y taparía justo el caso. Lo que se exige es el mensaje de LA REGLA, no el del core."""
        pedido = self.pedido_de()
        for nombre in QUIEN_NO_COBRA:
            usuario = self.usuarios[nombre]
            for cache in ('tibia', 'fria'):
                if cache == 'tibia':
                    self.assertTrue(self.proveedor.read())
                else:
                    self.frio()
                with self.subTest(usuario=nombre, cache=cache):
                    try:
                        creada = self.env['payment.transaction'].with_user(usuario).create(
                            self.valores(pedido, state='done'))
                    except AccessError as error:
                        self.assertIn('crear una transacción', str(error), 'lo niega la regla, no el core')
                    else:
                        self.fail(f'la {nombre} creó una transacción «hecha» con la caché {cache}: {creada.state}')

    def test_ni_siquiera_una_transaccion_pendiente_y_ni_copiar(self):
        pedido, tx = self.pedido_con_transaccion()
        vendedora = self.usuarios['vendedora']
        with self.assertRaises(AccessError):
            self.env['payment.transaction'].with_user(vendedora).create(self.valores(pedido))
        self.frio()
        with self.assertRaises(AccessError):
            tx.with_user(vendedora).copy()

    def test_la_regla_no_le_quita_nada_a_quien_cobra(self):
        """La regla es de «quien no cobra». El administrador crea; Caja, Gerencia y contabilidad no pasan por la regla
        (en el core de Odoo leer un proveedor de pago es solo de administrador, así que ahí los frena el core, con su
        propio mensaje: no el de la regla)."""
        pedido = self.pedido_de()
        valores = self.valores(pedido)
        creada = self.env['payment.transaction'].with_user(self.usuarios['administrador']).create(valores)
        self.assertTrue(creada)
        for nombre in ('caja', 'gerencia', 'contabilidad'):
            self.frio()
            with self.subTest(usuario=nombre):
                try:
                    self.env['payment.transaction'].with_user(self.usuarios[nombre]).create(valores)
                except AccessError as error:
                    self.assertNotIn('crear una transacción', str(error), 'lo frena el core, no la regla')


@tagged('post_install', '-at_install')
class TestElOtroLadoDeLaRelacion(BaseTransaccion):
    """R8-1: ``sale.order.transaction_ids`` y ``account.move.transaction_ids`` son la MISMA tabla de relación que
    ``payment.transaction.sale_order_ids`` / ``invoice_ids`` y la Vendedora los escribía. Ligar un cobro ajeno a un
    pedido soltaba mercancía sin cobrar; ligarlo a una factura aplicaba el dinero de un cliente a la factura de otro."""

    def cobro_ajeno(self):
        """Un cobro HECHO de otro cliente (lo deja el sistema)."""
        return self.transaccion_de(self.pedido_de(self.otro_cliente), estado='done')

    def test_la_vendedora_no_liga_un_cobro_ajeno_a_su_pedido(self):
        ajeno = self.cobro_ajeno()
        pedido = self.pedido_de(vendedora=self.usuarios['vendedora'])
        for nombre in QUIEN_NO_COBRA:
            self.frio()
            with self.subTest(usuario=nombre), self.assertRaises(AccessError):
                pedido.with_user(self.usuarios[nombre]).write({'transaction_ids': [Command.link(ajeno.id)]})
        self.assertNotIn(ajeno, pedido.sudo().transaction_ids)

    def test_la_vendedora_no_suelta_el_cobro_hecho_de_su_pedido(self):
        """Esconder el pago: el pedido deja de verse pagado y el apartado nocturno ya no lo cuenta como reclamado."""
        pedido = self.pedido_de(vendedora=self.usuarios['vendedora'])
        propio = self.transaccion_de(pedido, estado='done')
        for comando in (Command.unlink(propio.id), Command.clear(), Command.set([])):
            self.frio()
            with self.assertRaises(AccessError):
                pedido.with_user(self.usuarios['vendedora']).write({'transaction_ids': [comando]})
        self.assertIn(propio, pedido.sudo().transaction_ids)

    def test_ni_al_crear_un_pedido_con_el_cobro_ya_ligado(self):
        ajeno = self.cobro_ajeno()
        valores = {'partner_id': self.cliente.id, 'user_id': self.usuarios['vendedora'].id,
                   'transaction_ids': [Command.link(ajeno.id)]}
        self.frio()
        with self.assertRaises(AccessError):
            self.env['sale.order'].with_user(self.usuarios['vendedora']).create(valores)

    def test_ni_creando_o_actualizando_una_transaccion_desde_el_pedido(self):
        """``Command.create`` y ``Command.update`` en el campo del pedido: la transacción nueva (o su cambio de estado)
        también se niega, por el campo del pedido y por la regla de la transacción."""
        pedido = self.pedido_de(vendedora=self.usuarios['vendedora'])
        tx = self.transaccion_de(pedido)
        valores = {'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': pedido.amount_total,
                   'currency_id': pedido.currency_id.id, 'partner_id': self.cliente.id, 'operation': 'online_direct',
                   'state': 'done'}
        for comando in (Command.create(valores), Command.update(tx.id, {'state': 'done'})):
            self.frio()
            with self.assertRaises(AccessError):
                pedido.with_user(self.usuarios['vendedora']).write({'transaction_ids': [comando]})
        self.frio()
        with self.assertRaises(AccessError):
            self.env['sale.order'].with_user(self.usuarios['vendedora']).create({
                'partner_id': self.cliente.id, 'user_id': self.usuarios['vendedora'].id,
                'transaction_ids': [Command.create(valores)]})
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'pending')

    def test_la_vendedora_no_liga_un_cobro_ajeno_a_una_factura(self):
        ajeno = self.cobro_ajeno()
        pedido = self.pedido_de(vendedora=self.usuarios['vendedora'])
        pedido.action_confirm()
        factura = pedido._create_invoices()
        for nombre in QUIEN_NO_COBRA:
            self.frio()
            with self.subTest(usuario=nombre), self.assertRaises(AccessError):
                factura.with_user(self.usuarios[nombre]).write({'transaction_ids': [Command.link(ajeno.id)]})
        self.assertNotIn(ajeno, factura.sudo().transaction_ids)

    def test_crear_una_factura_a_mano_con_el_cobro_de_otro_se_niega_por_varias_reglas(self):
        """El ``create`` de la factura SÍ lleva la comprobación posterior de ``transaction_ids`` (R9-2: niega a quien no
        cobra; ``sale`` crea la factura del pedido, con sus cobros, con ``sudo`` y por eso pasa). Además, dos reglas de
        ``dcasa_base`` cierran la factura a mano y esta prueba las fija como defensa en profundidad: una factura suelta
        (sin líneas del pedido) la niega «quien no cobra no hace facturas sueltas» (``cobros.py``), y una con líneas de
        SU pedido (``sale_line_ids``) la niega ``enlace_factura.py`` (nadie escribe a mano el enlace con el pedido)."""
        ajeno = self.cobro_ajeno()
        pedido = self.pedido_de(vendedora=self.usuarios['vendedora'])
        pedido.action_confirm()
        linea = pedido.order_line[:1]
        suelta = {'move_type': 'out_invoice', 'partner_id': self.cliente.id,
                  'transaction_ids': [Command.link(ajeno.id)]}
        con_lineas_del_pedido = {
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_origin': pedido.name,
            'invoice_line_ids': [Command.create({
                'product_id': self.producto.id, 'quantity': 1, 'price_unit': 50.0,
                'sale_line_ids': [Command.link(linea.id)]})],
            'transaction_ids': [Command.link(ajeno.id)]}
        for valores in (suelta, con_lineas_del_pedido):
            self.frio()
            with self.assertRaises(UserError):      # (AccessError es un UserError: las dos reglas dan uno u otro)
                self.env['account.move'].with_user(self.usuarios['vendedora']).create(valores)

    def test_la_vendedora_sigue_creando_la_factura_de_un_pedido_ya_cobrado(self):
        """No negar el ``create`` a ciegas: ``sale._create_invoices`` manda los cobros DEL PROPIO pedido (con
        ``Command.set``) y corre con ``sudo``: la factura de un pedido ya pagado en línea sigue naciendo con su
        cobro."""
        vendedora = self.usuarios['vendedora']
        pedido = self.pedido_de(vendedora=vendedora)
        pedido.action_confirm()
        propio = self.transaccion_de(pedido, estado='done')
        self.frio()
        factura = pedido.with_user(vendedora)._create_invoices()
        self.assertTrue(factura)
        self.assertEqual(factura.sudo().transaction_ids, propio, 'la factura nace con el cobro del propio pedido')

    def test_caja_si_puede_ligar_y_el_sistema_con_sudo_tambien(self):
        """No es un permiso nuevo de los demás: Caja y el sistema escriben ``transaction_ids`` como siempre."""
        pedido = self.pedido_de(vendedora=self.usuarios['vendedora'])
        tx = self.transaccion_de(pedido)
        otro_pedido = self.pedido_de(self.otro_cliente)
        otra_tx = self.transaccion_de(otro_pedido)
        pedido.with_user(self.usuarios['caja']).write({'transaction_ids': [Command.link(otra_tx.id)]})
        self.assertIn(otra_tx, pedido.sudo().transaction_ids)
        pedido.sudo().write({'transaction_ids': [Command.unlink(otra_tx.id)]})
        self.assertEqual(pedido.sudo().transaction_ids, tx)


@tagged('post_install', '-at_install')
class TestLasPuertasQueNoSeVieron(BaseTransaccion):
    """RV8b (R9-1 a R9-3): las puertas que el cierre de R8-1 dejó abiertas."""

    def cobro_ajeno(self):
        return self.transaccion_de(self.pedido_de(self.otro_cliente), estado='done')

    def crear_recibo(self, usuario, ajeno=None):
        valores = {
            'move_type': 'out_receipt', 'partner_id': self.cliente.id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': 107.0})]}
        if ajeno:
            valores['transaction_ids'] = [Command.link(ajeno.id)]
        self.frio()
        return self.env['account.move'].with_user(usuario).create(valores)

    # -- R9-1: el default_ del contexto no pasa por ``vals`` ---------------------------------------------------------
    def test_r1_el_pedido_no_nace_con_un_cobro_puesto_por_el_contexto(self):
        """Odoo aplica ``default_<campo>`` del contexto al crear, después de mirar ``vals`` (por RPC cualquiera manda el
        contexto): el guardia mira lo que el pedido trae DESPUÉS de crear."""
        ajeno = self.cobro_ajeno()
        for comando in (Command.link(ajeno.id), Command.set([ajeno.id])):
            for nombre in QUIEN_NO_COBRA:
                self.frio()
                with self.subTest(usuario=nombre, comando=comando[0]), self.assertRaises(AccessError):
                    self.env['sale.order'].with_user(self.usuarios[nombre]).with_context(
                        default_transaction_ids=[comando]).create({
                            'partner_id': self.cliente.id, 'user_id': self.usuarios[nombre].id})

    def test_r1_quien_cobra_y_el_sistema_si_pueden_crear_un_pedido_con_cobros(self):
        ajeno = self.cobro_ajeno()
        for nombre in ('caja', 'gerencia'):       # contabilidad y el administrador a secas no crean pedidos (Ventas)
            with self.subTest(usuario=nombre):
                pedido = self.env['sale.order'].with_user(self.usuarios[nombre]).with_context(
                    default_transaction_ids=[Command.link(ajeno.id)]).create({'partner_id': self.cliente.id})
                self.assertIn(ajeno, pedido.sudo().transaction_ids)
        self.frio()
        pedido = self.env['sale.order'].with_user(self.usuarios['vendedora']).sudo().with_context(
            default_transaction_ids=[Command.link(ajeno.id)]).create({'partner_id': self.cliente.id})
        self.assertIn(ajeno, pedido.sudo().transaction_ids, 'el sistema (sudo) no se ve afectado')

    # -- R9-2: crear a mano la factura (o el recibo) con el cobro ligado ----------------------------------------------
    def test_r2_quien_no_cobra_no_crea_un_recibo_con_el_cobro_de_otro(self):
        """La regla «quien no cobra no hace facturas sueltas» solo mira ``out_invoice``: un recibo de venta
        (``out_receipt``) con el cobro de otro cliente ligado SÍ se creaba."""
        ajeno = self.cobro_ajeno()
        for nombre in QUIEN_NO_COBRA:
            with self.subTest(usuario=nombre), self.assertRaises(AccessError):
                self.crear_recibo(self.usuarios[nombre], ajeno)

    def test_r2_tampoco_con_el_default_del_contexto(self):
        ajeno = self.cobro_ajeno()
        self.frio()
        with self.assertRaises(AccessError):
            self.env['account.move'].with_user(self.usuarios['vendedora']).with_context(
                default_transaction_ids=[Command.link(ajeno.id)]).create({
                    'move_type': 'out_receipt', 'partner_id': self.cliente.id})

    def test_r2_la_factura_de_un_pedido_ya_cobrado_sigue_naciendo_con_su_cobro_y_quien_cobra_sigue_creando(self):
        """El cuidado: ``sale._create_invoices`` crea con ``sudo`` (pasa); Caja puede crear un recibo con cobros."""
        vendedora = self.usuarios['vendedora']
        pedido = self.pedido_de(vendedora=vendedora)
        pedido.action_confirm()
        propio = self.transaccion_de(pedido, estado='done')
        self.frio()
        factura = pedido.with_user(vendedora)._create_invoices()
        self.assertEqual(factura.sudo().transaction_ids, propio)
        recibo = self.crear_recibo(self.usuarios['caja'], propio)
        self.assertIn(propio, recibo.sudo().transaction_ids)

    # -- R9-2: el cambio de tipo ---------------------------------------------------------------------------------------
    def test_r3_quien_no_cobra_no_cambia_el_tipo_de_un_documento_de_cliente(self):
        """Recibo → factura (suelta) y → nota de crédito (en borrador, sin Gerencia): ``write(move_type)`` no tenía
        guardia."""
        for nombre in QUIEN_NO_COBRA:
            recibo = self.crear_recibo(self.usuarios[nombre])
            for tipo in ('out_invoice', 'out_refund'):
                self.frio()
                with self.subTest(usuario=nombre, tipo=tipo), self.assertRaises(AccessError):
                    recibo.with_user(self.usuarios[nombre]).write({'move_type': tipo})
            recibo.invalidate_recordset()
            self.assertEqual(recibo.move_type, 'out_receipt')

    def test_r3_caja_cambia_recibo_a_factura_pero_la_nota_de_credito_es_de_gerencia(self):
        recibo = self.crear_recibo(self.usuarios['caja'])
        self.frio()
        with self.assertRaises(AccessError):
            recibo.with_user(self.usuarios['caja']).write({'move_type': 'out_refund'})
        recibo.with_user(self.usuarios['caja']).write({'move_type': 'out_invoice'})
        self.assertEqual(recibo.move_type, 'out_invoice')
        recibo.with_user(self.usuarios['gerencia']).write({'move_type': 'out_refund'})
        self.assertEqual(recibo.move_type, 'out_refund')

    def test_r3_un_write_del_mismo_tipo_no_se_niega(self):
        """La Vendedora guarda formularios con web_save: un ``move_type`` igual al que ya tiene no cambia nada."""
        recibo = self.crear_recibo(self.usuarios['vendedora'])
        recibo.with_user(self.usuarios['vendedora']).write({'move_type': 'out_receipt'})
        self.assertEqual(recibo.move_type, 'out_receipt')

    # -- R9-3: los métodos públicos del core que corren con sudo -----------------------------------------------------
    def test_r4_quien_no_cobra_no_devuelve_captura_ni_anula_un_cobro(self):
        ajeno = self.cobro_ajeno()
        for nombre in QUIEN_NO_COBRA:
            for metodo, frase in (('action_refund', 'devolver un cobro'), ('action_capture', 'capturar un cobro'),
                                  ('action_void', 'anular un cobro')):
                self.frio()
                with self.subTest(usuario=nombre, metodo=metodo):
                    try:
                        getattr(ajeno.with_user(self.usuarios[nombre]), metodo)()
                    except AccessError as error:
                        self.assertIn(frase, str(error), 'lo niega la regla, no el core')
                    else:
                        self.fail(f'{nombre} pudo llamar a {metodo}')
        ajeno.invalidate_recordset()
        self.assertFalse(ajeno.sudo().child_transaction_ids, 'no quedó ninguna transacción hija de devolución')
