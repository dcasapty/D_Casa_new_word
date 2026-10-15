"""El paquete de impresión (factura + copia + nota de entrega) con el QR de uso interno, con wkhtmltopdf de verdad.

La copia de la empresa es la misma factura con la cinta «COPIA EMPRESA» arriba a la derecha: hereda el QR, que va al
final de la hoja, lejos de la cinta (no se pisan).
"""
import shutil
from unittest import skipUnless

from odoo.tests import tagged

from ..models import paquete
from .test_paquete import _flujo_de_la_pagina, textos_de_pdf_real, tiene_la_cinta
from .test_paquete_http import PaqueteHttpComun


@tagged('post_install', '-at_install')
@skipUnless(shutil.which('wkhtmltopdf'), 'sin wkhtmltopdf (la imagen Docker lo comprueba en CI)')
class TestPaqueteConQr(PaqueteHttpComun):

    def _armar(self, factura):
        contenido, _nombre = self.env['dcasa.impresion.paquete'].with_context(force_report_rendering=True)._armar_pdf(
            factura, ['cliente', 'copia', 'entrega'])
        return contenido

    def test_con_el_interruptor_encendido_la_factura_la_copia_y_la_entrega_llevan_qr_y_la_cinta_sigue_legible(self):
        _pedido, factura = self._venta()
        self.env.company.dcasa_mostrar_qr_documentos = True
        contenido = self._armar(factura)
        flujos = [_flujo_de_la_pagina(pagina) for pagina in paquete._paginas(paquete._leer(contenido))]
        self.assertEqual(len(flujos), 3)
        self.assertEqual([tiene_la_cinta(flujo) for flujo in flujos], [False, True, False],
                         'la cinta COPIA EMPRESA sigue solo en la copia')
        paginas = textos_de_pdf_real(contenido)
        if paginas is not None:
            self.assertEqual(len(paginas), 3, 'el QR no agrega páginas')
            for pagina in paginas:
                self.assertIn('USO INTERNO', pagina)
            self.assertIn('COPIA EMPRESA', paginas[1])
            self.assertNotIn('COPIA EMPRESA', paginas[0] + paginas[2])

    def test_apagado_el_paquete_sale_sin_qr(self):
        _pedido, factura = self._venta()
        self.env.company.dcasa_mostrar_qr_documentos = False
        paginas = textos_de_pdf_real(self._armar(factura))
        if paginas is not None:
            self.assertEqual(len(paginas), 3)
            self.assertNotIn('USO INTERNO', ''.join(paginas))
