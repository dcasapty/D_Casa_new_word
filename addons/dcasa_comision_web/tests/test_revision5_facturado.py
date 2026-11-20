"""Quinta revisión adversarial, importante 1: la base de la comisión es lo FACTURADO y cobrado, y quien tiene permiso de
facturas (Caja, Gerencia y hasta la vendedora, por el asistente de facturar) podía editar el precio o la cantidad de la
factura en borrador de un pedido online, publicarla y cobrarla: una base de 5,000.00 (comisión de 500.00 al 10 %) donde
lo normal era 1,000.00 (100.00); también con un anticipo de monto fijo mayor que el pedido (Odoo no le pone tope).
El documento decía que esto lo cubría «el aviso de Ventas del sitio», y ese aviso no existía.

Ahora la venta sale señalada como «Facturado distinto del pedido» (campo ``facturado_distinto``, filtro y aviso en
*Ventas del sitio*). Es una SEÑAL, no un freno: lo que se paga no cambia (la pregunta para Gerencia —solo señal o además
un freno— queda en «Por decidir» de ``docs/COMISION_WEB.md``). Las ventas normales NO salen señaladas: con descuento en
la línea, con envío, con un premio, con anticipo y factura final, con una nota de crédito y con una factura parcial.

Cifras y personas de PRUEBA."""
# ruff: noqa: E501, B023
from lxml import etree

from odoo.addons.dcasa_comision_web.tests.common import DIA
from odoo.addons.dcasa_comision_web.tests.test_comision import ComisionReloj
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestFacturadoDistintoDelPedido(ComisionReloj):

    def setUp(self):
        super().setUp()
        self.Venta = self.env['dcasa.web.venta']
        self.publico = self.env.ref('base.public_user')

    # --- ayudas ---------------------------------------------------------------------------------------------------

    def asistente(self, orden, usuario=None, **valores):
        asistente = self.env['sale.advance.payment.inv']
        if usuario:
            asistente = asistente.with_user(usuario)
        return asistente.with_context(active_model='sale.order', active_ids=orden.ids, active_id=orden.id).create(valores)

    def factura_en_borrador(self, orden, usuario=None):
        """El borrador de la factura de TODO el pedido, como lo arma el asistente de facturar."""
        self.asistente(orden, usuario, advance_payment_method='delivered').create_invoices()
        borrador = orden.invoice_ids.filtered(lambda f: f.state == 'draft')
        borrador.sudo().invoice_date = DIA
        return borrador

    def publicar_y_cobrar(self, factura, usuario=None):
        (factura.with_user(usuario) if usuario else factura).action_post()
        self.pagar(factura)
        return self.venta(factura)

    def anticipo(self, orden, usuario=None, **valores):
        """Una factura de anticipo, publicada y cobrada. Devuelve la factura."""
        self.asistente(orden, usuario, **valores).create_invoices()
        factura = orden.invoice_ids.filtered(lambda f: f.state == 'draft')
        factura.sudo().invoice_date = DIA
        (factura.with_user(usuario) if usuario else factura).action_post()
        self.pagar(factura)
        return factura

    def revertir(self, factura, motivo):
        """La nota de crédito que revierte la factura entera (el camino de Odoo), publicada."""
        self.env['account.move.reversal'].with_context(active_model='account.move', active_ids=factura.ids).create({
            'journal_id': factura.journal_id.id, 'date': DIA, 'reason': motivo}).refund_moves()
        nota = factura.reversal_move_ids
        self.assertEqual(len(nota), 1)
        nota.action_post()
        return nota

    def assertNormal(self, factura, que):
        venta = self.venta(factura)
        self.assertTrue(venta, f'{que}: la factura es una venta del sitio')
        self.assertFalse(venta.facturado_distinto, f'{que}: una venta normal NO se señala')

    # --- ventas normales: sin falsos positivos ---------------------------------------------------------------------

    def test_una_venta_normal_no_se_senala(self):
        self.version(10.0)
        self.assertNormal(self.venta_web(), 'venta normal')

    def test_sin_version_de_reglas_tambien_se_mide_la_senal(self):
        """La señal es de la medición (como las otras): no depende de que haya una versión de las reglas."""
        venta = self.venta(self.venta_web())
        self.assertEqual(venta.estado, 'medida')
        self.assertFalse(venta.facturado_distinto)

    def test_descuento_de_la_linea_envio_y_premio_no_se_senalan(self):
        self.version(10.0)
        orden = self.orden(lineas=[(self.mueble, 1000.0, 2, {'discount': 10.0}), (self.premio, -50.0, 1, {}),
                                   (self.envio, 40.0, 1, {'is_delivery': True})])
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual(venta.productos_centavos, 180000)
        self.assertEqual(venta.descuento_negativas_centavos, 5000)
        self.assertEqual(venta.envio_centavos, 4000)
        self.assertFalse(venta.facturado_distinto)

    def test_un_pedido_con_varias_cantidades_no_se_senala(self):
        self.version(10.0)
        factura = self.facturar(self.orden(lineas=[(self.mueble, 1000.0, 3, {})]))
        self.pagar(factura)
        self.assertNormal(factura, 'tres unidades')

    def test_anticipo_de_porcentaje_y_factura_final_no_se_senalan(self):
        self.version(10.0)
        orden = self.orden()
        anticipo = self.anticipo(orden, advance_payment_method='percentage', amount=40.0)
        self.assertNormal(anticipo, 'anticipo del 40 %')
        final = self.factura_en_borrador(orden)
        self.assertTrue(final.invoice_line_ids.filtered('is_downpayment'), 'la final resta el anticipo')
        self.publicar_y_cobrar(final)
        self.assertNormal(final, 'factura final con el anticipo restado')

    def test_anticipo_de_monto_fijo_que_cabe_en_el_pedido_y_factura_final_no_se_senalan(self):
        self.version(10.0)
        orden = self.orden()
        anticipo = self.anticipo(orden, advance_payment_method='fixed', fixed_amount=321.0)
        self.assertNormal(anticipo, 'anticipo fijo de 321')
        final = self.factura_en_borrador(orden)
        self.publicar_y_cobrar(final)
        self.assertNormal(final, 'factura final tras un anticipo fijo')

    def test_dos_anticipos_que_suman_justo_el_pedido_no_se_senalan(self):
        """Con la tolerancia de los centavos: tres tercios de 1,000 no se pasan por un centavo de redondeo."""
        self.version(10.0)
        orden = self.orden()
        primero = self.anticipo(orden, advance_payment_method='percentage', amount=33.33)
        segundo = self.anticipo(orden, advance_payment_method='percentage', amount=33.33)
        tercero = self.anticipo(orden, advance_payment_method='percentage', amount=33.34)
        for factura in (primero, segundo, tercero):
            self.assertNormal(factura, 'un tercio del pedido')

    def test_una_nota_de_credito_no_senala_la_venta(self):
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.nota(factura, 200.0)
        venta._reconciliar()
        self.assertEqual(venta.devuelto_centavos, 20000, 'la nota sí se mide')
        self.assertFalse(venta.facturado_distinto, 'pero una devolución no es «distinto del pedido»')

    def test_la_reversa_completa_de_la_factura_tampoco_la_senala(self):
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.revertir(factura, 'Devolución de prueba')
        venta._reconciliar()
        self.assertFalse(venta.facturado_distinto)

    def test_una_factura_parcial_y_la_que_completa_el_pedido_no_se_senalan(self):
        """Se factura primero una parte de las unidades y después el resto: cada factura sale igual del pedido."""
        self.version(10.0)
        orden = self.orden(lineas=[(self.mueble, 1000.0, 3, {})])
        primera = orden._create_invoices()
        primera.invoice_date = DIA
        primera.invoice_line_ids.quantity = 1
        primera.action_post()
        self.pagar(primera)
        self.assertNormal(primera, 'factura de 1 de 3 unidades')
        segunda = orden._create_invoices()
        segunda.invoice_date = DIA
        self.assertEqual(segunda.invoice_line_ids.quantity, 2)
        segunda.action_post()
        self.pagar(segunda)
        self.assertNormal(segunda, 'factura de las 2 unidades que faltaban')

    def test_lo_que_no_es_del_sitio_no_se_senala_ni_se_mide(self):
        """Una factura de mostrador con un precio raro no es una venta del sitio: no entra ni se señala."""
        self.version(10.0)
        factura = self.venta_web(web=False)
        self.assertFalse(self.venta(factura))

    # --- el caso del revisor: editar la factura en borrador --------------------------------------------------------

    def test_editar_el_precio_la_cantidad_o_el_descuento_de_la_factura_en_borrador_senala_la_venta(self):
        """Caja, Gerencia y la vendedora (por el asistente de facturar) facturan un pedido de 1,000 que abrió un
        visitante, cambian la línea de la factura, la publican y la cobran. Antes: ninguna señal. Ahora: señalada, y
        lo que se paga no cambia (es una señal, no un freno)."""
        self.version(10.0)
        casos = {'precio 5000': ({'price_unit': 5000.0}, 500000), 'cantidad 5': ({'quantity': 5}, 500000),
                 'descuento 50': ({'discount': 50.0}, 50000), 'precio de 800 (a la baja)': ({'price_unit': 800.0}, 80000)}
        for rol, usuario in (('caja', self.u_caja), ('gerencia', self.u_gerencia), ('vendedora', self.u_vendedora)):
            for nombre, (cambio, base) in casos.items():
                with self.subTest(rol=rol, cambio=nombre):
                    orden = self.orden(creado_por=self.publico)          # el carrito lo abrió un VISITANTE
                    borrador = self.factura_en_borrador(orden, usuario)
                    borrador.invoice_line_ids.with_user(usuario).write(cambio)
                    venta = self.publicar_y_cobrar(borrador, usuario)
                    self.assertTrue(venta, 'cuenta como venta del sitio')
                    self.assertTrue(venta.facturado_distinto, 'ahora sí sale señalada')
                    self.assertFalse(venta.tocada_por_id or venta.creado_por_personal,
                                     'las otras señales siguen vacías: esta es la que faltaba')
                    self.assertEqual(venta.base_centavos, base, 'la señal no cambia lo que se paga')
                    self.assertEqual(venta.comision_centavos, base // 10)

    def test_un_anticipo_de_monto_fijo_mayor_que_el_pedido_senala_la_venta(self):
        """Odoo no le pone tope al anticipo de monto fijo: 5,000 sobre un pedido de 1,000 (base 4,672.90 sin ITBMS)."""
        self.version(10.0)
        for rol, usuario in (('caja', self.u_caja), ('gerencia', self.u_gerencia)):
            with self.subTest(rol=rol):
                orden = self.orden(creado_por=self.publico)
                factura = self.anticipo(orden, usuario, advance_payment_method='fixed', fixed_amount=5000.0)
                venta = self.venta(factura)
                self.assertTrue(venta.facturado_distinto)
                self.assertEqual((venta.base_centavos, venta.comision_centavos), (467290, 46729),
                                 'la señal no cambia lo que se paga')

    def test_un_anticipo_pasado_que_se_devuelve_con_una_nota_deja_de_senalar(self):
        """El anticipo se mide NETO de lo devuelto: si la nota de crédito lo deshace, ya no pasa del pedido."""
        self.version(10.0)
        orden = self.orden()
        factura = self.anticipo(orden, advance_payment_method='fixed', fixed_amount=5000.0)
        venta = self.venta(factura)
        self.assertTrue(venta.facturado_distinto)
        self.revertir(factura, 'Anticipo de más')
        venta._reconciliar()
        self.assertFalse(venta.facturado_distinto, 'con la nota publicada lo anticipado queda en cero')

    # --- la señal es de la medición: se mantiene al comparar y se ve en la pantalla --------------------------------

    def test_el_barrido_y_armar_no_cambian_la_senal_ni_anotan_nada(self):
        self.version(10.0)
        normal = self.venta_web()
        orden = self.orden(creado_por=self.publico)
        borrador = self.factura_en_borrador(orden)
        borrador.invoice_line_ids.price_unit = 5000.0
        inflada = self.publicar_y_cobrar(borrador)
        libro = self.libro().ids
        for _vez in range(2):
            self.Venta._barrido()
            self.Venta._poner_al_dia()
            for venta in self.Venta.search([]):
                venta._reconciliar()
        self.assertEqual((self.venta(normal).facturado_distinto, inflada.facturado_distinto), (False, True))
        self.assertEqual(self.libro().ids, libro, 'comparar otra vez no anota nada')

    def test_si_la_factura_vuelve_a_coincidir_con_el_pedido_la_senal_se_quita(self):
        """La señal se recalcula con lo que dice la factura hoy (como «una nota trae líneas sin producto»)."""
        self.version(10.0)
        orden = self.orden(creado_por=self.publico)
        borrador = self.factura_en_borrador(orden)
        borrador.invoice_line_ids.price_unit = 5000.0
        venta = self.publicar_y_cobrar(borrador)
        self.assertTrue(venta.facturado_distinto)
        pago = borrador._get_reconciled_payments()
        pago.action_cancel()
        borrador.button_draft()
        borrador.invoice_line_ids.price_unit = 1000.0
        borrador.action_post()
        self.pagar(borrador)
        self.assertFalse(venta.facturado_distinto)
        self.assertEqual(venta.base_centavos, 100000)

    def test_la_pantalla_trae_la_columna_el_aviso_y_el_filtro(self):
        self.version(10.0)
        orden = self.orden(creado_por=self.publico)
        borrador = self.factura_en_borrador(orden)
        borrador.invoice_line_ids.price_unit = 5000.0
        inflada = self.publicar_y_cobrar(borrador)
        normal = self.venta(self.venta_web())
        vistas = self.Venta.with_user(self.u_nomina).get_views([[False, 'list'], [False, 'form'], [False, 'search']])
        for tipo, esperado in (('list', "//field[@name='facturado_distinto']"), ('form', "//field[@name='facturado_distinto']"),
                               ('search', "//filter[@name='facturado_distinto']")):
            with self.subTest(vista=tipo):
                self.assertTrue(etree.fromstring(vistas['views'][tipo]['arch']).xpath(esperado), tipo)
        aviso = ' '.join(etree.fromstring(vistas['views']['form']['arch']).itertext())
        self.assertIn('no coincide con el pedido', aviso)
        self.assertIn('no cambia lo que se paga', aviso)
        encontradas = self.Venta.with_user(self.u_nomina).search([('facturado_distinto', '=', True)])
        self.assertEqual(encontradas, inflada)
        self.assertNotIn(normal, encontradas)

    def test_la_senal_solo_la_escribe_el_sistema(self):
        """Como todo lo de la venta: ni Nómina ni Gerencia la editan (ni la borran) a mano."""
        self.version(10.0)
        venta = self.venta(self.venta_web())
        for usuario in (self.u_nomina, self.u_gerencia, self.u_caja):
            self.rechaza(lambda usuario=usuario: venta.with_user(usuario).write({'facturado_distinto': True}))

    def test_una_factura_con_lineas_de_otro_pedido_solo_compara_las_online(self):
        """Si una factura junta un pedido online y uno de la tienda, solo cuenta (y se compara) lo online."""
        self.version(10.0)
        online = self.orden()
        mostrador = self.orden(web=False, lineas=[(self.mueble, 700.0, 1, {})])
        factura = (online | mostrador)._create_invoices(grouped=False)
        self.assertEqual(len(factura), 1)
        factura.invoice_date = DIA
        factura.invoice_line_ids.filtered(lambda ln: ln.sale_line_ids.order_id == mostrador).price_unit = 9000.0
        factura.action_post()
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertTrue(venta)
        self.assertEqual(venta.productos_centavos, 100000, 'solo la parte online')
        self.assertFalse(venta.facturado_distinto, 'cambiar la línea de mostrador no señala lo online')
