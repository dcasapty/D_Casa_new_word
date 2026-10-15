"""«Mostrar el código público…»: DC-K7M4PX en lugar de la referencia del proveedor, y solo con el interruptor encendido.

Con el interruptor encendido la referencia del proveedor (``IM-2001``) no aparece NUNCA en lo que ve el cliente: ni en
la «Código», ni en el nombre de la línea, ni en la nota de entrega. Apagado, nada cambia (lo vigilan
``test_documentos_intactos.py`` y, para las pantallas, los tests de abajo).
"""
from lxml import html as lxml_html

from odoo import Command
from odoo.addons.dcasa_base.models.codigo_publico import CLAVE_PASE, PASE
from odoo.tests import tagged

from ..models import lineas
from .documentos import DocumentosDePrueba
from .test_documentos_intactos import INFORME_COTIZACION, INFORME_ENTREGA, INFORME_FACTURA

REFERENCIAS = ('IM-2001', '1062010735N', 'DCASA-FLETE')


def celdas_de_codigo(contenido, nombre='td_codigo'):
    """El texto de la columna «Código» (filas de producto) de un informe de factura o cotización."""
    arbol = lxml_html.document_fromstring(contenido)
    return [(celda.text_content() or '').strip() for celda in arbol.xpath(f"//td[@name='{nombre}']")] + [
        (celda.text_content() or '').strip() for celda in arbol.xpath("//td[contains(@class, 'o_dcasa_td_codigo')]"
                                                                     f"[not(@name='{nombre}')]")]


@tagged('post_install', '-at_install')
class TestCodigoPublicoEnDocumentos(DocumentosDePrueba):

    def codigos(self, *productos):
        return [producto.dcasa_codigo_publico for producto in productos]

    def assertSinReferencias(self, contenido, donde):
        for referencia in REFERENCIAS:
            self.assertNotIn(referencia, contenido, f'{donde}: salió la referencia del proveedor {referencia}')

    # --- La función de la columna -------------------------------------------------------------------

    def test_codigo_a_imprimir(self):
        self.assertEqual(lineas.codigo_a_imprimir(self.company, self.colchon, 'IM-2001'), 'IM-2001')
        self.interruptores(codigo_publico=True)
        self.assertEqual(lineas.codigo_a_imprimir(self.company, self.colchon, 'IM-2001'),
                         self.colchon.dcasa_codigo_publico)
        self.assertEqual(lineas.codigo_a_imprimir(self.company, self.env['product.product'], 'ABC'), '',
                         'una línea sin producto no muestra el código del proveedor')
        self.assertEqual(lineas.quitar_referencia_delante('[IM-2001] COLCHON', 'IM-2001'), 'COLCHON')
        self.assertEqual(lineas.quitar_referencia_delante('[OTRA] COLCHON', 'IM-2001'), '[OTRA] COLCHON')
        self.assertEqual(lineas.quitar_referencia_delante('COLCHON', False), 'COLCHON')

    # --- Factura y cotización --------------------------------------------------------------------------

    def test_factura_encendido_muestra_el_codigo_publico(self):
        self.interruptores(codigo_publico=True)
        factura = self.factura_completa()
        contenido = self.html(INFORME_FACTURA, factura, normalizado=False)
        self.assertSinReferencias(contenido, 'factura')
        self.assertEqual(celdas_de_codigo(contenido), self.codigos(self.colchon, self.cama, self.flete))
        self.assertIn('COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO', contenido, 'la descripción sigue')

    def test_factura_hecha_antes_de_encender_tambien_sale_sin_referencia(self):
        """El nombre guardado trae «[IM-2001] …» (se hizo con el interruptor apagado): al imprimir se limpia."""
        factura = self.factura_completa()
        self.assertTrue(factura.invoice_line_ids[0].name.startswith('[IM-2001]'))
        self.interruptores(codigo_publico=True)
        contenido = self.html(INFORME_FACTURA, factura, normalizado=False)
        self.assertSinReferencias(contenido, 'factura vieja')
        self.assertIn(self.colchon.dcasa_codigo_publico, contenido)

    def test_cotizacion_y_pedido_encendido_muestran_el_codigo_publico(self):
        self.interruptores(codigo_publico=True)
        for pedido in (self.cotizacion(), self.cotizacion(confirmar=True)):
            contenido = self.html(INFORME_COTIZACION, pedido, normalizado=False)
            self.assertSinReferencias(contenido, pedido.name)
            self.assertEqual(celdas_de_codigo(contenido), self.codigos(self.colchon, self.cama, self.flete))

    def test_cotizacion_hecha_antes_de_encender_sale_sin_referencia(self):
        pedido = self.cotizacion()
        self.assertTrue(pedido.order_line[0].name.startswith('[IM-2001]'))
        self.interruptores(codigo_publico=True)
        self.assertSinReferencias(self.html(INFORME_COTIZACION, pedido, normalizado=False), 'cotización vieja')

    def test_sin_codigo_publico_la_celda_queda_vacia_nunca_la_del_proveedor(self):
        self.cama.product_tmpl_id.with_context(**{CLAVE_PASE: PASE}).write({'dcasa_codigo_publico': False})
        self.assertFalse(self.cama.dcasa_codigo_publico)
        self.interruptores(codigo_publico=True)
        pedido = self.cotizacion()
        contenido = self.html(INFORME_COTIZACION, pedido, normalizado=False)
        self.assertSinReferencias(contenido, 'cotización')
        self.assertEqual(celdas_de_codigo(contenido), [self.colchon.dcasa_codigo_publico, '',
                                                       self.flete.dcasa_codigo_publico])
        factura = self.factura_completa()
        contenido = self.html(INFORME_FACTURA, factura, normalizado=False)
        self.assertSinReferencias(contenido, 'factura')
        self.assertEqual(celdas_de_codigo(contenido)[1], '')

    def test_apagado_la_columna_es_la_del_proveedor(self):
        contenido = self.html(INFORME_COTIZACION, self.cotizacion(), normalizado=False)
        self.assertEqual(celdas_de_codigo(contenido), ['IM-2001', '1062010735N', 'DCASA-FLETE'])
        self.assertNotIn(self.colchon.dcasa_codigo_publico, contenido)

    def test_lineas_de_seccion_y_nota_no_llevan_codigo(self):
        self.interruptores(codigo_publico=True)
        pedido = self.cotizacion()
        pedido.write({'order_line': [
            Command.create({'display_type': 'line_section', 'name': 'Sala'}),
            Command.create({'display_type': 'line_note', 'name': 'Entrega en la mañana'})]})
        contenido = self.html(INFORME_COTIZACION, pedido, normalizado=False)
        self.assertIn('Sala', contenido)
        self.assertSinReferencias(contenido, 'cotización con secciones')
        self.assertEqual(pedido.order_line.filtered('display_type')[0]._dcasa_codigo(), '')

    # --- El nombre que Odoo guarda en la línea ------------------------------------------------------------

    def test_el_nombre_de_la_linea_nueva_no_lleva_la_referencia(self):
        """Lo que ve el cliente en el portal y en los correos."""
        apagado = self.cotizacion().order_line[0].name
        self.assertTrue(apagado.startswith('[IM-2001] '), apagado)
        self.interruptores(codigo_publico=True)
        encendido = self.cotizacion().order_line[0].name
        self.assertEqual(encendido, 'COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO')
        self.colchon.description_sale = 'Resortes ensacados'
        con_descripcion = self.cotizacion().order_line[0].name
        self.assertEqual(con_descripcion, 'COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO\nResortes ensacados')
        self.assertNotIn('IM-2001', con_descripcion)

    def test_el_nombre_de_una_linea_de_factura_manual_no_lleva_la_referencia(self):
        self.interruptores(codigo_publico=True)
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': self.colchon.id, 'quantity': 1, 'price_unit': 10})]})
        self.assertEqual(factura.invoice_line_ids.name, 'COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO')
        self.interruptores(codigo_publico=False)
        otra = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'product_id': self.colchon.id, 'quantity': 1, 'price_unit': 10})]})
        self.assertEqual(otra.invoice_line_ids.name, '[IM-2001] COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO')

    def test_la_referencia_sigue_en_las_pantallas_internas(self):
        """El equipo sigue encontrando el producto por su referencia: el nombre del producto no cambia."""
        self.interruptores(codigo_publico=True)
        self.assertEqual(self.colchon.display_name, '[IM-2001] COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO')
        self.assertEqual(self.colchon.default_code, 'IM-2001')

    # --- Nota de entrega ---------------------------------------------------------------------------------------

    def assertEntregaSinReferencias(self, entrega, donde):
        contenido = self.html(INFORME_ENTREGA, entrega, normalizado=False)
        self.assertSinReferencias(contenido, donde)
        for producto in (self.colchon, self.cama):
            self.assertEqual(contenido.count(f'[{producto.dcasa_codigo_publico}] {producto.name}'), 1,
                             f'{donde}: «[{producto.dcasa_codigo_publico}] {producto.name}» debe salir una vez')
        return contenido

    def test_nota_de_entrega_encendido_muestra_el_codigo_publico(self):
        self.interruptores(codigo_publico=True)
        self.assertEntregaSinReferencias(self.entrega(), 'entrega por hacer')

    def test_nota_de_entrega_hecha_antes_de_encender(self):
        entrega = self.entrega()
        self.assertIn('[IM-2001]', self.html(INFORME_ENTREGA, entrega, normalizado=False))
        self.interruptores(codigo_publico=True)
        self.assertEntregaSinReferencias(entrega, 'entrega hecha antes de encender')

    def test_nota_de_entrega_ya_entregada_y_con_pendientes(self):
        self.interruptores(codigo_publico=True)
        entrega = self.entrega()
        movimiento = entrega.move_ids.filtered(lambda m: m.product_id == self.colchon)
        movimiento.quantity = 1          # se entrega 1 de 2: el resto queda pendiente en otra entrega
        (entrega.move_ids - movimiento).quantity = 1
        entrega.move_ids.picked = True
        entrega.with_context(skip_backorder=True).button_validate()
        self.assertEqual(entrega.state, 'done')
        self.assertTrue(entrega.backorder_ids, 'quedó una entrega pendiente')
        contenido = self.html(INFORME_ENTREGA, entrega, normalizado=False)
        self.assertSinReferencias(contenido, 'entrega hecha con pendientes')
        self.assertIn(f'[{self.colchon.dcasa_codigo_publico}] {self.colchon.name}', contenido)
        self.assertIn('Remaining quantities not yet delivered', contenido)

    def test_la_descripcion_propia_de_la_entrega_se_conserva_sin_la_referencia(self):
        self.interruptores(codigo_publico=True)
        entrega = self.entrega()
        movimiento = entrega.move_ids.filtered(lambda m: m.product_id == self.colchon)
        movimiento.description_picking = f'[IM-2001] {self.colchon.name}\nColor gris con patas negras'
        contenido = self.html(INFORME_ENTREGA, entrega, normalizado=False)
        self.assertSinReferencias(contenido, 'entrega con descripción')
        self.assertIn('Color gris con patas negras', contenido)
