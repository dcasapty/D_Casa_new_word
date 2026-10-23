"""F5: los papeles que se lleva el cliente nombran los productos en formato título; por dentro siguen en MAYÚSCULAS.

Decisión de la dueña (2026-10-22): «Lo que ve el cliente: "Cama Queen Tapizada", y solo por dentro queden en
MAYÚSCULAS». La cotización, la factura y la nota de entrega (la de Odoo y la fácil de leer), con el código público
apagado o encendido. Lo guardado en las líneas no cambia.
"""
from lxml import html as lxml_html

from odoo.tests import tagged

from .documentos import DocumentosDePrueba

CAMA_GUARDADA, CAMA_CLIENTE = 'CAMA QUEEN GREY CON ESTANTES', 'Cama Queen Grey con Estantes'
COLCHON_GUARDADO, COLCHON_CLIENTE = 'COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO', 'Colchon Imperial Twin 3/4 Buen Sueño'


@tagged('post_install', '-at_install')
class TestNombresParaElClienteEnLosPapeles(DocumentosDePrueba):

    def _texto(self, informe, registros):
        arbol = lxml_html.document_fromstring(self.html(informe, registros, normalizado=False))
        for nodo in arbol.xpath('//script|//style'):
            nodo.drop_tree()
        return ' '.join(arbol.find('body').text_content().split())

    def assertParaElCliente(self, texto, donde):
        for cliente, guardado in ((CAMA_CLIENTE, CAMA_GUARDADA), (COLCHON_CLIENTE, COLCHON_GUARDADO)):
            self.assertIn(cliente, texto, donde)
            self.assertNotIn(guardado, texto, f'{donde}: el cliente no lee el nombre en MAYÚSCULAS')

    def test_cotizacion_y_factura(self):
        for codigo_publico in (False, True):
            self.interruptores(codigo_publico=codigo_publico)
            pedido = self.cotizacion()
            self.assertIn(CAMA_GUARDADA, ' '.join(pedido.order_line.mapped('name')), 'lo guardado no cambia')
            self.assertParaElCliente(self._texto('sale.report_saleorder', pedido), f'cotización {codigo_publico}')
            factura = self.factura_completa()
            self.assertParaElCliente(self._texto('account.report_invoice', factura), f'factura {codigo_publico}')

    def test_notas_de_entrega(self):
        for codigo_publico in (False, True):
            self.interruptores(codigo_publico=codigo_publico)
            for facil in (False, True):
                self.company.dcasa_entrega_facil = facil
                entrega = self.entrega()
                self.assertParaElCliente(self._texto('stock.report_deliveryslip', entrega),
                                         f'nota de entrega (fácil={facil}, código público={codigo_publico})')
                self.assertIn(CAMA_GUARDADA, ' '.join(entrega.move_ids.product_id.mapped('display_name')),
                              'en la pantalla de la entrega sigue en MAYÚSCULAS')
