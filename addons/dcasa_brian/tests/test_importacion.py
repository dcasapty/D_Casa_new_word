"""Importación de productos desde el Excel de un proveedor: proponer, aplicar y deshacer."""
import base64
import io

from PIL import Image

from odoo import Command
from odoo.addons.dcasa_brian.models import lector_importacion
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _png(color, modo='RGB', lado=20):
    bufer = io.BytesIO()
    Image.new(modo, (lado, lado), color).save(bufer, format='PNG')
    return bufer.getvalue()


def _excel(filas, fotos=None, foto_en_titulo=False):
    """Mismo molde que el catálogo LTSC-07: título arriba, encabezado en la fila 4, fotos en «Imagen»."""
    import openpyxl
    from openpyxl.drawing.image import Image as ImagenXL
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = 'Catálogo IMP-01'
    hoja.append(['Catálogo de productos – Pedido IMP-01'])
    hoja.append(['Proveedor: Fábrica de Prueba · Fecha PI: 09/08/2026'])
    hoja.append(['🔍 Buscar (nombre o código):', None, None, '=IF($B$3="","todos","filtrados")'])
    hoja.append(['Imagen', 'Código', 'Descripción', 'Medidas (L × A × Alto)', 'Precio cama sola', 'Tamaño',
                 'Combo Dulce Sueños'])
    for fila in filas:
        hoja.append([None, *fila])
    for celda, crudo in (fotos or {}).items():
        hoja.add_image(ImagenXL(io.BytesIO(crudo)), celda)
    if foto_en_titulo:
        hoja.add_image(ImagenXL(io.BytesIO(_png((254, 208, 15)))), 'H1')
    bufer = io.BytesIO()
    libro.save(bufer)
    return bufer.getvalue()


FILAS = [
    ('IMP-888K', 'Cama tapizada King – beige', '228 × 223 × 120 cm', 259.98999999999998, 'KING', '=E5+158.67'),
    ('IMP-888Q', 'Cama tapizada Queen', '228 × 182 × 120 cm', 219.99, 'QUEEN', 378.66),
    ('IMP-DUP', 'Mesa de noche blanca', None, 49.99, None, None),
    (' imp-dup ', 'Mesa de noche negra', None, 49.99, None, None),
    ('IMP-SINPRECIO', 'Sofá gris', None, '$—', None, None),
    (None, None, 'TOTAL', 579.97, None, None),
]


@tagged('post_install', '-at_install')
class TestImportacion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)
        cls.vendedora = Usuarios.create({
            'name': 'Vendedora Importa', 'login': 'imp_vendedora',
            'group_ids': [Command.set([ref('base.group_user').id, ref('dcasa_base.group_vendedora').id])]})
        cls.gerente = Usuarios.create({
            'name': 'Gerente Importa', 'login': 'imp_gerente',
            'group_ids': [Command.set([ref('base.group_user').id, ref('dcasa_base.group_gerencia').id])]})
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        cls.queen = cls.env['product.template'].create({
            'name': 'Cama Queen vieja', 'default_code': 'imp-888q ', 'list_price': 150.0, 'type': 'consu',
            'is_storable': True, 'taxes_id': [Command.set(impuesto.ids)]})
        cls.foto_k = _png((19, 64, 177))
        cls.foto_q = _png((19, 64, 177, 128), modo='RGBA')

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def adjunto(self, usuario, crudo, nombre='Catalogo_IMP-01.xlsx'):
        return self.env['ir.attachment'].with_user(usuario).create({
            'name': nombre, 'raw': crudo, 'mimetype': MIME_XLSX, 'res_model': 'brian.conversacion'})

    def ejecutar(self, usuario, nombre, argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos)

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def confirmar(self, usuario, respuesta):
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        return self.env['brian.herramientas'].with_user(usuario).confirmar(respuesta['accion_id'])

    def proponer(self, usuario, crudo, **extra):
        archivo = self.adjunto(usuario, crudo)
        return self.ok(self.ejecutar(usuario, 'proponer_importacion', {'adjunto': archivo.name, **extra}))

    def excel_base(self, **extra):
        return _excel(FILAS, {'A5': self.foto_k, 'A6': self.foto_q}, **extra)

    def producto(self, codigo):
        return self.env['product.template'].with_context(active_test=False).search(
            [('default_code', '=ilike', codigo)])

    # ------------------------------------------------------------------
    # Lector
    # ------------------------------------------------------------------

    def test_lector_encabezado_columnas_y_fotos_por_fila(self):
        tabla = lector_importacion.leer_tabla(self.excel_base(foto_en_titulo=True))
        self.assertEqual(tabla['fila_encabezado'], 4)
        self.assertEqual({rol: c['columna'] for rol, c in tabla['columnas'].items()}, {
            'imagen': 'A', 'codigo': 'B', 'nombre': 'C', 'medidas': 'D', 'precio': 'E', 'tamano': 'F'})
        self.assertEqual([f['fila'] for f in tabla['filas']], [5, 6, 7, 8, 9])  # la de TOTAL no cuenta
        self.assertEqual(set(tabla['fotos']), {5, 6})
        self.assertEqual(tabla['fotos_en_hoja'], 3)
        self.assertTrue(any('fila 1' in a and 'no la asigné' in a for a in tabla['avisos']), tabla['avisos'])
        self.assertEqual(lector_importacion.precio_de(259.98999999999998), 259.99)
        self.assertIsNone(lector_importacion.precio_de('$—'))
        self.assertEqual(lector_importacion.precio_de('$1,234.50'), 1234.5)

    def test_dos_fotos_en_la_misma_fila_no_se_adivinan(self):
        tabla = lector_importacion.leer_tabla(_excel(FILAS[:2], {'A5': self.foto_k, 'B5': self.foto_q}))
        self.assertEqual(tabla['fotos'], {})
        self.assertTrue(any('fila 5 tiene 2 fotos' in a for a in tabla['avisos']), tabla['avisos'])

    def test_foto_normalizada_jpeg_o_png_con_transparencia(self):
        grande = io.BytesIO()
        Image.new('RGB', (3000, 1500), (19, 64, 177)).save(grande, format='PNG')
        salida = Image.open(io.BytesIO(lector_importacion.foto_normalizada(grande.getvalue())))
        self.assertEqual((salida.format, salida.size), ('JPEG', (1920, 960)))
        salida = Image.open(io.BytesIO(lector_importacion.foto_normalizada(self.foto_q)))
        self.assertEqual(salida.format, 'PNG')

    # ------------------------------------------------------------------
    # Proponer → aplicar → segunda importación → deshacer
    # ------------------------------------------------------------------

    def test_proponer_vista_previa(self):
        datos = self.proponer(self.vendedora, self.excel_base(foto_en_titulo=True))
        self.assertEqual(datos['conteo'], {'crear': 1, 'actualizar': 1, 'omitir': 3})
        self.assertEqual(datos['fotos'], {'en_la_hoja': 3, 'asignadas_a_un_producto': 2})
        lineas = {li['codigo'].strip(): li for li in datos['lineas']}
        self.assertEqual(lineas['IMP-888K']['accion'], 'crear')
        self.assertEqual(lineas['IMP-888K']['precio'], '$259.99')
        self.assertTrue(lineas['IMP-888K']['foto'])
        self.assertEqual(lineas['IMP-888Q']['cambios']['list_price'], '$150.00 → $219.99')
        self.assertIn('IMP-DUP', lineas)
        self.assertIn('Código repetido en las filas 7, 8', lineas['IMP-DUP']['motivo'])
        self.assertEqual(lineas['IMP-SINPRECIO']['motivo'], 'Sin precio')
        avisos = ' | '.join(datos['avisos'])
        self.assertIn('Códigos repetidos', avisos)
        self.assertIn('+47%', avisos)                       # 150 → 219.99: cambio de más del 30 %
        self.assertIn('Sin precio, no se importan: filas 9', avisos)
        self.assertIn('no es de un producto', avisos)       # la foto del título no se asigna
        # Nada cambió todavía.
        self.assertFalse(self.producto('IMP-888K'))
        self.assertEqual(self.queen.list_price, 150.0)
        # La vendedora ve su borrador pero no lo puede editar por RPC.
        importacion = self.env['brian.importacion'].with_user(self.vendedora).browse(datos['importacion_id'])
        self.assertEqual(importacion.estado, 'borrador')
        with self.assertRaises(AccessError):
            importacion.write({'modo_itbms': 'incluido'})
        with self.assertRaises(AccessError):
            importacion.linea_ids[:1].write({'precio': 1.0})

    def test_vendedora_no_aplica_ni_deshace(self):
        datos = self.proponer(self.vendedora, self.excel_base())
        for herramienta in ('aplicar_importacion', 'deshacer_importacion'):
            respuesta = self.ejecutar(self.vendedora, herramienta,
                                      {'importacion_id': datos['importacion_id'], 'motivo': 'x'}
                                      if herramienta == 'deshacer_importacion' else
                                      {'importacion_id': datos['importacion_id']})
            self.assertFalse(respuesta['ok'])
            self.assertIn('no tienes permiso', respuesta['error'])
            self.assertFalse(respuesta.get('requiere_confirmacion'))
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertIn('proponer_importacion', nombres)
        self.assertNotIn('aplicar_importacion', nombres)

    def test_aplicar_segunda_importacion_y_deshacer(self):
        datos = self.proponer(self.vendedora, self.excel_base())
        respuesta = self.ejecutar(self.gerente, 'aplicar_importacion', {'importacion_id': datos['importacion_id']})
        self.assertIn('Crear 1 producto(s)', respuesta['resumen'])
        self.assertIn('cambian más de 30%', respuesta['resumen'])
        self.ok(self.confirmar(self.gerente, respuesta))

        king = self.producto('IMP-888K')
        self.assertEqual(len(king), 1)
        self.assertEqual(king.list_price, 259.99)          # el precio del Excel tal cual (sin ITBMS)
        self.assertFalse(king.taxes_id.price_include)
        self.assertEqual(king.taxes_id, self.env['brian.herramientas']._b_itbms_venta())
        self.assertFalse(king.is_published)
        self.assertTrue(king.allow_out_of_stock_order)
        self.assertEqual(king.dcasa_medidas, 'L × A × Alto: 228 × 223 × 120 cm')
        self.assertEqual(king.categ_id, self.env.ref('dcasa_base.product_category_recamaras'))
        self.assertEqual(king.attribute_line_ids.value_ids.name, 'King')
        self.assertTrue(king.image_1920)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(king.image_1920))).format, 'JPEG')
        # El existente: precio nuevo, foto (PNG con transparencia) y medidas porque no tenía; el nombre no se toca.
        self.assertEqual(self.queen.list_price, 219.99)
        self.assertEqual(self.queen.name, 'Cama Queen vieja')
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(self.queen.image_1920))).format, 'PNG')
        self.assertEqual(self.queen.dcasa_medidas, 'L × A × Alto: 228 × 182 × 120 cm')
        self.assertFalse(self.producto('IMP-DUP'))
        primera = self.env['brian.importacion'].browse(datos['importacion_id'])
        self.assertEqual(primera.estado, 'aplicada')
        self.assertIn('"list_price": 150.0', primera.linea_ids.filtered(lambda li: li.codigo == 'IMP-888Q').antes)
        # No se aplica dos veces.
        otra = self.ejecutar(self.gerente, 'aplicar_importacion', {'importacion_id': primera.id})
        self.assertFalse(otra['ok'])
        self.assertIn('ya no está en borrador', otra['error'])

        # Segunda importación: el King sube de precio; guarda el antes.
        filas = [('imp-888k', 'Cama tapizada King – beige', '228 × 223 × 120 cm', 279.99, 'KING', None)]
        segunda = self.proponer(self.gerente, _excel(filas))
        self.assertEqual(segunda['conteo'], {'crear': 0, 'actualizar': 1, 'omitir': 0})
        self.ok(self.confirmar(self.gerente, self.ejecutar(
            self.gerente, 'aplicar_importacion', {'importacion_id': segunda['importacion_id']})))
        self.assertEqual(king.list_price, 279.99)
        linea = self.env['brian.importacion'].browse(segunda['importacion_id']).linea_ids
        self.assertIn('"list_price": 259.99', linea.antes)

        # Deshacer la segunda: vuelve el precio anterior.
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'deshacer_importacion', {
            'importacion_id': segunda['importacion_id'], 'motivo': 'precio equivocado'})))
        self.assertEqual(king.list_price, 259.99)

        # La dueña cambia a mano el precio del Queen; deshacer la primera respeta ese cambio.
        self.queen.list_price = 199.0
        respuesta = self.ejecutar(self.gerente, 'deshacer_importacion', {
            'importacion_id': primera.id, 'motivo': 'lote cancelado'})
        self.assertIn('Deshacer', respuesta['resumen'])
        datos = self.ok(self.confirmar(self.gerente, respuesta))
        self.assertFalse(king.exists())                     # creado y sin uso: se borra
        self.assertEqual(self.queen.list_price, 199.0)      # cambiado después: no se toca
        self.assertFalse(self.queen.image_1920)             # la foto que puso la importación se quita
        self.assertFalse(self.queen.dcasa_medidas)
        self.assertEqual(datos['conservados'][0]['codigo'], 'IMP-888Q')
        self.assertEqual(primera.estado, 'deshecha')
        self.assertEqual(primera.motivo_deshacer, 'lote cancelado')

    def test_deshacer_archiva_lo_que_ya_se_vendio(self):
        datos = self.proponer(self.gerente, self.excel_base())
        self.ok(self.confirmar(self.gerente, self.ejecutar(
            self.gerente, 'aplicar_importacion', {'importacion_id': datos['importacion_id']})))
        king = self.producto('IMP-888K')
        cliente = self.env['res.partner'].create({'name': 'Cliente Importación'})
        self.env['sale.order'].create({'partner_id': cliente.id, 'order_line': [
            Command.create({'product_id': king.product_variant_id.id, 'product_uom_qty': 1})]})
        self.ok(self.confirmar(self.gerente, self.ejecutar(self.gerente, 'deshacer_importacion', {
            'importacion_id': datos['importacion_id'], 'motivo': 'prueba'})))
        self.assertTrue(king.exists())
        self.assertFalse(king.active)
        # Un Excel con ese código ahora avisa que existe archivado (no crea otro).
        otra = self.proponer(self.gerente, self.excel_base())
        linea = next(li for li in otra['lineas'] if li['codigo'] == 'IMP-888K')
        self.assertEqual(linea['accion'], 'omitir')
        self.assertIn('archivado', linea['motivo'])

    def test_modo_itbms(self):
        mas = self.proponer(self.gerente, self.excel_base())
        incluido = self.proponer(self.gerente, self.excel_base(), modo_itbms='incluido')
        Importacion = self.env['brian.importacion']
        k_mas = Importacion.browse(mas['importacion_id']).linea_ids.filtered(lambda li: li.codigo == 'IMP-888K')
        k_inc = Importacion.browse(incluido['importacion_id']).linea_ids.filtered(lambda li: li.codigo == 'IMP-888K')
        self.assertEqual((k_mas.precio_excel, k_mas.precio), (259.99, 259.99))
        self.assertEqual((k_inc.precio_excel, k_inc.precio), (259.99, 242.98))   # 259.99 / 1.07
        self.assertIn('ya incluye', incluido['precios'])
        respuesta = self.ejecutar(self.gerente, 'proponer_importacion', {
            'adjunto': 'Catalogo_IMP-01.xlsx', 'modo_itbms': 'con_todo'})
        self.assertFalse(respuesta['ok'])

    def test_columna_de_precio_y_archivo_ajeno(self):
        datos = self.proponer(self.gerente, self.excel_base(), columna_precio='Combo Dulce Sueños')
        # La columna pedida es una fórmula sin valor guardado en la fila 5 → no se inventa el precio.
        linea = next(li for li in datos['lineas'] if li['codigo'] == 'IMP-888K')
        self.assertIn('fórmula sin valor guardado', linea['motivo'])
        self.assertIn('G «Combo Dulce Sueños»', datos['columnas']['precio'])
        malo = self.ejecutar(self.gerente, 'proponer_importacion', {
            'adjunto': 'Catalogo_IMP-01.xlsx', 'columna_precio': 'Precio de luna'})
        self.assertIn('No encontré la columna de precio', malo['error'])
        # El Excel que subió otra persona no lo encuentra.
        self.adjunto(self.gerente, self.excel_base(), nombre='Solo_gerencia.xlsx')
        ajeno = self.ejecutar(self.vendedora, 'proponer_importacion', {'adjunto': 'Solo_gerencia.xlsx'})
        self.assertIn('No encuentro el archivo', ajeno['error'])
