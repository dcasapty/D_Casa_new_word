from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SociosCommon


@tagged('post_install', '-at_install')
class TestCompras(SociosCommon):

    # --- La factura pagada suma puntos, sola --------------------------------

    def test_factura_pagada_suma_puntos(self):
        factura = self.factura(precio=329.99)  # la factura real: $353.09 con ITBMS
        compra = factura.dcasa_compra_ids
        self.assertEqual(len(compra), 1)
        self.assertEqual((compra.monto_centavos, compra.puntos), (35309, 353))
        self.assertEqual(compra.reglas_version, 2)
        self.assertTrue(self.cliente.dcasa_socio_codigo, 'La ficha se abre sola con la primera compra')
        self.assertEqual(self.cliente.dcasa_celular, '60000002')
        self.assertEqual(self.cliente.dcasa_saldo, 353)

    def test_factura_sin_pagar_no_suma(self):
        factura = self.factura(pagar=False)
        self.assertFalse(factura.dcasa_compra_ids)
        self.assertEqual(factura._dcasa_puntos_por_ganar(), 107)
        self.pagar(factura)
        self.assertEqual(factura.dcasa_compra_ids.puntos, 107)

    def test_una_factura_una_carga(self):
        factura = self.factura()
        factura._invoice_paid_hook()
        self.assertEqual(len(self.env['dcasa.compra'].search([('move_id', '=', factura.id)])), 1)
        self.assertEqual(self.cliente.dcasa_saldo, 107)

    def test_por_debajo_del_minimo_se_registra_con_cero(self):
        factura = self.factura(precio=18.0)  # $19.26 con ITBMS
        self.assertEqual(factura.dcasa_compra_ids.puntos, 0)
        self.assertFalse(self.movimientos(self.cliente))

    def test_la_factura_impresa_lleva_los_puntos(self):
        factura = self.factura()
        html = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', factura.ids)[0].decode()
        self.assertIn('Socios D\'CASA', html)
        self.assertIn(self.cliente.dcasa_socio_codigo, html)
        self.assertIn('/socios', html)

    # --- Anular ---------------------------------------------------------------

    def test_nota_de_credito_total_devuelve_los_puntos(self):
        factura = self.factura()
        factura._reverse_moves([{'ref': 'Devolución'}], cancel=True)
        self.assertEqual(factura.dcasa_compra_ids.estado, 'anulada')
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.assertTrue(self.movimientos(self.cliente, 'reverso'))

    def test_nota_de_credito_parcial_descuenta_la_parte(self):
        factura = self.factura(precio=200.0)  # 214 puntos
        nota = factura._reverse_moves([{'ref': 'Devolución parcial'}])
        nota.invoice_line_ids.price_unit = 50.0  # devuelve $53.50
        nota.action_post()
        self.assertEqual(factura.dcasa_compra_ids.estado, 'activa')
        self.assertEqual(self.cliente.dcasa_saldo, 214 - 53)

    def test_factura_cancelada_o_a_borrador_anula_la_compra(self):
        factura = self.factura(pagar=False)
        self.pagar(factura)
        factura.button_draft()
        self.assertEqual(factura.dcasa_compra_ids.estado, 'anulada')
        self.assertEqual(self.cliente.dcasa_saldo, 0)

    def test_anular_pide_motivo(self):
        compra = self.factura().dcasa_compra_ids
        with self.assertRaises(UserError):
            compra._anular('  ', 'test')

    # --- Referidos -------------------------------------------------------------

    def test_referido_se_paga_con_la_primera_compra(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        compra = self.factura().dcasa_compra_ids
        self.assertEqual(compra.referido, 'pagado')
        self.assertEqual(self.padrino.dcasa_saldo, 500)
        self.assertEqual(self.cliente.dcasa_saldo, 107 + 250)
        self.assertTrue(self.cliente.dcasa_referido_pagado_en)
        segunda = self.factura().dcasa_compra_ids
        self.assertEqual(segunda.referido, 'ya-pagado')
        self.assertEqual(self.padrino.dcasa_saldo, 500)

    def test_sin_padrino_no_paga(self):
        self.assertEqual(self.factura().dcasa_compra_ids.referido, 'sin-padrino')

    def test_compra_que_no_da_puntos_no_estrena_a_nadie(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        self.assertEqual(self.factura(precio=10.0).dcasa_compra_ids.referido, 'no-califica')
        # ...y no quema el referido: la primera compra de verdad sí paga.
        self.assertEqual(self.factura().dcasa_compra_ids.referido, 'pagado')

    def test_anular_la_compra_deshace_el_referido_y_suelta_el_sello(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        factura = self.factura()
        factura._reverse_moves([{'ref': 'Devolución'}], cancel=True)
        self.assertEqual(self.padrino.dcasa_saldo, 0)
        self.assertEqual(self.cliente.dcasa_saldo, 0)
        self.assertFalse(self.cliente.dcasa_referido_pagado_en)
        self.assertEqual(self.factura().dcasa_compra_ids.referido, 'pagado', 'La compra de verdad sí paga')

    def test_padrino_suspendido_no_cobra(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        self.padrino.action_dcasa_suspender()
        self.assertEqual(self.factura().dcasa_compra_ids.referido, 'padrino-no-vale')

    def test_tope_de_ahijados(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        with self.reglas_con(referido__topeDeAhijadosPorPadrino=0):
            self.assertEqual(self.factura().dcasa_compra_ids.referido, 'tope-de-ahijados')

    def test_tope_del_mes_nunca_hace_fallar_la_venta(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        with self.reglas_con(referido__topeDePuntosPorPadrinoAlMes=400):
            compra = self.factura().dcasa_compra_ids
        self.assertEqual(compra.referido, 'tope-del-mes')
        self.assertEqual(compra.puntos, 107, 'La compra suma igual')

    # --- La venta propone el padrino ---------------------------------------------

    def test_venta_registra_el_padrino_una_sola_vez(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'dcasa_referido_por_id': self.padrino.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})],
        })
        orden.action_confirm()
        self.assertEqual(self.cliente.dcasa_referido_por_id, self.padrino)
        otro = self.env['res.partner'].create({'name': 'Luis'})
        otro._dcasa_asegurar_ficha()
        orden2 = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})],
        })
        self.assertEqual(orden2.dcasa_referido_por_id, self.padrino)
        self.assertTrue(orden2.dcasa_padrino_fijo)

    def test_nadie_es_su_propio_padrino(self):
        self.cliente._dcasa_asegurar_ficha()
        self.assertFalse(self.cliente._dcasa_asignar_padrino(self.cliente))
        self.cliente._dcasa_asignar_padrino(self.padrino)
        self.assertFalse(self.padrino._dcasa_asignar_padrino(self.cliente), 'No se invitan mutuamente')

    def test_quien_ya_compro_no_recibe_padrino(self):
        self.factura()
        self.assertFalse(self.cliente._dcasa_asignar_padrino(self.padrino))

    def test_compra_manual_de_la_transicion(self):
        wizard = self.env['dcasa.compra.manual.wizard'].create(
            {'partner_id': self.cliente.id, 'factura': 'F-000821', 'monto': 353.09})
        wizard.action_confirmar()
        self.assertEqual(self.cliente.dcasa_saldo, 353)
        repetida = self.env['dcasa.compra.manual.wizard'].create(
            {'partner_id': self.cliente.id, 'factura': 'f 821', 'monto': 353.09})
        with self.assertRaises(UserError):
            repetida.action_confirmar()
