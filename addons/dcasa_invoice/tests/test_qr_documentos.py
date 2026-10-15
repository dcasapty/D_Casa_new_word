"""El código QR de uso interno: qué dirección lleva, dónde se imprime y que, con el interruptor apagado, no existe.

La ruta que abre el QR (``/dcasa/doc/…``) se prueba en ``test_documento_ruta.py``; el Escáner, en ``dcasa_barras``.
"""
import base64
import io

from lxml import html as lxml_html
from PIL import Image

from odoo import Command
from odoo.tests import tagged

from ..models import documento
from .documentos import DocumentosDePrueba
from .test_documentos_intactos import INFORME_COMPRA, INFORME_COTIZACION, INFORME_ENTREGA, INFORME_FACTURA

BASE = 'https://erp.example.com'
QR_Y_SU_LIMPIEZA = ('dcasa_qr', 'dcasa_qr_limpio')   # los dos bloques que agrega el interruptor


def qr_del_html(contenido):
    """Los ``src`` de los QR de uso interno que trae el HTML de un informe."""
    return lxml_html.document_fromstring(contenido).xpath("//div[@name='dcasa_qr']//img/@src")


@tagged('post_install', '-at_install')
class TestQrDocumentos(DocumentosDePrueba):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('web.base.url', BASE)
        cls.proveedor = cls.env['res.partner'].create({'name': 'PROVEEDOR DE PRUEBA, S.A.', 'phone': '+507 300-0000'})

    def compra(self):
        pedido = self.env['purchase.order'].create({
            'partner_id': self.proveedor.id,
            'order_line': [Command.create({'product_id': self.colchon.id, 'product_qty': 3, 'price_unit': 60.0})]})
        pedido.button_confirm()
        return pedido

    def png(self, src):
        self.assertTrue(src.startswith('data:image/png;base64,'))
        return base64.b64decode(src.split(',', 1)[1])

    def esperado(self, url):
        return self.env['ir.actions.report'].barcode(
            'QR', url, width=documento.QR_PIXELES, height=documento.QR_PIXELES, quiet=0, barLevel=documento.QR_NIVEL)

    # --- La dirección --------------------------------------------------------------------------

    def test_la_direccion_de_cada_tipo_de_documento(self):
        factura, pedido, compra = self.factura_completa(), self.cotizacion(), self.compra()
        entrega = self.entrega()
        for registro, tipo in ((factura, 'FAC'), (pedido, 'COT'), (compra, 'COM'), (entrega, 'ENT')):
            self.assertEqual(registro._dcasa_qr_url(), f'{BASE}/dcasa/doc/{tipo}/{registro.name}', tipo)
        self.assertRegex(factura._dcasa_qr_url(), r'/dcasa/doc/FAC/[A-Z]*INV/\d{4}/\d{5}$')
        self.assertRegex(entrega._dcasa_qr_url(), r'/dcasa/doc/ENT/\w+/OUT/\d+$')

    def test_la_nota_de_credito_es_una_factura(self):
        nota = self.factura_completa(abono=0)._reverse_moves([{'invoice_date': '2026-10-14', 'date': '2026-10-14'}])
        nota.action_post()
        self.assertEqual(nota._dcasa_qr_tipo(), 'FAC')
        self.assertEqual(nota._dcasa_qr_url(), f'{BASE}/dcasa/doc/FAC/{nota.name}')

    def test_la_direccion_no_lleva_datos_del_cliente(self):
        """Uso interno y cero datos del cliente: solo el tipo y el número del documento."""
        for registro in (self.factura_completa(), self.cotizacion(), self.entrega()):
            url = registro._dcasa_qr_url()
            resto = url.removeprefix(f'{BASE}/dcasa/doc/')
            self.assertEqual(resto, f'{registro._dcasa_qr_tipo()}/{registro.name}')
            for dato in ('CLIENTE', 'PRUEBA', '8-000-0000', '61234567', 'cliente@example.com', 'Balboa', 'Karen',
                         'Ana', '100', '352'):
                self.assertNotIn(dato, url, dato)

    def test_sin_direccion_del_sistema_no_hay_qr(self):
        self.interruptores(qr=True)
        factura = self.factura_completa()
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', '')
        self.assertEqual(factura._dcasa_qr_url(), '')
        self.assertEqual(factura._dcasa_qr_src(), '')

    def test_las_referencias_raras_se_escapan_y_las_barras_se_dejan(self):
        url = documento.url_del_documento
        self.assertEqual(url(BASE, 'FAC', 'INV/2026/00001'), f'{BASE}/dcasa/doc/FAC/INV/2026/00001')
        self.assertEqual(url(f'{BASE}/', 'ENT', 'WH/OUT/00005'), f'{BASE}/dcasa/doc/ENT/WH/OUT/00005')
        self.assertEqual(url(BASE, 'COT', 'S 7?x#y'), f'{BASE}/dcasa/doc/COT/S%207%3Fx%23y')
        self.assertEqual(url('', 'COT', 'S00007'), '')
        self.assertEqual(url(BASE, 'XXX', 'S00007'), '')
        self.assertEqual(url(BASE, 'COT', ''), '')

    def test_leer_la_direccion(self):
        validas = {
            f'{BASE}/dcasa/doc/FAC/INV/2026/00001': ('FAC', 'INV/2026/00001'),
            '/dcasa/doc/ENT/WH/OUT/00005': ('ENT', 'WH/OUT/00005'),
            'http://localhost:8069/dcasa/doc/COT/S00007': ('COT', 'S00007'),
            'erp.example.com/dcasa/doc/COM/P00012': ('COM', 'P00012'),
            f'{BASE}/dcasa/doc/cot/S00007?utm=1#x': ('COT', 'S00007'),
            f'  {BASE}/dcasa/doc/FAC/INV%2F2026%2F00001\r\n': ('FAC', 'INV/2026/00001'),
            f'{BASE}/dcasa/doc/COT/S00007/': ('COT', 'S00007'),
        }
        for texto, esperado in validas.items():
            self.assertEqual(documento.leer_url(texto), esperado, texto)
        for texto in ('', 'DC0001', 'DC-K7M4PX', 'ZZT-CAMA-1', '7501234567890', f'{BASE}/dcasa/doc/',
                      f'{BASE}/dcasa/doc/FAC', f'{BASE}/dcasa/doc/FAC/', f'{BASE}/dcasa/doc/XXX/S00007',
                      f'{BASE}/otra/ruta/FAC/S00007', 'una frase /dcasa/doc/FAC/INV/1',
                      f'{BASE}/dcasa/doc/FAC/' + 'X' * 100, f'{BASE}/' + 'a' * 500, None, 7, ['x']):
            self.assertIsNone(documento.leer_url(texto), texto)

    def test_leer_la_direccion_con_los_simbolos_cambiados_por_el_lector(self):
        """Un lector con la distribución equivocada cambia «/» por «-», «:» por «Ñ»…: letras y números llegan."""
        tolerante = documento.leer_url_tolerante
        self.assertEqual(tolerante('httpsÑ--erp.example.com-dcasa-doc-FAC-INV-2026-00001'), ('FAC', 'INV202600001'))
        self.assertEqual(tolerante('https://erp.example.com/dcasa/doc/ent/wh/out/00005'), ('ENT', 'WHOUT00005'))
        self.assertEqual(tolerante('httpsÑ--x.co-DCASA_DOC_COT_S00007'), ('COT', 'S00007'))
        for texto in ('', 'DC0001', 'dcasapty.com', 'dcasa doc', 'httpsÑ--x.co-dcasa-doc-XXX-S00007',
                      'httpsÑ--x.co-dcasa-doc-FAC-', 'dcasa-doc-FAC-' + 'A' * 100, None, 3):
            self.assertIsNone(tolerante(texto), texto)

    # --- Con el interruptor apagado: nada --------------------------------------------------------

    def test_apagado_no_hay_qr_en_factura_cotizacion_ni_entrega(self):
        self.interruptores(qr=False)
        for informe, registro in ((INFORME_FACTURA, self.factura_completa()), (INFORME_COTIZACION, self.cotizacion()),
                                  (INFORME_ENTREGA, self.entrega())):
            contenido = self.html(informe, registro, normalizado=False)
            self.assertNotIn('o_dcasa_qr', contenido, informe)
            self.assertNotIn('Uso interno', contenido, informe)
            self.assertEqual(registro._dcasa_qr_src(), '')

    # --- Encendido: aparece el QR y no cambia nada más ----------------------------------------------

    def test_encendido_aparece_el_qr_y_no_cambia_nada_mas(self):
        """Con el interruptor encendido el documento es el MISMO, más el bloque del QR."""
        nota = self.factura_completa(abono=0)._reverse_moves([{'invoice_date': '2026-10-14', 'date': '2026-10-14'}])
        nota.action_post()
        casos = [(INFORME_FACTURA, self.factura_completa()), (INFORME_FACTURA, nota),
                 (INFORME_COTIZACION, self.cotizacion()), (INFORME_COTIZACION, self.cotizacion(confirmar=True)),
                 (INFORME_ENTREGA, self.entrega())]
        for informe, registro in casos:
            self.interruptores(qr=False)
            apagado = self.html(informe, registro)
            self.interruptores(qr=True)
            encendido_crudo = self.html(informe, registro, normalizado=False)
            fuentes = qr_del_html(encendido_crudo)
            self.assertEqual(len(fuentes), 1, f'{informe} {registro.name}: debe haber un solo QR')
            self.assertEqual(self.png(fuentes[0]), self.esperado(registro._dcasa_qr_url()))
            self.assertIn('Uso interno', encendido_crudo)
            self.assertEqual(self.html(informe, registro, quitar=QR_Y_SU_LIMPIEZA), apagado,
                             f'{informe} {registro.name}: con el QR encendido cambió algo más que el QR')

    def test_donde_va_el_qr(self):
        """Con textos de garantía/cambios/términos, a su derecha (no pide más alto en la hoja); sin ellos, al final."""
        self.interruptores(qr=True)
        for informe, registro in ((INFORME_FACTURA, self.factura_completa()), (INFORME_COTIZACION, self.cotizacion())):
            arbol = lxml_html.document_fromstring(self.html(informe, registro, normalizado=False))
            self.assertEqual(len(arbol.xpath("//div[@name='dcasa_legales']//div[@name='dcasa_qr']")), 1, informe)
            self.assertEqual(len(arbol.xpath("//div[@name='dcasa_qr']")), 1, informe)
        self.company.write({'dcasa_factura_garantia': False, 'dcasa_factura_cambios': False,
                            'dcasa_factura_terminos': False})
        for informe, registro in ((INFORME_FACTURA, self.factura_completa()), (INFORME_COTIZACION, self.cotizacion())):
            arbol = lxml_html.document_fromstring(self.html(informe, registro, normalizado=False))
            self.assertFalse(arbol.xpath("//div[@name='dcasa_legales']"), informe)
            self.assertEqual(len(arbol.xpath("//div[@name='dcasa_qr']")), 1, f'{informe}: sin textos va al final')

    def test_el_qr_es_una_imagen_cuadrada_y_distinta_por_documento(self):
        self.interruptores(qr=True)
        factura, otra = self.factura_completa(), self.factura_completa(abono=0)
        imagen = Image.open(io.BytesIO(self.png(factura._dcasa_qr_src())))
        self.assertEqual(imagen.size, (documento.QR_PIXELES, documento.QR_PIXELES))
        self.assertNotEqual(factura._dcasa_qr_src(), otra._dcasa_qr_src())
        self.assertEqual(factura._dcasa_qr_src(), factura._dcasa_qr_src(), 'el mismo documento, el mismo QR')

    def test_factura_en_borrador_no_lleva_qr(self):
        """Sin número no hay a dónde apuntar."""
        self.interruptores(qr=True)
        borrador = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': self.colchon.id, 'quantity': 1, 'price_unit': 10})]})
        self.assertEqual(borrador._dcasa_qr_src(), '')
        self.assertNotIn('o_dcasa_qr', self.html(INFORME_FACTURA, borrador, normalizado=False))

    def test_la_imagen_va_incrustada_no_se_pide_al_servidor(self):
        """Nada de ``/report/barcode/…``: el QR sale igual en el PDF, la vista previa y las pruebas."""
        self.interruptores(qr=True)
        contenido = self.html(INFORME_FACTURA, self.factura_completa(), normalizado=False)
        self.assertNotIn('/report/barcode', contenido)
        self.assertEqual(len(qr_del_html(contenido)), 1)

    # --- El pedido de compra: siempre ------------------------------------------------------------------

    def test_el_pedido_de_compra_siempre_lleva_su_qr(self):
        compra = self.compra()
        for encendido in (False, True):
            self.interruptores(qr=encendido)
            contenido = self.html(INFORME_COMPRA, compra, normalizado=False)
            fuentes = qr_del_html(contenido)
            self.assertEqual(len(fuentes), 1, f'interruptor {encendido}')
            self.assertEqual(self.png(fuentes[0]), self.esperado(f'{BASE}/dcasa/doc/COM/{compra.name}'))
            # El documento del proveedor sigue con lo suyo (la referencia del proveedor es la que él conoce).
            self.assertIn('IM-2001', contenido)
            self.assertIn('Uso interno', contenido)

    def test_el_pedido_de_compra_solo_agrega_el_bloque_del_qr(self):
        """El diseño del pedido de compra no se daña: quitado el bloque del QR queda el HTML aprobado
        (``test_documentos_intactos.test_pedido_de_compra_igual``)."""
        compra = self.compra()
        con_qr = self.html(INFORME_COMPRA, compra)
        self.assertIn('name="dcasa_qr"', con_qr)
        self.assertNotIn('dcasa_qr', self.html(INFORME_COMPRA, compra, quitar=('dcasa_qr',)))
