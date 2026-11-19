"""Qué cuenta como venta online (la definición única de ``dcasa_base``) y cómo se mide cada caso.

Los casos de Gerencia (2026-11-19): compra en la página → cuenta; cotiza en la página y paga en la tienda → cuenta; toda
venta de Andrés → cuenta; Juan lo manda a la página y compra solo → cuenta; lo atiende una vendedora por Juan → NO
cuenta (aunque ella mande el enlace). Y lo de la tienda, nunca."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ComisionCommon


@tagged('post_install', '-at_install')
class TestVentaOnline(ComisionCommon):

    # ------------------------------------------------------------------ qué se mide

    def test_una_compra_en_la_pagina_se_mide_aunque_no_haya_reglas_ni_porcentaje(self):
        factura = self.venta_web()
        venta = self.venta(factura)
        self.assertEqual(len(venta), 1)
        self.assertEqual((venta.como_llego, venta.estado, venta.cobrada), ('web', 'medida', True))
        self.assertFalse(venta.reglas_id)
        self.assertEqual(venta.productos, 1000.0, 'sin ITBMS')
        self.assertEqual(venta.factura, factura.name)
        self.assertFalse(self.libro(), 'sin versión de reglas solo se mide: no hay libro')

    def test_una_factura_sin_pagar_o_pagada_a_medias_no_cuenta_hasta_que_se_completa(self):
        factura = self.venta_web(pagar=False)
        self.assertFalse(self.venta(factura))
        self.pagar(factura, monto=100.0)
        self.assertFalse(self.venta(factura), 'un abono a medias no cuenta')
        self.pagar(factura)
        self.assertEqual(len(self.venta(factura)), 1)

    def test_lo_de_la_tienda_no_cuenta(self):
        factura = self.venta_web(web=False)
        self.assertFalse(self.venta(factura))
        self.assertEqual(factura._dcasa_factor_online()[factura.id], 0.0)

    def test_cotiza_en_la_pagina_y_paga_en_la_tienda_cuenta(self):
        """El mismo pedido que nació en la página, apartado y pagado en el local por Caja (sin pago de la pasarela)."""
        orden = self.orden(pago='en_tienda')
        self.assertTrue(orden.dcasa_nacio_en_web and orden.dcasa_venta_online)
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual((venta.forma_pago, venta.como_llego), ('en_tienda', 'tienda'))

    def test_toda_venta_de_andres_cuenta_aunque_la_cierre_una_vendedora(self):
        orden = self.orden(vendedora=self.u_vendedora)
        orden._dcasa_escribir_marca(dcasa_via_andres=True)
        self.assertTrue(orden.dcasa_venta_online)
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual(venta.como_llego, 'andres')
        self.assertTrue(venta.atendida_por_vendedora, 'se mide cuántas pasan por una vendedora')

    def test_andres_manda_sobre_la_vendedora_que_hablo_con_el_cliente(self):
        self.hablar(self.cliente, 'vendedora', hace_dias=2)
        orden = self.orden(confirmar=False)
        orden._dcasa_escribir_marca(dcasa_via_andres=True)
        orden.action_confirm()
        self.assertFalse(orden.dcasa_llevada_por_vendedora, 'ni se mira: la venta es de Andrés')
        self.assertTrue(orden.dcasa_venta_online)

    def test_juan_lo_manda_a_la_pagina_y_la_persona_compra_sola_cuenta(self):
        self.hablar(self.cliente, 'bot', hace_dias=1)
        orden = self.orden()
        self.assertFalse(orden.dcasa_llevada_por_vendedora)
        self.assertTrue(orden.dcasa_venta_online)
        factura = self.facturar(orden)
        self.pagar(factura)
        self.assertEqual(self.venta(factura).como_llego, 'juan')

    def test_juan_y_la_atiende_una_vendedora_no_cuenta_aunque_ella_mande_el_enlace(self):
        self.hablar(self.cliente, 'bot', hace_dias=2)
        self.hablar(self.cliente, 'vendedora', hace_dias=1)
        orden = self.orden()
        self.assertTrue(orden.dcasa_nacio_en_web, 'el pedido sí salió de la página')
        self.assertTrue(orden.dcasa_llevada_por_vendedora, 'pero la llevó una vendedora')
        self.assertFalse(orden.dcasa_venta_online)
        factura = self.facturar(orden)
        self.pagar(factura)
        self.assertFalse(self.venta(factura), 'no es venta online: no se mide como del sitio')

    def test_una_vendedora_que_hablo_hace_mas_de_treinta_dias_no_llevo_esta_venta(self):
        self.hablar(self.cliente, 'vendedora', hace_dias=45)
        self.assertTrue(self.orden().dcasa_venta_online)

    def test_los_mensajes_del_cliente_y_otros_clientes_no_cuentan_como_vendedora(self):
        self.hablar(self.cliente, 'cliente', hace_dias=1)
        otro = self.env['res.partner'].create({'name': 'Otro cliente comisión', 'phone': '+507 6555-0302',
                                               'email': 'otro.comision@example.com'})
        self.hablar(otro, 'vendedora', hace_dias=1, id_externo='50761999002')
        self.assertTrue(self.orden().dcasa_venta_online)

    # ------------------------------------------------------------------ el testigo de origen

    def test_el_testigo_se_escribe_al_crear_y_nadie_lo_forja(self):
        tienda = self.orden(web=False, dcasa_nacio_en_web=True, dcasa_via_andres=True, dcasa_venta_online=True)
        self.assertFalse(tienda.dcasa_nacio_en_web, 'un pedido de la tienda no se hace pasar por la web')
        self.assertFalse(tienda.dcasa_via_andres)
        self.assertFalse(tienda.dcasa_venta_online)

    def test_el_testigo_no_se_cambia_ni_con_sudo(self):
        orden = self.orden()
        for marca in ('dcasa_nacio_en_web', 'dcasa_via_andres', 'dcasa_llevada_por_vendedora'):
            with self.subTest(marca=marca), self.assertRaisesRegex(UserError, 'lo pone el sistema'):
                orden.sudo().write({marca: not orden[marca]})
        self.assertTrue(orden.dcasa_nacio_en_web)

    def test_cambiar_el_sitio_despues_no_cambia_el_origen(self):
        orden = self.orden()
        orden.website_id = False
        self.assertTrue(orden.dcasa_nacio_en_web and orden.dcasa_venta_online)
        otra = self.orden(web=False)
        otra.website_id = self.website
        self.assertFalse(otra.dcasa_nacio_en_web, 'ponerle sitio a un pedido de la tienda no lo vuelve online')
        self.assertFalse(otra.dcasa_venta_online)

    def test_duplicar_un_pedido_de_la_pagina_no_copia_las_marcas(self):
        orden = self.orden()
        orden._dcasa_escribir_marca(dcasa_via_andres=True)
        copia = orden.copy()
        self.assertFalse(copia.dcasa_nacio_en_web or copia.dcasa_via_andres or copia.dcasa_venta_online)

    # ------------------------------------------------------------------ las líneas

    def test_una_factura_que_junta_un_pedido_web_con_otro_de_la_tienda_mide_solo_lo_web(self):
        web = self.orden(lineas=[(self.mueble, 1000.0, 1, {})])
        tienda = self.orden(web=False, lineas=[(self.mueble, 500.0, 1, {})])
        factura = (web | tienda)._create_invoices()
        factura.invoice_date = '2030-03-04'
        factura.action_post()
        self.assertEqual(len(factura), 1, 'las dos ventas salen en una sola factura')
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual(venta.productos, 1000.0, 'solo las líneas del pedido de la web')
        self.assertAlmostEqual(factura._dcasa_factor_online()[factura.id], 1000 / 1500)

    def test_los_componentes_separan_descuento_envio_e_itbms(self):
        orden = self.orden(lineas=[(self.mueble, 1000.0, 1, {}), (self.premio, -100.0, 1, {}),
                                   (self.envio, 50.0, 1, {'is_delivery': True})])
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual((venta.productos_centavos, venta.descuento_negativas_centavos, venta.envio_centavos),
                         (100000, 10000, 5000))
        self.assertEqual(venta.itbms_centavos, round(factura.amount_tax * 100))
        self.assertGreater(venta.itbms_centavos, 0)

    def test_el_descuento_de_cada_linea_se_guarda_para_calcular_antes_de_descuentos(self):
        orden = self.orden(lineas=[(self.mueble, 1000.0, 1, {'discount': 10.0})])
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual((venta.productos_centavos, venta.descuento_lineas_centavos), (90000, 10000))
