"""Cuarta revisión adversarial, bloqueante 1 y importante 2: el enlace factura-pedido no se fabrica con un ``default_*``
del contexto (de punta a punta: hasta el libro de la comisión) y quien mueve la línea de un pedido online sin facturar
a otro pedido deja huella en el pedido de donde sale.

Cifras y personas de PRUEBA."""
# ruff: noqa: E501
from odoo import Command
from odoo.addons.dcasa_comision_web.tests.common import DIA
from odoo.addons.dcasa_comision_web.tests.test_vendedoras import VendedoraCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVentaFabricadaConUnDefault(VendedoraCommon):
    """Caja, Nómina y Gerencia, cada uno solo y sin ``sudo``, creaban una factura vacía, le agregaban una línea de 5,000
    con ``default_sale_line_ids`` hacia un pedido online de 1,000, la publicaban y la cobraban: 500.00 de comisión."""

    def test_una_factura_de_mostrador_no_se_cobra_como_venta_del_sitio_con_un_default_sale_line_ids(self):
        self.version(10.0)
        for nombre, usuario in (('caja', self.u_caja), ('nomina', self.u_nomina), ('gerencia', self.u_gerencia)):
            with self.subTest(rol=nombre):
                online = self.orden()          # pedido online de 1,000, pagado por otra vía y todavía sin facturar
                libro_antes = len(self.libro())
                factura = self.env['account.move'].with_user(usuario).create({
                    'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA})
                self.env['account.move.line'].with_user(usuario).with_context(
                    default_sale_line_ids=[[6, 0, online.order_line.ids]]).create({
                        'move_id': factura.id, 'name': 'Mueble de mostrador', 'quantity': 1, 'price_unit': 5000.0,
                        'display_type': 'product', 'tax_ids': [Command.set(self.itbms.ids)]})
                factura.action_post()
                self.pagar(factura)
                self.assertEqual(factura.payment_state, 'paid', 'la factura de mostrador sí se pudo cobrar')
                self.assertFalse(factura.invoice_line_ids.sale_line_ids, 'pero sin el enlace que fabricaba el origen')
                self.assertFalse(self.venta(factura), 'no entra una venta del sitio fabricada')
                self.assertEqual(len(self.libro()), libro_antes, 'ni un centavo de comisión')

    def test_el_otro_lado_default_invoice_lines_de_gerencia_tampoco_enlaza(self):
        self.version(10.0)
        online = self.orden()
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'name': 'M', 'quantity': 1, 'price_unit': 5000.0,
                                                 'tax_ids': [Command.set(self.itbms.ids)]})]})
        self.env['sale.order.line'].with_user(self.u_gerencia).with_context(
            default_invoice_lines=[[6, 0, factura.invoice_line_ids.ids]]).create({
                'order_id': online.id, 'product_id': self.mueble.id, 'product_uom_qty': 1, 'price_unit': 1000.0})
        self.assertFalse(factura.invoice_line_ids.sale_line_ids)
        factura.action_post()
        self.pagar(factura)
        self.assertFalse(self.venta(factura))

    def test_facturar_el_pedido_online_de_verdad_sigue_dando_la_venta_del_sitio(self):
        """Control: el camino legítimo no se rompe (el enlace lo escribe el código de ventas)."""
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.assertTrue(factura.invoice_line_ids.sale_line_ids)
        self.assertEqual((venta.base_centavos, venta.comision_centavos), (100000, 10000))


@tagged('post_install', '-at_install')
class TestRobarLaVentaAntesDeFacturar(VendedoraCommon):
    """El espejo de lo que cierra la puerta del enlace: antes de facturar, la línea del pedido online se pasa a un pedido
    de mostrador de una vendedora; se factura ese y la venta online sería de ella (bono). Pasarla ya no es invisible."""

    def test_mover_la_linea_de_un_pedido_online_sin_facturar_marca_el_pedido_de_donde_sale(self):
        self.version(10.0)
        for nombre, usuario in (('caja', self.u_caja), ('gerencia', self.u_gerencia), ('nomina', self.u_nomina)):
            with self.subTest(rol=nombre):
                online = self.orden(creado_por=self.env.ref('base.public_user'), confirmar=True)
                mostrador = self.orden(web=False, vendedora=self.u_vendedora, lineas=[(self.mueble, 1.0, 1, {})])
                self.assertFalse(online.dcasa_tocada_por_id)
                online.order_line.with_user(usuario).write({'order_id': mostrador.id})
                self.assertEqual(online.dcasa_tocada_por_id, usuario,
                                 'el pedido online quedó vacío: el equipo que le quitó la línea queda anotado')
                self.assertFalse(mostrador.dcasa_tocada_por_id, 'el de mostrador no es de un flujo digital')

    def test_la_venta_robada_sale_senalada_como_del_equipo_en_ventas_del_sitio(self):
        """Lo que ve Gerencia: el pedido online al que le quitaron la línea y que alguien cobra con otra cosa."""
        self.version(10.0)
        online = self.orden(creado_por=self.env.ref('base.public_user'), confirmar=False,
                            lineas=[(self.mueble, 1000.0, 1, {}), (self.mueble, 500.0, 1, {})])
        quitada = online.order_line[:1]
        otro = self.orden(web=False, vendedora=self.u_vendedora, lineas=[(self.mueble, 1.0, 1, {})])
        quitada.with_user(self.u_gerencia).write({'order_id': otro.id})
        online.action_confirm()
        factura = self.facturar(online)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual((venta.tocada_por_id, venta.creado_por_personal), (self.u_gerencia, True))

    def test_mover_una_linea_de_un_pedido_online_a_otro_marca_los_dos(self):
        publico = self.env.ref('base.public_user')
        origen = self.orden(creado_por=publico, confirmar=False)
        destino = self.orden(creado_por=publico, confirmar=False)
        origen.order_line.with_user(self.u_gerencia).write({'order_id': destino.id})
        self.assertEqual((origen.dcasa_tocada_por_id, destino.dcasa_tocada_por_id), (self.u_gerencia, self.u_gerencia))

    def test_lo_que_no_cambia_de_pedido_ni_es_de_un_usuario_interno_no_deja_huella(self):
        publico = self.env.ref('base.public_user')
        online = self.orden(creado_por=publico, confirmar=False)
        mostrador = self.orden(web=False, confirmar=False)
        # un visitante (o el servidor en su nombre) que mueve la línea no es alguien del equipo
        online.order_line.with_user(publico).sudo().write({'order_id': mostrador.id})
        self.assertFalse(online.dcasa_tocada_por_id)
        # y un pedido de mostrador al que le quitan líneas no es de un flujo digital
        mostrador.order_line.with_user(self.u_gerencia).write({'order_id': online.id})
        self.assertFalse(mostrador.dcasa_tocada_por_id)
