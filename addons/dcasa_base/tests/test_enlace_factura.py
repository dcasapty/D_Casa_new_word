"""El enlace factura ↔ pedido (``sale_line_ids``) solo lo escribe el código de ventas (``models/enlace_factura.py``).

Tercera revisión adversarial de la comisión web (2026-11-20): Caja, Nómina y Gerencia, cada uno solo y sin ``sudo``,
creaban una factura de mostrador enlazada a la línea de un pedido online y la comisión del sitio la cobraba como venta
del sitio. Aquí se prueba, sin depender de ningún módulo que lea el enlace: (1) por dónde SÍ se enlaza (facturar el
pedido, el anticipo, la nota de crédito, anular y crear de nuevo) y (2) que a mano no se puede, con ningún usuario y
tampoco con ``sudo``. Datos inventados."""
from odoo import Command
from odoo.addons.dcasa_base.models.enlace_factura import CLAVE_ENLACE, ENLACE
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


class EnlaceBase(TransactionCase):
    """Los datos y ayudas que comparten las pruebas del enlace (no tiene pruebas propias)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente enlace de factura'})
        cls.producto = cls.env['product.product'].create({
            'name': 'MUEBLE ENLACE DE FACTURA', 'type': 'consu', 'invoice_policy': 'order', 'list_price': 100.0})
        cls.caja = new_test_user(cls.env, login='enlace_caja', groups='base.group_user,dcasa_base.group_caja')
        cls.gerencia = new_test_user(cls.env, login='enlace_gerencia',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        cls.contador = new_test_user(cls.env, login='enlace_contador',
                                     groups='base.group_user,account.group_account_manager')

    def pedido(self, precio=100.0):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1,
                                           'price_unit': precio})]})
        orden.action_confirm()
        return orden

    def factura_de(self, orden):
        factura = orden._create_invoices()
        factura.action_post()
        return factura

    def enlace_a_mano(self, orden, usuario=None, comando=None):
        """Una factura tecleada a mano cuya línea apunta a la del pedido."""
        Move = self.env['account.move']
        if usuario:
            Move = Move.with_user(usuario)
        return Move.create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2030-03-04',
            'invoice_line_ids': [Command.create({
                'name': 'Mueble de mostrador', 'quantity': 1, 'price_unit': 5000.0,
                'sale_line_ids': [Command.set(orden.order_line.ids)] if comando is None else comando})]})


@tagged('post_install', '-at_install')
class TestEnlaceFacturaPedido(EnlaceBase):

    # ------------------------------------------------------------------ por dónde SÍ se enlaza

    def test_la_factura_que_sale_del_pedido_queda_enlazada(self):
        orden = self.pedido()
        factura = self.factura_de(orden)
        self.assertEqual(factura.invoice_line_ids.sale_line_ids, orden.order_line)
        self.assertEqual(orden.order_line.invoice_lines, factura.invoice_line_ids)

    def test_quien_factura_no_se_queda_con_la_llave(self):
        """La factura que devuelve ``_create_invoices`` no lleva la llave interna en su contexto."""
        orden = self.pedido()
        factura = orden._create_invoices()
        self.assertNotIn('dcasa_base_enlace_de_factura', factura.env.context)
        with self.assertRaises(UserError):
            factura.invoice_line_ids.write({'sale_line_ids': [Command.clear()]})

    def test_el_anticipo_y_la_factura_final_quedan_enlazados(self):
        orden = self.pedido(200.0)
        asistente = self.env['sale.advance.payment.inv'].with_context(
            active_model='sale.order', active_ids=orden.ids, active_id=orden.id).create({
                'advance_payment_method': 'percentage', 'amount': 50})
        anticipo = asistente.create_invoices() and orden.invoice_ids
        self.assertTrue(anticipo.invoice_line_ids.sale_line_ids.filtered('is_downpayment'))
        anticipo.action_post()
        final = self.env['sale.advance.payment.inv'].with_context(
            active_model='sale.order', active_ids=orden.ids, active_id=orden.id).create({
                'advance_payment_method': 'delivered'})
        final.create_invoices()
        facturas = orden.invoice_ids - anticipo
        self.assertEqual(len(facturas), 1)
        self.assertTrue(facturas.invoice_line_ids.sale_line_ids, 'la factura final también lleva el enlace')

    def test_la_nota_de_credito_copia_el_enlace_de_la_factura_que_revierte(self):
        orden = self.pedido()
        factura = self.factura_de(orden)
        asistente = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'reason': 'devolución de prueba', 'journal_id': factura.journal_id.id})
        asistente.refund_moves()
        nota = factura.reversal_move_ids
        self.assertEqual(len(nota), 1)
        self.assertEqual(nota.invoice_line_ids.sale_line_ids, orden.order_line)

    def test_anular_y_crear_una_factura_nueva_conserva_el_enlace(self):
        """«Anular y crear una nueva factura»: el borrador nuevo sale de copiar la factura con sus enlaces."""
        orden = self.pedido()
        factura = self.factura_de(orden)
        asistente = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'reason': 'corregir de prueba', 'journal_id': factura.journal_id.id})
        asistente.modify_moves()
        nueva = asistente.new_move_ids.filtered(lambda m: m.move_type == 'out_invoice')
        self.assertEqual(len(nueva), 1)
        self.assertEqual(nueva.invoice_line_ids.sale_line_ids, orden.order_line)

    def test_el_pedido_de_otro_usuario_se_factura_desde_el_boton_sin_llave_extra(self):
        """Caja y Gerencia facturan un pedido con su propio usuario (el camino normal no se rompe)."""
        for usuario in (self.caja, self.gerencia):
            with self.subTest(usuario=usuario.login):
                orden = self.pedido()
                factura = orden.with_user(usuario).sudo()._create_invoices()
                self.assertTrue(factura.invoice_line_ids.sale_line_ids)

    # ------------------------------------------------------------------ a mano NO se puede

    def test_una_factura_tecleada_no_se_enlaza_a_un_pedido_con_ningun_usuario(self):
        orden = self.pedido()
        for usuario in (self.caja, self.gerencia, self.contador, None):
            for comando in ([Command.set(orden.order_line.ids)], [Command.link(orden.order_line.id)],
                            [Command.create({'order_id': orden.id, 'product_id': self.producto.id})]):
                with self.subTest(usuario=usuario.login if usuario else 'sudo', comando=comando[0][0]):
                    with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
                        self.enlace_a_mano(orden, usuario, comando)

    def test_una_factura_tecleada_con_el_enlace_vacio_si_se_puede(self):
        """Un many2many vacío no enlaza nada: el formulario de Odoo lo manda así y no se frena."""
        factura = self.enlace_a_mano(self.pedido(), comando=[Command.set([])])
        self.assertFalse(factura.invoice_line_ids.sale_line_ids)
        otra = self.enlace_a_mano(self.pedido(), comando=[Command.clear()])
        self.assertFalse(otra.invoice_line_ids.sale_line_ids)

    def test_el_enlace_de_una_linea_ya_facturada_no_se_agrega_ni_se_quita_ni_se_cambia(self):
        orden = self.pedido()
        factura = self.factura_de(orden)
        otra_orden = self.pedido()
        linea = factura.invoice_line_ids
        for usuario in (self.caja, self.gerencia, self.contador, None):
            for comando in ([Command.clear()], [Command.unlink(orden.order_line.id)],
                            [Command.link(otra_orden.order_line.id)],
                            [Command.set(otra_orden.order_line.ids)]):
                with self.subTest(usuario=usuario.login if usuario else 'sudo', comando=comando[0][0]):
                    destino = linea.with_user(usuario) if usuario else linea
                    with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
                        destino.write({'sale_line_ids': comando})
        self.assertEqual(linea.sale_line_ids, orden.order_line, 'nada cambió')

    def test_escribir_lo_mismo_que_ya_hay_no_se_frena(self):
        orden = self.pedido()
        linea = self.factura_de(orden).invoice_line_ids
        linea.write({'sale_line_ids': [Command.set(orden.order_line.ids)]})
        linea.write({'sale_line_ids': [Command.link(orden.order_line.id)]})
        self.assertEqual(linea.sale_line_ids, orden.order_line)

    def test_el_otro_lado_del_enlace_tampoco_se_escribe_a_mano(self):
        """``sale.order.line.invoice_lines`` es la misma tabla: escribirla desde el pedido enlaza igual."""
        orden = self.pedido()
        tienda = self.enlace_a_mano(orden, comando=[])
        with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
            orden.order_line.write({'invoice_lines': [Command.link(tienda.invoice_line_ids.id)]})
        with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
            self.env['sale.order.line'].create({
                'order_id': orden.id, 'product_id': self.producto.id,
                'invoice_lines': [Command.link(tienda.invoice_line_ids.id)]})
        self.assertFalse(tienda.invoice_line_ids.sale_line_ids)

    def test_duplicar_una_factura_con_el_contexto_de_las_notas_no_copia_el_enlace_a_mano(self):
        """``include_business_fields`` es la bandera con que Odoo copia el enlace al revertir; por RPC cualquiera puede
        mandarla en el contexto: duplicar una factura así no puede dejarle el enlace a la copia."""
        orden = self.pedido()
        factura = self.factura_de(orden)
        for usuario in (self.caja, self.gerencia, None):
            with self.subTest(usuario=usuario.login if usuario else 'sudo'):
                origen = factura.with_user(usuario) if usuario else factura
                with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
                    origen.with_context(include_business_fields=True).copy()
        copia = factura.copy()
        self.assertFalse(copia.invoice_line_ids.sale_line_ids, 'duplicar a secas no copia el enlace (copy=False)')

    def test_la_llave_no_viaja_por_rpc(self):
        """Quien manda ``dcasa_base_enlace_de_factura: True`` en el contexto no abre la puerta."""
        orden = self.pedido()
        with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
            self.env['account.move'].with_context(dcasa_base_enlace_de_factura=True).create({
                'move_type': 'out_invoice', 'partner_id': self.cliente.id,
                'invoice_line_ids': [Command.create({
                    'name': 'X', 'quantity': 1, 'price_unit': 1.0,
                    'sale_line_ids': [Command.set(orden.order_line.ids)]})]})

    def test_una_linea_ya_facturada_no_cambia_de_pedido(self):
        """Si no, la línea facturada de una venta de mostrador se podría mover a un pedido online."""
        orden, otra = self.pedido(), self.pedido()
        self.factura_de(orden)
        with self.assertRaisesRegex(UserError, 'no cambia de pedido'), self.env.cr.savepoint():
            orden.order_line.write({'order_id': otra.id})
        self.assertEqual(orden.order_line.order_id, orden)
        sin_facturar = otra.order_line
        sin_facturar.write({'order_id': otra.id})      # lo que no cambia de pedido no se frena


@tagged('post_install', '-at_install')
class TestEnlaceFacturaPorDefectoDelContexto(EnlaceBase):
    """Cuarta revisión adversarial (2026-11-20): el gancho de ``create`` solo miraba ``vals``, pero Odoo aplica los
    ``default_<campo>`` del contexto DESPUÉS, y por RPC cualquiera los manda: Caja, Nómina y Gerencia enlazaban una
    línea de 5,000 a la línea de un pedido de 1,000 con ``context={'default_sale_line_ids': ...}``."""

    def factura_sin_enlace(self, usuario=None):
        """Una factura de mostrador en borrador con una línea sin enlace."""
        return self.enlace_a_mano(self.pedido(), usuario, comando=[])

    def linea_con_default(self, usuario, borrador, **contexto):
        Linea = self.env['account.move.line']
        if usuario:
            Linea = Linea.with_user(usuario)
        return Linea.with_context(**contexto).create({
            'move_id': borrador.id, 'name': 'Otra línea de mostrador', 'quantity': 1, 'price_unit': 5000.0,
            'display_type': 'product'})

    def test_un_default_sale_line_ids_del_contexto_no_enlaza_la_linea_nueva_de_la_factura(self):
        orden = self.pedido()
        for usuario in (self.caja, self.gerencia, self.contador, None):
            with self.subTest(usuario=usuario.login if usuario else 'sudo'):
                borrador = self.factura_sin_enlace()
                self.linea_con_default(usuario, borrador, default_sale_line_ids=[[6, 0, orden.order_line.ids]])
                self.assertEqual(len(borrador.invoice_line_ids), 2, 'la línea se creó: solo falta el enlace')
                self.assertFalse(borrador.invoice_line_ids.sale_line_ids)
                self.assertFalse(orden.order_line.invoice_lines)

    def test_un_default_invoice_lines_del_contexto_no_enlaza_la_linea_nueva_del_pedido(self):
        orden = self.pedido()
        for usuario in (self.gerencia, None):
            with self.subTest(usuario=usuario.login if usuario else 'sudo'):
                borrador = self.factura_sin_enlace()
                Linea = self.env['sale.order.line']
                if usuario:
                    Linea = Linea.with_user(usuario)
                nueva = Linea.with_context(default_invoice_lines=[[6, 0, borrador.invoice_line_ids.ids]]).create({
                    'order_id': orden.id, 'product_id': self.producto.id, 'product_uom_qty': 1, 'price_unit': 1.0})
                self.assertTrue(nueva)
                self.assertFalse(borrador.invoice_line_ids.sale_line_ids)
                self.assertFalse(nueva.invoice_lines)

    def test_default_get_de_las_dos_lineas_descarta_el_enlace_salvo_con_la_llave_interna(self):
        orden = self.pedido()
        borrador = self.factura_sin_enlace()
        LineaFactura = self.env['account.move.line']
        LineaPedido = self.env['sale.order.line']
        de_factura = {'default_sale_line_ids': [[6, 0, orden.order_line.ids]]}
        de_pedido = {'default_invoice_lines': [[6, 0, borrador.invoice_line_ids.ids]]}
        self.assertNotIn('sale_line_ids', LineaFactura.with_context(**de_factura).default_get(['sale_line_ids']))
        self.assertNotIn('invoice_lines', LineaPedido.with_context(**de_pedido).default_get(['invoice_lines']))
        # el código que de verdad factura sí puede (y lo demás de ``default_get`` no cambia)
        self.assertIn('sale_line_ids', LineaFactura._dcasa_con_enlace_de_pedido().with_context(
            **de_factura).default_get(['sale_line_ids']))
        self.assertIn('invoice_lines', LineaPedido.with_context(**{CLAVE_ENLACE: ENLACE}, **de_pedido).default_get(
            ['invoice_lines']))
        self.assertEqual(LineaFactura.with_context(default_name='texto').default_get(['name']), {'name': 'texto'})

    def test_la_llave_en_el_contexto_como_texto_o_true_no_abre_la_puerta_de_los_defaults(self):
        orden = self.pedido()
        borrador = self.factura_sin_enlace()
        for llave in (True, 'True', 1, {}):
            with self.subTest(llave=llave):
                self.linea_con_default(self.gerencia, borrador, default_sale_line_ids=[[6, 0, orden.order_line.ids]],
                                       dcasa_base_enlace_de_factura=llave)
        self.assertFalse(borrador.invoice_line_ids.sale_line_ids)

    def test_un_default_de_las_lineas_de_la_factura_con_el_enlace_adentro_se_frena(self):
        """``default_invoice_line_ids`` / ``default_line_ids`` traen las líneas ya armadas: cada una pasa por el gancho
        de ``create`` de la línea, que mira sus valores."""
        orden = self.pedido()
        linea = {'name': 'X', 'quantity': 1, 'price_unit': 5000.0, 'sale_line_ids': [Command.set(orden.order_line.ids)]}
        for usuario in (self.caja, self.gerencia, None):
            for clave in ('default_invoice_line_ids', 'default_line_ids'):
                with self.subTest(usuario=usuario.login if usuario else 'sudo', clave=clave):
                    Move = self.env['account.move']
                    if usuario:
                        Move = Move.with_user(usuario)
                    with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
                        Move.with_context(**{clave: [Command.create(linea)]}).create({
                            'move_type': 'out_invoice', 'partner_id': self.cliente.id})

    def test_duplicar_una_factura_o_una_linea_con_valores_que_traen_el_enlace_se_frena(self):
        orden = self.pedido()
        borrador = self.factura_sin_enlace()
        enlace = {'sale_line_ids': [Command.set(orden.order_line.ids)]}
        for usuario in (self.caja, self.gerencia, None):
            with self.subTest(usuario=usuario.login if usuario else 'sudo'):
                factura = borrador.with_user(usuario) if usuario else borrador
                with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
                    factura.copy(default={'invoice_line_ids': [Command.create(
                        {'name': 'X', 'quantity': 1, 'price_unit': 5000.0, **enlace})]})
                lineas = borrador.invoice_line_ids.with_user(usuario) if usuario else borrador.invoice_line_ids
                with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
                    lineas.copy(default=enlace)
        self.assertFalse(orden.order_line.invoice_lines)

    def test_importar_una_factura_con_el_enlace_no_lo_deja_pasar(self):
        """La importación (``load``) arma los valores y llama a ``create``: el enlace no se escribe."""
        orden = self.pedido()
        for usuario in (self.caja, self.gerencia, None):
            with self.subTest(usuario=usuario.login if usuario else 'sudo'):
                Move = self.env['account.move']
                if usuario:
                    Move = Move.with_user(usuario)
                with self.env.cr.savepoint():
                    resultado = Move.load(
                        ['move_type', 'partner_id/.id', 'invoice_date', 'invoice_line_ids/name',
                         'invoice_line_ids/quantity', 'invoice_line_ids/price_unit',
                         'invoice_line_ids/sale_line_ids/.id'],
                        [['out_invoice', str(self.cliente.id), '2030-03-04', 'X', '1', '5000',
                          str(orden.order_line.id)]])
                    creadas = Move.browse(resultado.get('ids') or [])
                    self.assertFalse(creadas.invoice_line_ids.sale_line_ids)
                self.assertFalse(orden.order_line.invoice_lines)
