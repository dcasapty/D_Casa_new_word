"""El papel del abono: una factura con algo pagado y algo por pagar sale como ABONO, con el saldo en grande.

Lo pidió la dueña (16 oct 2026): «cuando haga un abono, que en la factura diga abono y que diga saldo». Nada de la
contabilidad cambia: la factura es la misma (con su ITBMS), cada abono es un pago parcial con «Pagar», y aquí solo
se comprueba lo que se imprime. Todas las cifras salen de ``_dcasa_estado_abono`` (la misma fuente que «Mi cuenta»).

* Con un pago parcial: título «Abono» + número, recuadro «SALDO POR PAGAR», «Pagado $X de $Y», «Inicio del abono» y
  «El abono vence» en los datos, y si el plazo pasó, «El plazo venció el …» (sin multas: el sistema no cobra nada).
* Pagada por completo o sin pagos: «Factura» como siempre. Notas de crédito y facturas de proveedor: sin cambios.
* Imprimir u ofrecer el papel no cambia ni un asiento.
"""
import re
import shutil
from unittest import skipUnless
from unittest.mock import patch

from lxml import html as lxml_html

from odoo import Command, fields
from odoo.tests import HttpCase, tagged

from ..models.account_move import PARAMETRO_MESES_ABONO
from ..wizard.impresion_paquete import DcasaImpresionPaquete
from .documentos import DocumentosDePrueba
from .test_paquete import _renderizar_falso, textos, textos_de_pdf_real

INFORME_FACTURA = 'account.report_invoice_with_payments'   # el del botón «Imprimir» de la factura
INFORME_SIN_PAGOS = 'account.report_invoice'


def _texto(elemento):
    return ' '.join(elemento.text_content().split()) if elemento is not None else ''


def _monto(valor):
    """Como se imprime un monto en el papel: «$1,070.50» (pegado al símbolo)."""
    return f'${valor:,.2f}'


@tagged('post_install', '-at_install')
class TestPapelDelAbono(DocumentosDePrueba):
    """La factura «completa» de los documentos aprobados (hoy = 14/10/2026, reloj fijo) con uno o varios abonos."""

    def _abonar(self, factura, monto, fecha='2026-10-14'):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': fecha, 'amount': monto, 'journal_id': self.banco.id})._create_payments()

    def _papel(self, registro, informe=INFORME_FACTURA):
        """(título, recuadro del saldo, {etiqueta: valor} de los datos, texto de toda la hoja) del HTML impreso."""
        arbol = lxml_html.document_fromstring(self.html(informe, registro, normalizado=False))
        titulo = _texto(arbol.find('.//h2'))
        recuadro = arbol.xpath('//div[@name="dcasa_saldo"]')
        datos = {_texto(fila.find('th')): _texto(fila.find('td'))
                 for fila in arbol.xpath('//table[contains(@class, "o_dcasa_tabla_datos")]//tr')}
        return titulo, recuadro[0] if recuadro else None, datos, _texto(arbol.find('body'))

    # --- Con un abono -------------------------------------------------------------------------

    def test_un_abono_sale_como_abono_con_su_saldo(self):
        factura = self.factura_completa(abono=100.0)
        self.assertTrue(factura._dcasa_es_abono())
        estado = factura._dcasa_estado_abono()
        titulo, recuadro, datos, hoja = self._papel(factura)

        self.assertTrue(titulo.startswith('Abono'), titulo)
        self.assertIn(factura.name, titulo, 'el número de la factura sigue visible')
        self.assertNotIn('Factura', titulo)

        self.assertIsNotNone(recuadro, 'falta el recuadro «SALDO POR PAGAR»')
        texto = _texto(recuadro)
        self.assertTrue(texto.startswith('SALDO POR PAGAR'), texto)
        self.assertIn(_monto(estado['saldo']), texto)
        self.assertIn(f"Pagado {_monto(100.0)} de {_monto(factura.amount_total)}", texto)
        self.assertEqual(estado['saldo'], factura.amount_residual)
        self.assertNotIn('venció', texto, 'el plazo aún no vence')
        self.assertEqual(recuadro.xpath('.//div[contains(@class, "o_dcasa_saldo_monto")]')[0].text_content().strip(),
                         _monto(estado['saldo']), 'el saldo va en grande, solo')

        # La lista de abonos de siempre se mantiene.
        self.assertIn('Abono del 14/10/2026 · Banco de prueba', hoja)

        # Datos: el plazo del abono en lugar del «Vence» de la condición de pago.
        self.assertEqual(datos['Inicio del abono'], '14/10/2026')
        self.assertEqual(datos['El abono vence'], '14/11/2026', 'un mes desde el primer abono (parámetro de la dueña)')
        self.assertNotIn('Vence', datos)
        self.assertIn('Condiciones', datos, 'lo demás de los datos sigue')

    def test_el_saldo_se_escribe_en_el_recuadro_con_cada_abono(self):
        factura = self.factura_completa(abono=100.0)
        self._abonar(factura, 50.0, '2026-10-14')
        self.assertTrue(factura._dcasa_es_abono())
        _titulo, recuadro, datos, hoja = self._papel(factura)
        self.assertIn(_monto(factura.amount_residual), _texto(recuadro))
        self.assertIn(f"Pagado {_monto(150.0)} de", _texto(recuadro))
        self.assertEqual(hoja.count('Abono del 14/10/2026'), 2)
        self.assertEqual(datos['Inicio del abono'], '14/10/2026', 'el plazo cuenta desde el PRIMER abono')

    def test_plazo_vencido_lo_dice_sin_cobrar_nada(self):
        factura = self.factura_completa(abono=0)
        self._abonar(factura, 100.0, '2026-08-01')
        estado = factura._dcasa_estado_abono()
        self.assertTrue(estado['vencido'])
        residuo = factura.amount_residual
        _titulo, recuadro, datos, _hoja = self._papel(factura)
        self.assertIn('El plazo venció el 01/09/2026', _texto(recuadro))
        self.assertEqual(datos['El abono vence'], '01/09/2026')
        self.assertIn(_monto(residuo), _texto(recuadro), 'el saldo es el mismo: no se suma nada por vencer')
        self.assertEqual(factura.amount_residual, residuo)
        for palabra in ('multa', 'recargo', 'interés', 'penalidad'):
            self.assertNotIn(palabra, _texto(recuadro).lower())

    def test_sin_plazo_configurado_no_dice_cuando_vence(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAMETRO_MESES_ABONO, '0')
        factura = self.factura_completa(abono=100.0)
        titulo, recuadro, datos, _hoja = self._papel(factura)
        self.assertTrue(titulo.startswith('Abono'))
        self.assertEqual(datos['Inicio del abono'], '14/10/2026')
        self.assertNotIn('El abono vence', datos)
        self.assertNotIn('Vence', datos)
        self.assertNotIn('venció', _texto(recuadro))

    def test_el_informe_sin_pagos_tambien_dice_abono(self):
        """«Imprimir» sin pagos (el otro informe de Odoo): el título y el saldo son los mismos."""
        factura = self.factura_completa(abono=100.0)
        titulo, recuadro, _datos, _hoja = self._papel(factura, INFORME_SIN_PAGOS)
        self.assertTrue(titulo.startswith('Abono'), titulo)
        self.assertIn(_monto(factura.amount_residual), _texto(recuadro))

    # --- Lo demás, como siempre ---------------------------------------------------------------

    def test_pagada_por_completo_dice_factura_con_sus_abonos(self):
        factura = self.factura_completa(abono=100.0)
        self._abonar(factura, factura.amount_residual)
        self.assertTrue(factura._dcasa_is_paid())
        titulo, recuadro, datos, hoja = self._papel(factura)
        self.assertTrue(titulo.startswith('Factura'), titulo)
        self.assertIsNone(recuadro)
        self.assertEqual(hoja.count('Abono del 14/10/2026'), 2, 'la lista de abonos sigue')
        self.assertNotIn('Inicio del abono', datos)
        self.assertNotIn('Vence', datos)

    def test_sin_pagos_dice_factura_y_vence(self):
        factura = self.factura_completa(abono=0)
        self.assertFalse(factura._dcasa_es_abono())
        titulo, recuadro, datos, hoja = self._papel(factura)
        self.assertTrue(titulo.startswith('Factura'), titulo)
        self.assertIsNone(recuadro)
        self.assertEqual(datos['Vence'], '14/10/2026', 'la condición de pago manda, como siempre')
        self.assertNotIn('Inicio del abono', datos)
        self.assertNotIn('SALDO POR PAGAR', hoja)

    def test_nota_de_credito_con_pago_parcial_sigue_igual(self):
        # Una nota de crédito suelta (sin cruzarla con su factura) a la que se le devuelve al cliente una parte.
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': self.cama.id, 'quantity': 1, 'price_unit': 158.02})]})
        nota.action_post()
        self._abonar(nota, 20.0)
        self.assertEqual(nota.payment_state, 'partial')
        self.assertFalse(nota._dcasa_es_abono())
        titulo, recuadro, datos, _hoja = self._papel(nota)
        self.assertTrue(titulo.startswith('Nota de crédito'), titulo)
        self.assertIsNone(recuadro)
        self.assertNotIn('Inicio del abono', datos)
        self.assertFalse(nota._get_report_base_filename().startswith('Abono'))

    def test_factura_de_proveedor_con_pago_parcial_sigue_igual(self):
        proveedor = self.env['res.partner'].create({'name': 'PROVEEDOR ABONO'})
        compra = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': proveedor.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': self.cama.id, 'quantity': 1, 'price_unit': 60.0})]})
        compra.action_post()
        self._abonar(compra, 10.0)
        self.assertEqual(compra.payment_state, 'partial')
        self.assertFalse(compra._dcasa_es_abono())
        titulo, recuadro, datos, _hoja = self._papel(compra)
        self.assertNotIn('Abono', titulo)
        self.assertIsNone(recuadro)
        self.assertNotIn('Inicio del abono', datos)
        self.assertFalse(compra._get_report_base_filename().startswith('Abono'))

    # --- El nombre del PDF --------------------------------------------------------------------

    def test_el_pdf_de_un_abono_se_llama_abono(self):
        factura = self.factura_completa(abono=100.0)
        self.assertEqual(factura._get_report_base_filename(), f'Abono {factura.name}')
        informe = self.env.ref('account.account_invoices')
        self.assertTrue(factura._get_invoice_report_filename(report=informe).startswith('Abono'))
        # Pagada: el nombre de siempre (el número), sin «Abono».
        self._abonar(factura, factura.amount_residual)
        self.assertEqual(factura._get_report_base_filename(), factura.name)
        sin_pagos = self.factura_completa(abono=0)
        self.assertEqual(sin_pagos._get_report_base_filename(), sin_pagos.name)

    # --- Imprimir no toca la contabilidad -----------------------------------------------------

    def test_imprimir_el_abono_no_cambia_ni_un_asiento(self):
        factura = self.factura_completa(abono=100.0)

        def foto():
            lineas = self.env['account.move.line'].search([], order='id')
            return (
                [(linea.id, linea.move_id.id, linea.account_id.id, linea.debit, linea.credit, linea.balance,
                  linea.amount_residual, linea.reconciled, linea.tax_ids.ids) for linea in lineas],
                self.env['account.partial.reconcile'].search_count([]),
                [(m.id, m.state, m.payment_state, m.amount_total, m.amount_residual)
                 for m in self.env['account.move'].search([], order='id')],
            )

        antes = foto()
        self._papel(factura)
        self._papel(factura, INFORME_SIN_PAGOS)
        factura._get_report_base_filename()
        factura._dcasa_estado_abono()
        cuadro = self.env['dcasa.impresion.paquete'].browse(factura.action_dcasa_imprimir_documentos()['res_id'])
        self.assertTrue(cuadro.con_saldo)
        cuadro.action_imprimir()
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = cuadro._armar_pdf(factura, ['cliente', 'copia'])
        self.assertEqual(len(textos(contenido)), 2)
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(foto(), antes)


@tagged('post_install', '-at_install')
class TestPapelDelAbonoEnPdf(HttpCase):
    """El PDF de verdad (wkhtmltopdf): la hoja dice ABONO y SALDO POR PAGAR."""

    @skipUnless(shutil.which('wkhtmltopdf') and shutil.which('pdftotext'), 'sin wkhtmltopdf o pdftotext')
    def test_el_pdf_dice_abono_y_saldo(self):
        cliente = self.env['res.partner'].create({'name': 'CLIENTE PDF ABONO'})
        producto = self.env['product.product'].create({'name': 'SOFÁ PDF ABONO', 'type': 'consu'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': producto.id, 'quantity': 1, 'price_unit': 500.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': fields.Date.today(), 'amount': 120.0})._create_payments()
        pdf, _tipo = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
            'account.account_invoices', factura.ids)
        texto = re.sub(r'\s+', ' ', ' '.join(textos_de_pdf_real(pdf)))
        self.assertIn('ABONO', texto)
        self.assertIn('SALDO POR PAGAR', texto)
        self.assertIn('$380.00', texto)
        self.assertIn('Pagado $120.00 de $500.00', texto)
