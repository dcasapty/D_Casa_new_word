"""La factura, la cotización y la nota de entrega de la dueña NO cambian con los interruptores apagados.

Es la regla máxima de este módulo: «la bonita factura» ya está aprobada. Cada documento se arma con datos fijos
(``documentos.py``), se pinta y se compara, letra por letra, con el HTML aprobado de ``tests/aprobado/``. Si alguien
toca las plantillas (``views/report_*.xml``) sin querer, este test falla y dice en qué línea.

Los PDF reales (wkhtmltopdf) salen de ese mismo HTML; además la comparación de imágenes se hace con
``comparar.py`` antes de entregar (ver docs/OPERACION.md, «Código QR y código público»).
"""
from odoo.tests import tagged

from .documentos import DocumentosDePrueba, comparar_con_lo_aprobado

INFORME_FACTURA = 'account.report_invoice_with_payments'   # el del botón «Imprimir» de la factura
INFORME_COTIZACION = 'sale.report_saleorder'
INFORME_ENTREGA = 'stock.report_deliveryslip'


@tagged('post_install', '-at_install')
class TestDocumentosIntactos(DocumentosDePrueba):

    def test_los_interruptores_vienen_apagados(self):
        campos = self.env['res.company']._fields
        for nombre in ('dcasa_mostrar_qr_documentos', 'dcasa_mostrar_codigo_publico'):
            self.assertFalse(campos[nombre].default(self.env['res.company']), nombre)
        self.assertFalse(self.company.dcasa_mostrar_qr_documentos)
        self.assertFalse(self.company.dcasa_mostrar_codigo_publico)

    def test_factura_completa_igual(self):
        factura = self.factura_completa()
        comparar_con_lo_aprobado(self, 'factura_completa', self.html(INFORME_FACTURA, factura))

    def test_factura_simple_pagada_igual(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'partner_shipping_id': self.entrega_partner.id, 'invoice_user_id': self.vendedora.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.colchon.id, 'quantity': 1, 'price_unit': 81.99})]})
        factura.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': '2026-10-14', 'journal_id': self.banco.id})._create_payments()
        comparar_con_lo_aprobado(self, 'factura_simple', self.html(INFORME_FACTURA, factura))

    def test_nota_de_credito_igual(self):
        factura = self.factura_completa(abono=0)
        nota = factura._reverse_moves([{'invoice_date': '2026-10-14', 'date': '2026-10-14'}])
        nota.action_post()
        comparar_con_lo_aprobado(self, 'nota_de_credito', self.html(INFORME_FACTURA, nota))

    def test_cotizacion_igual(self):
        comparar_con_lo_aprobado(self, 'cotizacion', self.html(INFORME_COTIZACION, self.cotizacion()))

    def test_pedido_confirmado_igual(self):
        comparar_con_lo_aprobado(
            self, 'pedido_confirmado', self.html(INFORME_COTIZACION, self.cotizacion(confirmar=True)))

    def test_nota_de_entrega_igual(self):
        comparar_con_lo_aprobado(self, 'nota_de_entrega', self.html(INFORME_ENTREGA, self.entrega()))
