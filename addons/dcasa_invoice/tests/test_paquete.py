"""«Imprimir documentos»: el paquete de factura + copia de la empresa + nota de entrega en un solo PDF.

Lo que se comprueba, en orden: el PDF unido (de verdad, con wkhtmltopdf, en dos pruebas; con PDF de mentira en el
resto, para no gastar minutos), el orden de las páginas, el tope de facturas, los permisos, el asistente de
«Pagar» (completo ofrece el cuadro; parcial, apagado o con un fallo, todo como antes) y que lo que ya se
imprimía no cambió.
"""
import io
from unittest.mock import patch

from odoo import Command, fields
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import pdf

from ..models import paquete
from ..wizard.impresion_paquete import DcasaImpresionPaquete

MODELO = 'dcasa.impresion.paquete'


def pdf_falso(texto, paginas=1):
    """Un PDF de verdad (reportlab) con el texto en cada página: sirve para ver QUÉ documento es cada página."""
    from reportlab.lib.pagesizes import letter  # noqa: PLC0415
    from reportlab.pdfgen import canvas  # noqa: PLC0415
    salida = io.BytesIO()
    lienzo = canvas.Canvas(salida, pagesize=letter)
    for _n in range(paginas):
        lienzo.drawString(72, 700, texto)
        lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


def textos(contenido):
    """El texto de cada página de un PDF."""
    lector = pdf.PdfFileReader(io.BytesIO(contenido), strict=False)
    return [(getattr(pagina, 'extract_text', None) or pagina.extractText)() for pagina in lector.pages]


def _renderizar_falso(self, informe, registros):
    """Reemplaza al render real: {id: PDF de una página que dice qué informe y qué registro es}."""
    return {r.id: pdf_falso(f'{informe.report_name} | {r.display_name}') for r in registros}


class PaqueteComun(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.gerencia = crear_usuario(cls.env, 'paq_gerencia', 'dcasa_base.group_gerencia')
        cls.vendedora = crear_usuario(cls.env, 'paq_vendedora', 'dcasa_base.group_vendedora')
        cls.cliente = cls.env['res.partner'].create({
            'name': 'CLIENTE PAQUETE', 'vat': '8-000-0000', 'country_id': cls.env.ref('base.pa').id})
        cls.mueble = cls.env['product.product'].create({
            'name': 'CAMA PAQUETE', 'default_code': 'PQ-001', 'type': 'consu', 'is_storable': True,
            'list_price': 100.0})
        cls.Paquete = cls.env[MODELO]

    def _venta(self, publicar=True, cantidad=1):
        """(pedido, factura) de un pedido confirmado: trae su entrega de salida."""
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': cantidad})]})
        pedido.action_confirm()
        factura = pedido._create_invoices()
        if publicar:
            factura.action_post()
        return pedido, factura

    def _factura_proveedor(self):
        proveedor = self.env['res.partner'].create({'name': 'PROVEEDOR PAQUETE'})
        factura = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': proveedor.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 60.0})]})
        factura.action_post()
        return factura

    def _pagar(self, factura, monto=None, contexto=None):
        """Lo que hace el asistente de «Pagar»; devuelve lo que devuelve el botón «Crear pago»."""
        asistente = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids, **(contexto or {})).create({
                'payment_date': fields.Date.today(), **({'amount': monto} if monto else {})})
        return asistente.action_create_payments()


@tagged('post_install', '-at_install')
class TestPaquetePdf(PaqueteComun):

    # --- El PDF de verdad (wkhtmltopdf) ---------------------------------------------------------

    def test_pdf_de_una_venta_trae_factura_copia_y_entrega_en_orden(self):
        pedido, factura = self._venta()
        entrega = pedido.picking_ids
        self.assertEqual(entrega.picking_type_code, 'outgoing')
        contenido, nombre = self.Paquete.with_context(force_report_rendering=True)._armar_pdf(
            factura, ['cliente', 'copia', 'entrega'])
        self.assertTrue(contenido.startswith(b'%PDF'))
        self.assertEqual(nombre, f"Documentos-{factura.name.replace('/', '-')}.pdf")
        paginas = textos(contenido)
        self.assertEqual(len(paginas), 3, 'una factura, su copia y la nota de entrega')
        self.assertIn(factura.name, paginas[0])
        self.assertNotIn('COPIA EMPRESA', paginas[0], 'la del cliente va sin la cinta')
        self.assertIn(factura.name, paginas[1])
        self.assertIn('COPIA EMPRESA', paginas[1], 'la copia de la empresa lleva la cinta')
        self.assertIn(entrega.name, paginas[2])

    def test_pdf_de_varias_ventas_va_venta_por_venta(self):
        pedido_a, factura_a = self._venta()
        pedido_b, factura_b = self._venta(cantidad=2)
        contenido, nombre = self.Paquete.with_context(force_report_rendering=True)._armar_pdf(
            factura_a | factura_b, ['cliente', 'copia', 'entrega'])
        self.assertEqual(nombre, 'Documentos-2-facturas.pdf')
        paginas = textos(contenido)
        self.assertEqual(len(paginas), 6)
        esperado = [(factura_a.name, False), (factura_a.name, True), (pedido_a.picking_ids.name, False),
                    (factura_b.name, False), (factura_b.name, True), (pedido_b.picking_ids.name, False)]
        for pagina, (texto, con_cinta) in zip(paginas, esperado, strict=True):
            self.assertIn(texto, pagina)
            self.assertEqual('COPIA EMPRESA' in pagina, con_cinta, texto)

    # --- Qué entra y en qué orden (PDF de mentira, rápido) --------------------------------------

    def test_cada_documento_se_puede_dejar_fuera(self):
        _pedido, factura = self._venta()
        casos = {
            ('cliente',): 1, ('copia',): 1, ('entrega',): 1,
            ('cliente', 'copia'): 2, ('cliente', 'entrega'): 2, ('cliente', 'copia', 'entrega'): 3,
        }
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            for claves, paginas in casos.items():
                contenido, _nombre = self.Paquete._armar_pdf(factura, list(claves))
                self.assertEqual(len(textos(contenido)), paginas, claves)

    def test_el_orden_es_cliente_empresa_entrega_aunque_se_pida_al_reves(self):
        pedido, factura = self._venta()
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = self.Paquete._armar_pdf(factura, ['entrega', 'copia', 'cliente'])
        paginas = textos(contenido)
        self.assertIn('account.report_invoice_with_payments', paginas[0])
        self.assertNotIn('COPIA EMPRESA', paginas[0])
        self.assertIn('COPIA EMPRESA', paginas[1])
        self.assertIn('stock.report_deliveryslip', paginas[2])
        self.assertIn(pedido.picking_ids.name, paginas[2])

    def test_dos_facturas_del_mismo_pedido_no_repiten_la_entrega(self):
        pedido, factura = self._venta(cantidad=2)
        # Una segunda factura del mismo pedido (como un anticipo): cuelga de las mismas líneas de venta.
        segunda = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({
                'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 10.0,
                'sale_line_ids': [Command.set(pedido.order_line.ids)]})]})
        segunda.action_post()
        self.assertEqual(segunda._dcasa_entregas(), pedido.picking_ids)
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = self.Paquete._armar_pdf(factura | segunda, ['cliente', 'entrega'])
        paginas = textos(contenido)
        self.assertEqual(len(paginas), 3, 'dos facturas y la entrega, una sola vez')
        self.assertEqual(len([p for p in paginas if 'stock.report_deliveryslip' in p]), 1)

    def test_factura_sin_entrega_solo_lleva_factura_y_copia(self):
        cliente = self.env['res.partner'].create({'name': 'SIN ENTREGA'})
        servicio = self.env['product.product'].create({'name': 'Servicio paquete', 'type': 'service'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': servicio.id, 'quantity': 1, 'price_unit': 20.0})]})
        factura.action_post()
        self.assertFalse(factura._dcasa_entregas())
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _n = self.Paquete._armar_pdf(factura, ['cliente', 'copia', 'entrega'])
            self.assertEqual(len(textos(contenido)), 2)
            with self.assertRaisesRegex(UserError, 'no tienen una entrega ligada'):
                self.Paquete._armar_pdf(factura, ['entrega'])

    def test_entrega_cancelada_o_de_devolucion_no_sale(self):
        pedido, factura = self._venta()
        entrega = pedido.picking_ids
        self.assertEqual(factura._dcasa_entregas(), entrega)
        entrega.action_cancel()
        self.assertFalse(factura._dcasa_entregas())

    # --- Solo facturas de clientes publicadas ----------------------------------------------------

    def test_solo_facturas_de_clientes_publicadas(self):
        _pedido, publicada = self._venta()
        _otro, borrador = self._venta(publicar=False)
        proveedor = self._factura_proveedor()
        nota = publicada._reverse_moves([{'ref': 'nota'}])
        nota.action_post()
        validas, fuera = self.Paquete._separar_validas(publicada | borrador | proveedor | nota)
        self.assertEqual(validas, publicada)
        self.assertEqual(fuera, borrador | proveedor | nota)
        eleccion = self.env['account.move'].browse((publicada | borrador | proveedor).ids)
        accion = eleccion.action_dcasa_imprimir_documentos()
        cuadro = self.Paquete.browse(accion['res_id'])
        self.assertEqual(cuadro.move_ids, publicada)
        self.assertEqual(cuadro.omitidas, 2)
        self.assertIn('Se dejaron fuera 2', cuadro.aviso)
        with self.assertRaisesRegex(UserError, 'No hay facturas de clientes publicadas'):
            (borrador | proveedor).action_dcasa_imprimir_documentos()

    def test_el_cuadro_trae_las_tres_casillas_marcadas_y_la_entrega(self):
        pedido, factura = self._venta()
        accion = factura.action_dcasa_imprimir_documentos()
        self.assertEqual((accion['res_model'], accion['target'], accion['view_mode']), (MODELO, 'new', 'form'))
        cuadro = self.Paquete.browse(accion['res_id'])
        self.assertTrue(cuadro.incluir_cliente and cuadro.incluir_copia and cuadro.incluir_entrega)
        self.assertEqual(cuadro._claves_marcadas(), ['cliente', 'copia', 'entrega'])
        self.assertFalse(cuadro.tras_pago)
        self.assertIn(factura.name, cuadro.resumen)
        self.assertIn(pedido.picking_ids.name, cuadro.entregas_texto)
        self.assertFalse(cuadro.aviso)
        cuadro.incluir_copia = False
        self.assertEqual(cuadro._claves_marcadas(), ['cliente', 'entrega'])

    def test_imprimir_y_descargar_piden_el_pdf_al_servidor_sin_guardar_nada(self):
        _pedido, factura = self._venta()
        cuadro = self.Paquete.browse(factura.action_dcasa_imprimir_documentos()['res_id'])
        adjuntos = self.env['ir.attachment'].search_count([])
        for modo, boton in (('imprimir', cuadro.action_imprimir), ('descargar', cuadro.action_descargar)):
            accion = boton()
            self.assertEqual((accion['type'], accion['tag']), ('ir.actions.client', 'dcasa_paquete_pdf'))
            params = accion['params']
            self.assertEqual(params['modo'], modo)
            self.assertEqual(params['url'], f'/dcasa/paquete.pdf?facturas={factura.id}&docs=cliente,copia,entrega')
            self.assertEqual(params['nombre'], f"Documentos-{factura.name.replace('/', '-')}.pdf")
            self.assertEqual(params['next'], {'type': 'ir.actions.act_window_close'})
        self.assertEqual(self.env['ir.attachment'].search_count([]), adjuntos, 'el PDF no se guarda en la base')
        cuadro.write({'incluir_cliente': False, 'incluir_copia': False, 'incluir_entrega': False})
        with self.assertRaisesRegex(UserError, 'Marca al menos un documento'):
            cuadro.action_imprimir()

    # --- El tope --------------------------------------------------------------------------------

    def test_el_tope_de_facturas_por_paquete(self):
        self.assertEqual(paquete.MAX_FACTURAS, 20)
        facturas = self.env['account.move']
        for _n in range(3):
            facturas |= self._venta()[1]
        with patch.object(paquete, 'MAX_FACTURAS', 2):
            cuadro = self.Paquete.browse(facturas.action_dcasa_imprimir_documentos()['res_id'])
            self.assertTrue(cuadro.excede)
            self.assertIn('el máximo por paquete es 2', cuadro.aviso)
            with self.assertRaisesRegex(UserError, 'máximo por paquete es 2'):
                cuadro.action_imprimir()
            with self.assertRaisesRegex(UserError, 'máximo por paquete es 2'):
                self.Paquete._armar_pdf(facturas, ['cliente'])
            # Con dos entra.
            with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
                contenido, _nombre = self.Paquete._armar_pdf(facturas[:2], ['cliente'])
            self.assertEqual(len(textos(contenido)), 2)

    # --- Desde el pedido ------------------------------------------------------------------------

    def test_boton_del_pedido_solo_con_factura_publicada(self):
        pedido, factura = self._venta(publicar=False)
        self.assertFalse(pedido.dcasa_tiene_factura_publicada)
        with self.assertRaisesRegex(UserError, 'No hay facturas de clientes publicadas'):
            pedido.action_dcasa_imprimir_documentos()
        factura.action_post()
        pedido.invalidate_recordset()
        self.assertTrue(pedido.dcasa_tiene_factura_publicada)
        cuadro = self.Paquete.browse(pedido.action_dcasa_imprimir_documentos()['res_id'])
        self.assertEqual(cuadro.move_ids, factura)

    def test_varios_pedidos_los_que_no_tienen_factura_se_dejan_fuera(self):
        pedido_a, factura_a = self._venta()
        pedido_b, factura_b = self._venta()
        sin_factura = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]})
        cuadro = self.Paquete.browse((pedido_a | pedido_b | sin_factura).action_dcasa_imprimir_documentos()['res_id'])
        self.assertEqual(cuadro.move_ids, factura_a | factura_b)
        self.assertEqual(cuadro.omitidas, 1)

    # --- Permisos -------------------------------------------------------------------------------

    def test_la_vendedora_arma_el_paquete_de_una_factura_de_cliente(self):
        pedido, factura = self._venta()
        como_vendedora = factura.with_user(self.vendedora)
        accion = como_vendedora.action_dcasa_imprimir_documentos()
        cuadro = self.Paquete.with_user(self.vendedora).browse(accion['res_id'])
        self.assertEqual(cuadro.move_ids, factura)
        self.assertIn(pedido.picking_ids.name, cuadro.entregas_texto)
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = self.Paquete.with_user(self.vendedora)._armar_pdf(
                factura, ['cliente', 'copia', 'entrega'])
        self.assertEqual(len(textos(contenido)), 3)
        self.assertTrue(cuadro.action_imprimir()['params']['url'])
        pedido_vendedora = pedido.with_user(self.vendedora)
        self.assertTrue(pedido_vendedora.dcasa_tiene_factura_publicada)
        self.assertEqual(self.Paquete.browse(pedido_vendedora.action_dcasa_imprimir_documentos()['res_id']).move_ids,
                         factura)

    def test_la_vendedora_no_imprime_facturas_de_proveedores(self):
        proveedor = self._factura_proveedor()
        como_vendedora = self.env['account.move'].with_user(self.vendedora).browse(proveedor.id)
        with self.assertRaises(AccessError):
            como_vendedora.action_dcasa_imprimir_documentos()
        with self.assertRaises(AccessError):
            self.Paquete.with_user(self.vendedora)._armar_pdf(como_vendedora, ['cliente', 'copia'])

    def test_gerencia_tambien_puede(self):
        _pedido, factura = self._venta()
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = self.Paquete.with_user(self.gerencia)._armar_pdf(
                factura.with_user(self.gerencia), ['cliente', 'copia', 'entrega'])
        self.assertEqual(len(textos(contenido)), 3)

    def test_quien_no_ve_ventas_ni_inventario_obtiene_factura_y_copia(self):
        _pedido, factura = self._venta()
        lector = crear_usuario(self.env, 'paq_lector', 'account.group_account_readonly')
        self.assertFalse(self.env['sale.order'].with_user(lector).has_access('read'))
        self.assertFalse(factura.with_user(lector)._dcasa_entregas())
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            contenido, _nombre = self.Paquete.with_user(lector)._armar_pdf(
                factura.with_user(lector), ['cliente', 'copia', 'entrega'])
        self.assertEqual(len(textos(contenido)), 2)


@tagged('post_install', '-at_install')
class TestCopiaDeLaEmpresa(PaqueteComun):
    """La copia es la misma factura con una cinta: nada de plantillas nuevas ni cambios a la del cliente."""

    def test_sellar_copia_agrega_la_cinta_y_conserva_el_documento(self):
        original = pdf_falso('FACTURA ORIGINAL', paginas=2)
        sellado = paquete.sellar_copia(original)
        paginas = textos(sellado)
        self.assertEqual(len(paginas), 2, 'la cinta va en cada página y no agrega ni quita páginas')
        for pagina in paginas:
            self.assertIn('FACTURA ORIGINAL', pagina)
            self.assertIn('COPIA EMPRESA', pagina)
        self.assertNotIn('COPIA EMPRESA', ''.join(textos(original)))
        self.assertEqual(paquete.paginas(sellado), 2)

    def test_unir_respeta_el_orden_y_las_paginas(self):
        union = paquete.unir([pdf_falso('A', 2), pdf_falso('B'), b'', pdf_falso('C', 3)])
        letras = [pagina.strip()[:1] for pagina in textos(union)]
        self.assertEqual(letras, ['A', 'A', 'B', 'C', 'C', 'C'])

    def test_la_factura_del_cliente_sale_igual_que_siempre(self):
        _pedido, factura = self._venta()
        html = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', factura.ids)[0].decode()
        self.assertNotIn('COPIA EMPRESA', html, 'el informe de siempre no cambia: la cinta va solo en la copia')
        self.assertIn(factura.name, html)
        # El botón «Imprimir» de siempre sigue apuntando a su informe.
        accion = factura.action_print_pdf()
        self.assertEqual(accion['report_name'], 'account.report_invoice_with_payments')

    def test_no_se_crearon_informes_ni_plantillas_nuevas(self):
        """El paquete reutiliza los informes que ya existen: este módulo no agrega ni un informe."""
        propios = self.env['ir.model.data'].search_count([
            ('module', '=', 'dcasa_invoice'), ('model', '=', 'ir.actions.report')])
        self.assertEqual(propios, 0)
        entrega = self.env.ref('stock.action_report_delivery')
        self.assertEqual((entrega.report_name, entrega.model), ('stock.report_deliveryslip', 'stock.picking'))


@tagged('post_install', '-at_install')
class TestOfertaAlPagar(PaqueteComun):
    """El asistente de «Pagar»: pago completo ofrece el cuadro; todo lo demás, como antes."""

    def _es_el_cuadro(self, accion):
        return isinstance(accion, dict) and accion.get('res_model') == MODELO and accion.get('target') == 'new'

    def test_el_interruptor_viene_encendido(self):
        self.assertTrue(self.company.dcasa_ofrecer_impresion_pago)

    def test_pago_completo_ofrece_el_cuadro(self):
        _pedido, factura = self._venta()
        accion = self._pagar(factura)
        self.assertTrue(factura._dcasa_is_paid())
        self.assertTrue(self._es_el_cuadro(accion))
        cuadro = self.Paquete.browse(accion['res_id'])
        self.assertEqual(cuadro.move_ids, factura)
        self.assertTrue(cuadro.tras_pago)
        self.assertTrue(cuadro.incluir_cliente and cuadro.incluir_copia and cuadro.incluir_entrega)

    def test_desde_la_factura_odoo_no_redirige_al_pago_y_tambien_se_ofrece(self):
        """El botón «Pagar» de la factura trae dont_redirect_to_payments: Odoo cierra el asistente y se queda en la
        factura. Aquí es donde se ofrece el cuadro."""
        _pedido, factura = self._venta()
        accion = self._pagar(factura, contexto={'dont_redirect_to_payments': True, 'display_account_trust': True})
        self.assertTrue(self._es_el_cuadro(accion))
        cuadro = self.Paquete.browse(accion['res_id'])
        self.assertFalse(cuadro.pago_ids)
        self.assertEqual(cuadro.action_cerrar(), {'type': 'ir.actions.act_window_close'})

    def test_cerrar_muestra_el_pago_como_siempre(self):
        _pedido, factura = self._venta()
        accion = self._pagar(factura)
        cuadro = self.Paquete.browse(accion['res_id'])
        pago = self.env['account.payment'].search([('partner_id', '=', self.cliente.id)])
        self.assertEqual(len(pago), 1)
        self.assertEqual(cuadro.pago_ids, pago)
        siguiente = cuadro.action_cerrar()
        self.assertEqual((siguiente['res_model'], siguiente['res_id'], siguiente['view_mode']),
                         ('account.payment', pago.id, 'form'))
        # Y al imprimir o descargar, al terminar se muestra lo mismo.
        self.assertEqual(cuadro.action_imprimir()['params']['next'], siguiente)

    def test_pago_parcial_no_ofrece_nada(self):
        _pedido, factura = self._venta()
        for contexto in ({}, {'dont_redirect_to_payments': True}):
            accion = self._pagar(factura, monto=10.0, contexto=contexto)
            self.assertEqual(factura.payment_state, 'partial')
            self.assertFalse(self._es_el_cuadro(accion))
            if contexto:
                self.assertIs(accion, True, 'como siempre: el asistente se cierra')
            else:
                self.assertEqual(accion['res_model'], 'account.payment', 'como siempre: se muestra el pago')

    def test_el_pago_que_la_completa_ofrece_el_cuadro(self):
        _pedido, factura = self._venta()
        self._pagar(factura, monto=10.0)
        self.assertEqual(factura.payment_state, 'partial')
        self.assertTrue(self._es_el_cuadro(self._pagar(factura)))

    def test_apagado_el_interruptor_todo_es_como_antes(self):
        self.company.dcasa_ofrecer_impresion_pago = False
        _pedido, factura = self._venta()
        accion = self._pagar(factura)
        self.assertTrue(factura._dcasa_is_paid())
        self.assertFalse(self._es_el_cuadro(accion))
        self.assertEqual(accion['res_model'], 'account.payment')
        _otro, factura2 = self._venta()
        self.assertIs(self._pagar(factura2, contexto={'dont_redirect_to_payments': True}), True)

    def test_cobros_por_codigo_no_abren_ventanas(self):
        """Brian, Juan y las integraciones llaman a _create_payments: devuelve los pagos y nada más."""
        _pedido, factura = self._venta()
        asistente = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({'payment_date': fields.Date.today()})
        pagos = asistente._create_payments()
        self.assertEqual(pagos._name, 'account.payment')
        self.assertTrue(factura._dcasa_is_paid())
        self.assertFalse(self.Paquete.search([]), 'no se creó ningún cuadro')

    def test_la_factura_de_un_proveedor_no_ofrece_nada(self):
        proveedor = self._factura_proveedor()
        accion = self._pagar(proveedor)
        self.assertFalse(self._es_el_cuadro(accion))

    def test_un_fallo_del_ofrecimiento_nunca_estorba_el_pago(self):
        _pedido, factura = self._venta()
        with patch.object(DcasaImpresionPaquete, '_accion_dialogo', side_effect=ValueError('falla de prueba')), \
                self.assertLogs('odoo.addons.dcasa_invoice.models.account_payment_register', 'ERROR'):
            accion = self._pagar(factura)
        self.assertTrue(factura._dcasa_is_paid(), 'el pago quedó registrado')
        self.assertFalse(self._es_el_cuadro(accion))
        self.assertEqual(accion['res_model'], 'account.payment')

    def test_la_vendedora_paga_y_ve_el_cuadro(self):
        _pedido, factura = self._venta()
        factura_vendedora = factura.with_user(self.vendedora)
        asistente = self.env['account.payment.register'].with_user(self.vendedora).with_context(
            active_model='account.move', active_ids=factura_vendedora.ids).create({'payment_date': fields.Date.today()})
        accion = asistente.action_create_payments()
        self.assertTrue(self._es_el_cuadro(accion))
        self.assertEqual(self.Paquete.with_user(self.vendedora).browse(accion['res_id']).move_ids, factura_vendedora)


@tagged('post_install', '-at_install')
class TestPantallasDelPaquete(PaqueteComun):
    """Los botones están donde deben y lo de siempre sigue en su lugar."""

    def _arch(self, modelo, tipo, xmlid=None):
        vista = self.env.ref(xmlid).id if xmlid else None
        return self.env[modelo].get_view(view_id=vista, view_type=tipo)['arch']

    def test_boton_en_la_factura_y_lo_de_siempre_sigue(self):
        arch = self._arch('account.move', 'form', 'account.view_move_form')
        self.assertIn('name="action_dcasa_imprimir_documentos"', arch)
        for conserva in ('name="action_print_pdf"', 'name="action_post"', 'name="action_register_payment"',
                         'name="action_send_and_print"', 'name="preview_invoice"'):
            self.assertIn(conserva, arch, conserva)

    def test_boton_en_la_lista_de_facturas_de_clientes_y_no_en_la_de_proveedores(self):
        clientes = self._arch('account.move', 'list', 'account.view_out_invoice_tree')
        proveedores = self._arch('account.move', 'list', 'account.view_in_invoice_tree')
        self.assertIn('name="action_dcasa_imprimir_documentos"', clientes)
        self.assertIn('Imprimir paquete', clientes)
        self.assertIn('name="action_force_register_payment"', clientes)
        self.assertNotIn('action_dcasa_imprimir_documentos', proveedores)

    def test_boton_en_el_pedido_y_en_la_lista_de_pedidos(self):
        formulario = self._arch('sale.order', 'form', 'sale.view_order_form')
        lista = self._arch('sale.order', 'list', 'sale.view_order_tree')
        self.assertIn('name="action_dcasa_imprimir_documentos"', formulario)
        self.assertIn('name="action_dcasa_imprimir_documentos"', lista)
        self.assertIn('name="action_confirm"', formulario)

    def test_el_cuadro_tiene_imprimir_descargar_y_cerrar(self):
        arch = self._arch(MODELO, 'form')
        for texto in ('name="action_imprimir"', 'name="action_descargar"', 'name="action_cerrar"', 'special="cancel"',
                      'name="incluir_cliente"', 'name="incluir_copia"', 'name="incluir_entrega"'):
            self.assertIn(texto, arch, texto)

    def test_el_interruptor_esta_en_la_ficha_de_la_empresa(self):
        arch = self._arch('res.company', 'form', 'base.view_company_form')
        self.assertIn('name="dcasa_ofrecer_impresion_pago"', arch)

    def test_el_js_y_los_estilos_estan_en_el_backend(self):
        rutas = {ruta for _a, ruta, *_ in self.env['ir.asset']._get_asset_paths('web.assets_backend', {})}
        for archivo in ('dcasa_invoice/static/src/js/paquete_pdf.js', 'dcasa_invoice/static/src/js/panel_facturas.js',
                        'dcasa_invoice/static/src/xml/panel_facturas.xml',
                        'dcasa_invoice/static/src/scss/panel_facturas.scss'):
            self.assertTrue(any(ruta.endswith(archivo) for ruta in rutas), f'{archivo} no está en web.assets_backend')
