"""La nota de entrega fácil de leer (la de bodega): foto, cantidad en número grande y en dibujitos, casilla.

Solo con «Nota de entrega fácil de leer» encendida en la empresa. Apagada, la nota sale exactamente como siempre (eso lo
vigila ``test_documentos_intactos.py`` letra por letra; aquí solo se comprueba que no aparece nada de lo nuevo).
"""
import base64
import io
import shutil
from unittest import skipUnless

from lxml import html as lxml_html
from PIL import Image

from odoo import Command
from odoo.tests import HttpCase, tagged
from odoo.tools.pdf import PdfFileReader

from ..models import entrega_facil
from .documentos import DocumentosDePrueba
from .test_documentos_intactos import INFORME_ENTREGA


def foto_de_prueba(color=(19, 64, 177)):
    imagen = io.BytesIO()
    Image.new('RGB', (64, 48), color).save(imagen, 'PNG')
    return base64.b64encode(imagen.getvalue())


def arbol(contenido):
    return lxml_html.document_fromstring(contenido)


def filas(contenido):
    return arbol(contenido).xpath("//tr[contains(@class, 'o_df_linea')]")


def texto(elemento, clase):
    return ' '.join(x.text_content().strip() for x in elemento.xpath(f".//*[contains(@class, '{clase}')]"))


class TestReglasDeLaNotaFacil(DocumentosDePrueba):
    """Lo que no depende de la base de datos."""

    def test_cantidad_en_texto(self):
        self.assertEqual(entrega_facil.texto_cantidad(3.0), '3')
        self.assertEqual(entrega_facil.texto_cantidad(2.5), '2.5')
        self.assertEqual(entrega_facil.texto_cantidad(0), '0')
        self.assertEqual(entrega_facil.texto_cantidad(None), '0')

    def test_un_dibujito_por_pieza_hasta_diez(self):
        self.assertEqual(entrega_facil.iconos_de_cantidad(1), (1, False))
        self.assertEqual(entrega_facil.iconos_de_cantidad(3.0), (3, False))
        self.assertEqual(entrega_facil.iconos_de_cantidad(10), (10, False))
        self.assertEqual(entrega_facil.iconos_de_cantidad(11), (10, True), 'más de diez: diez y un «+»')
        self.assertEqual(entrega_facil.iconos_de_cantidad(250), (10, True))

    def test_una_cantidad_con_decimales_o_vacia_no_se_dibuja(self):
        for cantidad in (0, -2, 2.5, None):
            self.assertEqual(entrega_facil.iconos_de_cantidad(cantidad), (0, False), cantidad)

    def test_junto_al_numero_solo_va_la_medida_si_no_es_la_unidad(self):
        self.assertEqual(entrega_facil.texto_unidad(True, 'Units'), '', 'unidades: basta el número')
        self.assertEqual(entrega_facil.texto_unidad(False, 'm'), 'm')

    def test_la_densidad_depende_de_cuantos_productos_hay(self):
        """Es una hoja carta: con pocos productos todo grande; con 8 o más (hasta 10 caben en una hoja) más apretado."""
        self.assertEqual([entrega_facil.densidad(n) for n in (0, 1, 4)], [1, 1, 1])
        self.assertEqual([entrega_facil.densidad(n) for n in (5, 6, 7)], [2, 2, 2])
        self.assertEqual([entrega_facil.densidad(n) for n in (8, 10, 14)], [3, 3, 3])

    def test_el_total_cuenta_piezas_y_no_metros(self):
        lineas = [{'cantidad': 2.0}, {'cantidad': 1.0}, {'cantidad': 2.5}]
        self.assertEqual(entrega_facil.total_de_piezas(lineas), 3)
        self.assertEqual(entrega_facil.total_de_piezas([]), 0)


@tagged('post_install', '-at_install')
class TestNotaDeEntregaFacil(DocumentosDePrueba):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.colchon.image_1920 = foto_de_prueba()   # el colchón tiene foto; la cama no

    def nota(self, entrega=None, facil=True, **interruptores):
        self.company.dcasa_entrega_facil = facil
        self.interruptores(**interruptores)
        return self.html(INFORME_ENTREGA, entrega or self.entrega(), normalizado=False)

    # --- Apagada ---------------------------------------------------------------------------------

    def test_el_interruptor_viene_apagado(self):
        self.assertFalse(self.env['res.company']._fields['dcasa_entrega_facil'].default(self.env['res.company']))

    def test_apagada_sale_la_nota_de_siempre(self):
        contenido = self.nota(facil=False)
        self.assertIn('stock_move_table', contenido)
        for nuevo in ('o_dcasa_entrega_facil', 'o_df_linea', 'o_df_casilla'):
            self.assertNotIn(nuevo, contenido)

    # --- Encendida: lo que se ve -----------------------------------------------------------------

    def test_encendida_no_sale_la_tabla_de_siempre_y_si_la_nota_facil(self):
        contenido = self.nota()
        self.assertNotIn('stock_move_table', contenido)
        self.assertEqual(len(arbol(contenido).xpath("//div[contains(@class, 'o_dcasa_entrega_facil')]")), 1)
        self.assertIn('Nota de entrega', contenido)

    def test_cada_producto_trae_casilla_foto_nombre_codigo_y_cantidad(self):
        contenido = self.nota()
        lineas = filas(contenido)
        self.assertEqual(len(lineas), 2, 'dos productos con existencias; el flete es un servicio y no sale de bodega')
        colchon, cama = lineas
        # El cliente lee los nombres en formato título (F5); por dentro siguen en MAYÚSCULAS.
        self.assertIn('Colchon Imperial Twin 3/4 Buen Sueño', texto(colchon, 'o_df_nombre'))
        self.assertIn('Cama Queen Grey con Estantes', texto(cama, 'o_df_nombre'))
        self.assertEqual(texto(colchon, 'o_df_codigo_valor'), 'IM-2001')
        self.assertEqual(texto(colchon, 'o_df_numero'), '2')
        self.assertEqual(texto(cama, 'o_df_numero'), '1')
        for fila in (colchon, cama):
            self.assertFalse(fila.xpath(".//*[contains(@class, 'o_df_unidad')]"), 'solo el número, sin «unidades»')
        for fila in lineas:
            self.assertEqual(len(fila.xpath(".//div[contains(@class, 'o_df_casilla')]")), 1, 'una casilla por producto')

    def test_con_foto_se_ve_la_foto_y_sin_foto_dice_sin_foto(self):
        colchon, cama = filas(self.nota())
        foto = colchon.xpath(".//img[contains(@class, 'o_df_foto')]")
        self.assertEqual(len(foto), 1)
        self.assertTrue(foto[0].get('src').startswith('data:image/png;base64,'))
        self.assertTrue(foto[0].get('alt'), 'la foto lleva su texto alternativo (lectores de pantalla)')
        self.assertFalse(cama.xpath(".//img[contains(@class, 'o_df_foto')]"))
        self.assertEqual(texto(cama, 'o_df_sin_foto'), 'Sin foto')

    def test_la_cantidad_tambien_es_una_fila_de_dibujitos_uno_por_pieza(self):
        colchon, cama = filas(self.nota())
        self.assertEqual(len(colchon.xpath(".//img[contains(@class, 'o_df_icono')]")), 2,
                         'dos colchones: dos fotos chicas')
        self.assertEqual(len(cama.xpath(".//span[contains(@class, 'o_df_icono_caja')]")), 1,
                         'sin foto el dibujito es una caja: una pieza, una caja')
        self.assertFalse(colchon.xpath(".//*[contains(@class, 'o_df_mas')]"))

    def test_mas_de_diez_piezas_dibuja_diez_y_un_mas(self):
        entrega = self.entrega()
        entrega.move_ids.filtered(lambda m: m.product_id == self.colchon).product_uom_qty = 14
        colchon, _cama = filas(self.nota(entrega))
        self.assertEqual(texto(colchon, 'o_df_numero'), '14')
        self.assertEqual(len(colchon.xpath(".//img[contains(@class, 'o_df_icono')]")), 10)
        self.assertEqual(texto(colchon, 'o_df_mas'), '+')

    def test_el_total_de_piezas_y_las_dos_rayas(self):
        contenido = self.nota()
        raiz = arbol(contenido)
        self.assertEqual(raiz.xpath("string(//td[contains(@class, 'o_df_total_numero')])").strip(), '3')
        self.assertIn('Sacó de bodega', contenido)
        self.assertIn('Recibió', contenido)
        self.assertEqual(len(raiz.xpath("//div[contains(@class, 'o_df_raya')]")), 2)

    def test_arriba_el_pedido_la_factura_y_la_fecha(self):
        entrega = self.entrega()
        pedido = entrega.sale_id
        pedido._create_invoices()
        pedido.invoice_ids.action_post()
        contenido = self.nota(entrega)
        datos = texto(arbol(contenido).xpath("//table[contains(@class, 'o_df_datos')]")[0], 'o_df_dato')
        self.assertIn(pedido.name, datos)
        self.assertIn(pedido.invoice_ids[0].name, datos)
        self.assertIn('14/10/2026', datos, 'dd/mm/aaaa, a la hora de Panamá')

    def test_la_vendedora_imprime_la_nota_facil_del_pedido_de_otra(self):
        """«Cada vendedora ve solo sus documentos»: la entrega la despacha cualquiera. La vendedora que no puede leer
        el pedido (ni la factura) de otra igual imprime su nota fácil, con el número de la factura arriba."""
        entrega = self.entrega()
        pedido = entrega.sale_id
        pedido._create_invoices()
        pedido.invoice_ids.action_post()
        otra = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Otra Vendedora Nota Facil', 'login': 'otra.vendedora.nota.facil',
            'group_ids': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('dcasa_base.group_vendedora').id])]})
        self.assertTrue(self.env['res.users']._dcasa_restriccion_activa())
        self.assertFalse(self.env['sale.order'].with_user(otra).search_count([('id', '=', pedido.id)]),
                         'el pedido es de Ana Vendedora: la otra no lo ve')
        self.company.dcasa_entrega_facil = True
        contenido, _tipo = self.env['ir.actions.report'].with_user(otra)._render_qweb_html(
            INFORME_ENTREGA, entrega.ids)
        datos = texto(arbol(contenido.decode()).xpath("//table[contains(@class, 'o_df_datos')]")[0], 'o_df_dato')
        self.assertIn(pedido.invoice_ids[0].name, datos)
        self.assertEqual(len(filas(contenido.decode())), 2)

    def test_sin_pedido_ni_factura_las_casillas_dicen_raya(self):
        entrega = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.warehouse0').out_type_id.id,
            'location_id': self.env.ref('stock.warehouse0').lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [Command.create({
                'product_id': self.cama.id, 'product_uom_qty': 1, 'product_uom': self.cama.uom_id.id,
                'location_id': self.env.ref('stock.warehouse0').lot_stock_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id})]})
        entrega.action_confirm()
        contenido = self.nota(entrega)
        self.assertEqual(len(filas(contenido)), 1)
        datos = texto(arbol(contenido).xpath("//table[contains(@class, 'o_df_datos')]")[0], 'o_df_dato')
        self.assertEqual(datos.count('—'), 2, 'sin pedido ni factura: dos rayas')

    def entrega_con(self, cuantos):
        """Una entrega de ``cuantos`` productos distintos (uno de cada)."""
        productos = [self.env['product.product'].create({'name': f'Mueble {i:02d}', 'type': 'consu'})
                     for i in range(cuantos)]
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': p.id, 'product_uom_qty': 1, 'price_unit': 10})
                           for p in productos]})
        pedido.action_confirm()
        return pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')[:1]

    def test_la_nota_se_aprieta_segun_cuantos_productos_lleva(self):
        for cuantos, clase in ((2, 'o_df_n1'), (6, 'o_df_n2'), (10, 'o_df_n3')):
            contenido = self.nota(self.entrega_con(cuantos))
            self.assertEqual(len(filas(contenido)), cuantos)
            self.assertEqual(len(arbol(contenido).xpath(f"//div[contains(@class, '{clase}')]")), 1, (cuantos, clase))

    def test_con_diez_productos_todos_traen_casilla_numero_y_su_lugar_para_la_foto(self):
        contenido = self.nota(self.entrega_con(10))
        for fila in filas(contenido):
            self.assertEqual(len(fila.xpath(".//div[contains(@class, 'o_df_casilla')]")), 1)
            self.assertEqual(texto(fila, 'o_df_numero'), '1')
            self.assertEqual(texto(fila, 'o_df_sin_foto'), 'Sin foto')

    def test_el_qr_va_junto_al_total_y_no_en_una_fila_aparte(self):
        contenido = self.nota(qr=True)
        self.assertEqual(len(arbol(contenido).xpath(
            "//td[contains(@class, 'o_df_cierre_qr')]//div[@name='dcasa_qr']")), 1)
        sin_qr = self.nota(qr=False)
        self.assertFalse(arbol(sin_qr).xpath("//td[contains(@class, 'o_df_cierre_qr')]"), 'sin QR no hay celda')

    # --- Código público y QR ---------------------------------------------------------------------

    def test_con_el_codigo_publico_encendido_nunca_sale_la_referencia_del_proveedor(self):
        contenido = self.nota(codigo_publico=True)
        colchon, cama = filas(contenido)
        self.assertEqual(texto(colchon, 'o_df_codigo_valor'), self.colchon.dcasa_codigo_publico)
        self.assertEqual(texto(cama, 'o_df_codigo_valor'), self.cama.dcasa_codigo_publico)
        for referencia in ('IM-2001', '1062010735N'):
            self.assertNotIn(referencia, contenido)

    def test_con_el_qr_encendido_la_nota_facil_lo_lleva(self):
        contenido = self.nota(qr=True)
        self.assertEqual(len(arbol(contenido).xpath(
            "//div[contains(@class, 'o_dcasa_entrega_facil')]//div[@name='dcasa_qr']")), 1)

    # --- Entrega terminada -----------------------------------------------------------------------

    def test_una_entrega_hecha_a_medias_muestra_lo_entregado_y_lo_que_falta(self):
        entrega = self.entrega()
        entrega.action_assign()
        for movimiento in entrega.move_ids:
            movimiento.quantity = 1
        accion = entrega.button_validate()
        self.assertEqual(accion['res_model'], 'stock.backorder.confirmation')
        self.env['stock.backorder.confirmation'].with_context(**accion['context']).create(
            {'pick_ids': [Command.link(entrega.id)]}).process()
        self.assertEqual(entrega.state, 'done')
        contenido = self.nota(entrega)
        self.assertEqual(len(filas(contenido)), 3, 'dos entregados y uno pendiente')
        colchon, cama = filas(contenido)[:2]
        self.assertEqual(texto(colchon, 'o_df_numero'), '1', 'salió 1 de los 2 colchones')
        self.assertEqual(texto(colchon, 'o_df_falta'), 'Faltan 1')
        self.assertFalse(cama.xpath(".//*[contains(@class, 'o_df_falta')]"))
        pendientes = arbol(contenido).xpath("//div[contains(@class, 'o_df_pendientes')]")
        self.assertEqual(len(pendientes), 1, 'lo que falta se anuncia aparte')
        self.assertIn('Colchon Imperial', pendientes[0].text_content())
        self.assertFalse(pendientes[0].xpath(".//div[contains(@class, 'o_df_casilla')]"), 'lo pendiente no se marca')


@tagged('post_install', '-at_install')
class TestNotaFacilEnPdf(HttpCase):
    """El PDF de verdad: wkhtmltopdf pide los estilos al propio Odoo, por eso es una prueba con servidor."""

    @skipUnless(shutil.which('wkhtmltopdf'), 'sin wkhtmltopdf (la imagen Docker lo comprueba en CI)')
    def test_sale_en_pdf_con_los_estilos_de_marca(self):
        self.env['ir.config_parameter'].sudo().set_param('report.url', False)
        self.env.company.dcasa_entrega_facil = True
        cliente = self.env['res.partner'].create({'name': 'Cliente PDF fácil'})
        con_foto = self.env['product.product'].create({
            'name': 'Mesa con foto', 'type': 'consu', 'image_1920': foto_de_prueba()})
        sin_foto = self.env['product.product'].create({'name': 'Silla sin foto', 'type': 'consu'})
        pedido = self.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [Command.create({'product_id': con_foto.id, 'product_uom_qty': 3, 'price_unit': 50}),
                           Command.create({'product_id': sin_foto.id, 'product_uom_qty': 1, 'price_unit': 20})]})
        pedido.action_confirm()
        entrega = pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')[:1]
        pdf, _tipo = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
            INFORME_ENTREGA, entrega.ids)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertIn(b'Inter', pdf, 'la nota salió sin estilos (wkhtmltopdf no cargó el CSS)')

    @skipUnless(shutil.which('wkhtmltopdf'), 'sin wkhtmltopdf (la imagen Docker lo comprueba en CI)')
    def test_diez_productos_con_foto_y_el_qr_caben_en_una_sola_hoja_carta(self):
        self.env['ir.config_parameter'].sudo().set_param('report.url', False)
        empresa = self.env.company
        empresa.write({'dcasa_entrega_facil': True, 'dcasa_mostrar_qr_documentos': True})
        cliente = self.env['res.partner'].create({'name': 'Cliente de las diez'})
        lineas = []
        for i in range(10):
            producto = self.env['product.product'].create({
                'name': f'MUEBLE DE PRUEBA NUMERO {i + 1} CON UN NOMBRE BASTANTE LARGO', 'type': 'consu',
                'image_1920': foto_de_prueba() if i % 2 else False})
            lineas.append(Command.create({'product_id': producto.id, 'product_uom_qty': i + 1, 'price_unit': 10}))
        pedido = self.env['sale.order'].create({'partner_id': cliente.id, 'order_line': lineas})
        pedido.action_confirm()
        entrega = pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')[:1]
        pdf, _tipo = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
            INFORME_ENTREGA, entrega.ids)
        self.assertEqual(len(PdfFileReader(io.BytesIO(pdf)).pages), 1,
                         'diez productos (con su foto, su número y su casilla) más el QR deben caber en una hoja')
