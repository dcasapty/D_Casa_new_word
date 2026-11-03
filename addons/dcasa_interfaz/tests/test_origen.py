"""De dónde salió cada cotización y cada factura (pedido de la dueña, 2026-11-03): «Web» si nació en la tienda en línea,
«Vendedora» si no; la factura hereda el origen de su pedido. El caso «Chatbot» (las que arma Juan) se prueba en
``dcasa_conversaciones`` (``test_origen_chatbot``)."""
from odoo.tests import tagged

from .test_inicio_por_rol import VentasCommon


@tagged('post_install', '-at_install')
class TestOrigen(VentasCommon):

    def test_una_cotizacion_de_ventas_es_de_una_vendedora(self):
        orden = self.pedido(confirmar=False)
        self.assertEqual(orden.dcasa_origen, 'vendedora')

    def test_una_de_la_tienda_en_linea_es_de_la_web_y_su_factura_tambien(self):
        orden = self.pedido(confirmar=False)
        orden.website_id = self.env['website'].search([], limit=1)
        self.assertEqual(orden.dcasa_origen, 'web')
        orden.action_confirm()
        factura = self.facturar(orden)
        self.assertEqual(factura.dcasa_origen, 'web')
        # Se filtra y se agrupa por origen, en Ventas y en Facturas.
        self.assertIn(orden, self.env['sale.order'].search([('dcasa_origen', '=', 'web')]))
        self.assertIn(factura, self.env['account.move'].search([('dcasa_origen', '=', 'web')]))

    def test_duplicar_un_pedido_de_la_web_es_de_una_vendedora(self):
        orden = self.pedido(confirmar=False)
        orden.website_id = self.env['website'].search([], limit=1)
        copia = orden.copy()
        self.assertFalse(copia.website_id)
        self.assertEqual(copia.dcasa_origen, 'vendedora')

    def test_la_factura_de_un_pedido_de_vendedora_y_la_hecha_a_mano(self):
        factura = self.facturar(self.pedido())
        self.assertEqual(factura.dcasa_origen, 'vendedora')
        a_mano = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.producto.id, 'quantity': 1, 'price_unit': 50})]})
        self.assertEqual(a_mano.dcasa_origen, 'vendedora', 'sin pedido: la hizo una persona')

    def test_una_factura_de_proveedor_no_tiene_origen(self):
        compra = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.cliente.id, 'invoice_date': self.hoy,
            'invoice_line_ids': [(0, 0, {'name': 'Flete', 'quantity': 1, 'price_unit': 10})]})
        self.assertFalse(compra.dcasa_origen)

    def test_las_vistas_muestran_el_origen(self):
        lista = self.env['sale.order'].get_view(self.env.ref('sale.view_quotation_tree').id, 'list')['arch']
        self.assertIn('dcasa_origen', lista)
        busqueda = self.env['account.move'].get_view(self.env.ref('account.view_account_invoice_filter').id,
                                                     'search')['arch']
        self.assertIn('dcasa_origen_chatbot', busqueda)
