"""El bloque Socios D'CASA de la factura impresa: cifras del libro, nunca a ojo."""
from html import unescape

from odoo.tests import tagged

from .common import SociosCommon


@tagged('post_install', '-at_install')
class TestFacturaImpresa(SociosCommon):

    def _render(self, registros, reporte='account.report_invoice'):
        # QWeb escapa el apóstrofo de «D'CASA» (&#39;); se deshace para leer el texto tal cual.
        return unescape(self.env['ir.actions.report']._render_qweb_html(reporte, registros.ids)[0].decode())

    def test_socio_con_factura_pagada_ve_codigo_puntos_y_saldo(self):
        factura = self.factura()  # $100 + ITBMS = $107 → 107 puntos
        html = self._render(factura)
        self.assertEqual(self.cliente.dcasa_saldo, 107)
        self.assertIn('Tu código de socio', html)
        self.assertIn(self.cliente.dcasa_socio_codigo, html)
        self.assertIn('Puntos de esta compra: <strong>107</strong>', html)
        self.assertIn('Tu saldo: <strong>107</strong>', html)
        self.assertNotIn('se acreditan al pagar', html)
        self.assertNotIn('Únete en', html)

    def test_socio_con_factura_sin_pagar_ve_lo_que_ganara(self):
        self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 300, 'test', motivo='Saldo de prueba')
        factura = self.factura(partner=self.padrino, pagar=False)
        html = self._render(factura)
        self.assertIn('Puntos de esta compra: <strong>107</strong> (se acreditan al pagar)', html)
        self.assertIn('Tu saldo hoy: <strong>300</strong>', html)
        self.assertNotIn('Únete en', html)

    def test_no_socio_recibe_invitacion_con_el_codigo_del_padrino(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'dcasa_referido_por_id': self.padrino.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1, 'price_unit': 100})],
        })
        orden.action_confirm()
        factura = orden._create_invoices()
        factura.action_post()
        self.assertFalse(self.cliente.dcasa_socio_codigo, 'Todavía no es socio: no ha pagado')
        html = self._render(factura)
        self.assertIn('Únete en', html)
        self.assertIn('/socios', html)
        self.assertIn(self.padrino.dcasa_socio_codigo, html)
        self.assertNotIn('Tu código de socio', html)
        self.assertNotIn('Puntos de esta compra', html)

    def test_no_socio_sin_padrino_solo_invitacion(self):
        factura = self.factura(pagar=False)
        html = self._render(factura)
        self.assertIn('Únete en', html)
        self.assertNotIn('quien te invitó', html)

    def test_premio_cobrado_sale_identificado(self):
        self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_10'))
        orden = self.env['sale.order'].create({
            'partner_id': self.padrino.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1, 'price_unit': 100})],
        })
        self.env['dcasa.cobrar.premio.wizard'].create({'order_id': orden.id, 'codigo': canje.codigo}).action_confirmar()
        orden.action_confirm()
        factura = orden._create_invoices()
        factura.action_post()
        html = self._render(factura)
        self.assertIn("Premio Socios D'CASA", html, 'La línea del premio lleva su distintivo')
        self.assertNotIn('o_dcasa_servicios', html, 'El premio es un descuento: se queda entre los muebles')
        linea_premio = factura.invoice_line_ids.filtered(lambda linea: linea.sale_line_ids.dcasa_canje_id)
        self.assertTrue(linea_premio)
        self.assertFalse(linea_premio._dcasa_va_aparte())
        self.assertNotIn('$-', html, 'El signo va delante del símbolo: -$9.35')
        self.assertIn('-$', html)
        self.assertIn('Premio cobrado en este pedido', html)
        self.assertIn(canje.premio_nombre, html)
        self.assertIn(canje.codigo, html)
        # El pedido impreso también lo identifica.
        self.assertIn("Premio Socios D'CASA", self._render(orden, 'sale.report_saleorder'))
