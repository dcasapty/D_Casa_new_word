"""El Escáner y el código QR de uso interno de un documento (``…/dcasa/doc/<TIPO>/<REFERENCIA>``).

Escaneado (lector o cámara), el QR de una factura, cotización, pedido de compra o entrega abre ESE documento, si quien
escanea puede verlo. Todo lo que no es un documento se escanea como siempre.
"""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .comun import BarrasCommon

BASE = 'https://erp.example.com'
GRUPOS = ('stock.group_stock_user,sales_team.group_sale_manager,account.group_account_invoice,'
          'purchase.group_purchase_user')


@tagged('post_install', '-at_install')
class TestEscanerDocumentos(BarrasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('web.base.url', BASE)
        cls.equipo = new_test_user(cls.env, login='barras_doc_equipo', groups=GRUPOS)
        cliente = cls.env['res.partner'].create({'name': 'CLIENTE SECRETO DEL QR', 'vat': '8-111-2222'})
        cls.pedido = cls.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [Command.create({'product_id': cls.cama.id, 'product_uom_qty': 2, 'price_unit': 100.0})]})
        cls.pedido.action_confirm()
        cls.entrega = cls.pedido.picking_ids
        cls.factura = cls.pedido._create_invoices()
        cls.factura.action_post()
        proveedor = cls.env['res.partner'].create({'name': 'PROVEEDOR SECRETO DEL QR'})
        cls.compra = cls.env['purchase.order'].create({
            'partner_id': proveedor.id,
            'order_line': [Command.create({'product_id': cls.cama.id, 'product_qty': 5, 'price_unit': 60.0})]})
        cls.compra.button_confirm()

    @staticmethod
    def abierto(accion):
        """El id del documento que abre la acción. La nota de entrega se abre en el panel de Bodega para quien usa
        Inventario (decisión de la dueña, 2026-10-22): una acción de cliente con ``params.entrega_id``."""
        if accion['type'] == 'ir.actions.client':
            return accion['params']['entrega_id']
        return accion['res_id']

    def leer(self, tipo, registro, usuario=None):
        return self.como(usuario or self.equipo).buscar(f'{BASE}/dcasa/doc/{tipo}/{registro.name}')

    # --- Abre el documento ------------------------------------------------------------------------

    def test_cada_tipo_de_documento_abre_su_formulario(self):
        for tipo, registro, modelo in (('FAC', self.factura, 'account.move'), ('COT', self.pedido, 'sale.order'),
                                       ('COM', self.compra, 'purchase.order')):
            r = self.leer(tipo, registro)
            self.assertEqual(r['resultado'], 'documento', tipo)
            accion = r['documento']['accion']
            self.assertEqual((accion['type'], accion['res_model'], accion['res_id']),
                             ('ir.actions.act_window', modelo, registro.id), tipo)
            self.assertEqual(accion['views'], [(False, 'form')])
            self.assertEqual(r['documento']['nombre'], registro.display_name)
            self.assertEqual((r['productos'], r['forma']), ([], False))
        # La nota de entrega, para quien usa Inventario, se abre en el panel de Bodega (decisión de la dueña,
        # 2026-10-22); antes abría el formulario de la entrega.
        for tipo, registro in (('ENT', self.entrega),):
            r = self.leer(tipo, registro)
            self.assertEqual(r['resultado'], 'documento', tipo)
            accion = r['documento']['accion']
            self.assertEqual((accion['type'], accion['tag'], self.abierto(accion)),
                             ('ir.actions.client', 'dcasa_barras_bodega', registro.id), tipo)
            self.assertEqual(r['documento']['nombre'], registro.display_name)
            self.assertEqual((r['productos'], r['forma']), ([], False))

    def test_una_direccion_larga_no_se_recorta(self):
        """Los códigos de producto se recortan a 64 caracteres; la dirección de un documento, no."""
        base = 'https://un-dominio-bastante-largo-del-erp.dcasa-panama.example.workers.dev'
        texto = f'{base}/dcasa/doc/COT/{self.pedido.name}'
        self.assertGreater(len(texto), 64)
        r = self.como(self.equipo).buscar(texto)
        self.assertEqual((r['resultado'], r['documento']['accion']['res_id']), ('documento', self.pedido.id))

    def test_como_la_escriba_el_lector(self):
        """Con salto de línea al final, en minúsculas o solo la ruta: el mismo documento."""
        nombre = self.entrega.name
        for texto in (f'{BASE}/dcasa/doc/ENT/{nombre}\r\n', f'{BASE}/dcasa/doc/ent/{nombre.lower()}',
                      f'/dcasa/doc/ENT/{nombre}', f'{BASE}/dcasa/doc/ENT/{nombre}?x=1'):
            r = self.como(self.equipo).buscar(texto)
            self.assertEqual((r['resultado'], self.abierto(r['documento']['accion'])), ('documento', self.entrega.id),
                             texto)

    def test_con_los_simbolos_cambiados_por_el_lector(self):
        """«/» llega como «-» y «:» como «Ñ» si el teclado del equipo está en otro idioma: se abre igual."""
        garabateado = f'httpsÑ--erp.example.com-dcasa-doc-FAC-{self.factura.name.replace("/", "-")}'
        r = self.como(self.equipo).buscar(garabateado)
        self.assertEqual((r['resultado'], r['documento']['accion']['res_id']), ('documento', self.factura.id))
        r = self.como(self.equipo).buscar(f'httpsÑ--x.co-dcasa-doc-ENT-{self.entrega.name.replace("/", "_")}')
        self.assertEqual((r['resultado'], self.abierto(r['documento']['accion'])), ('documento', self.entrega.id))
        # Sin permiso o inexistente, como siempre.
        self.assertEqual(self.como(self.vendedora).buscar(garabateado)['resultado'], 'documento_sin_permiso')
        self.assertEqual(self.como(self.equipo).buscar('httpsÑ--x.co-dcasa-doc-FAC-INV-2099-99999')['resultado'],
                         'documento_no_existe')

    # --- Sin permiso / no existe --------------------------------------------------------------------

    def test_sin_permiso_avisa_y_no_revela_nada(self):
        """La Vendedora del Escáner usa Inventario, que no lee facturas: se le avisa y no ve nada de la factura.
        (Cotizaciones y compras sí las leen los usuarios de Inventario en Odoo; las entregas, claro que sí.)"""
        r = self.leer('FAC', self.factura, self.vendedora)
        self.assertEqual(r['resultado'], 'documento_sin_permiso')
        self.assertIn('No tienes permiso', r['documento']['mensaje'])
        self.assertNotIn('accion', r['documento'])
        texto = str(r)   # (el número que se escaneó vuelve en la respuesta: lo escribió quien escaneó)
        for secreto in ('SECRETO', '8-111-2222', '200', '300', 'CLIENTE'):
            self.assertNotIn(secreto, texto, f'salió {secreto}')
        self.assertEqual(self.leer('ENT', self.entrega, self.vendedora)['resultado'], 'documento')

    def test_sin_permiso_tampoco_se_puede_averiguar_si_existe(self):
        """Quien no puede leer facturas recibe lo mismo con un número que existe y con uno que no."""
        existe = self.leer('FAC', self.factura, self.vendedora)['documento']
        no_existe = self.como(self.vendedora).buscar(f'{BASE}/dcasa/doc/FAC/INV/2099/99999')['documento']
        self.assertEqual((existe['estado'], existe['mensaje']), (no_existe['estado'], no_existe['mensaje']))
        self.assertEqual(existe['estado'], 'sin_permiso')

    def test_un_documento_que_no_existe_avisa(self):
        for tipo, referencia in (('FAC', 'INV/2099/99999'), ('COT', 'S99999'), ('COM', 'P99999'),
                                 ('ENT', 'WH/OUT/99999')):
            r = self.como(self.equipo).buscar(f'{BASE}/dcasa/doc/{tipo}/{referencia}')
            self.assertEqual(r['resultado'], 'documento_no_existe', tipo)
            self.assertIn('No encontramos ese documento', r['documento']['mensaje'])
            self.assertNotIn('accion', r['documento'])

    def test_quien_no_usa_inventario_sigue_sin_poder_usar_el_escaner(self):
        with self.assertRaises(AccessError):
            self.como(self.sin_inventario).buscar(f'{BASE}/dcasa/doc/COT/{self.pedido.name}')

    # --- Lo demás se escanea como siempre --------------------------------------------------------------

    def test_lo_que_no_es_un_documento_sigue_igual(self):
        for texto, forma in (('ZZT-CAMA-1', 'referencia'), (self.cama.dcasa_codigo_publico, 'codigo_publico')):
            r = self.Barras.buscar(texto)
            self.assertEqual((r['resultado'], r['forma'], r['productos'][0]['id']), ('ok', forma, self.cama.id), texto)
        self.zapatera.barcode = 'DC0001'
        self.assertEqual(self.Barras.buscar('DC0001')['productos'][0]['id'], self.zapatera.id)
        self.assertEqual(self.Barras.buscar('')['resultado'], 'vacio')
        self.assertEqual(self.Barras.buscar('NO-EXISTE-999')['resultado'], 'no_encontrado')

    def test_una_direccion_parecida_que_no_es_de_documento_se_busca_como_codigo(self):
        for texto in (f'{BASE}/dcasa/doc/XXX/S00001', f'{BASE}/dcasa/doc/', f'{BASE}/otra/cosa/COT/S00001'):
            self.assertEqual(self.Barras.buscar(texto)['resultado'], 'no_encontrado', texto)

    # --- Asignar etiquetas: el QR de un documento no es una etiqueta ----------------------------------------

    def test_el_qr_de_un_documento_no_se_toma_por_una_etiqueta(self):
        gerencia = self.como(self.gerencia)
        with self.assertUserError('código QR de un documento'):
            gerencia.etiqueta('httpsÑ--x.co-dcasa-doc-COT-S00001')   # con los símbolos cambiados por el lector
        with self.assertUserError('código QR de un documento'):
            gerencia.etiqueta(f'{BASE}/dcasa/doc/COT/{self.pedido.name}')
        with self.assertUserError('código QR de un documento'):
            gerencia.asignar_etiqueta(f'{BASE}/dcasa/doc/COT/{self.pedido.name}', self.cama.id)
        self.assertFalse(self.cama.barcode)
        with self.assertRaises(UserError):
            gerencia.etiqueta('DC9999 con espacio')
        self.assertEqual(gerencia.etiqueta('DC9999')['estado'], 'libre')
