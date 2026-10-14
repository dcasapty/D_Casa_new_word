"""El combos.csv real que dejó la extensión de Claude en Chrome (71 combos), contra el catálogo que trae el repositorio.

El archivo (catálogo, sin datos de personas) vive en ``combos_reales.py``. Los productos son los de una base limpia:
``catalogo.json`` y el inventario del sistema anterior (``dcasa_catalogo``). Lo que no está ahí —los sofás 77090 y una
cama con estantes archivada— se lista como pieza que falta; las piezas nunca se crean desde este archivo.
"""
import base64

from odoo.addons.dcasa_migracion import combos as C
from odoo.addons.dcasa_migracion import reglas_combos as RC
from odoo.tests import TransactionCase, tagged

from . import ejemplos
from .combos_reales import COMBOS_REALES

BOX_SPRING = 'COMBO BOX SPRING DE METAL SENCILLO TAMAÑO FULL / N-F10018-F-BK + COLCHON IMPERIAL'
UP_TWIN = 'COMBO CAMA BUTTERFLY UP TWIN + COLCHO IMPERIAL'
CAMAROTE = 'COMBO CAMAROTE TRIPLE 3 TWIN W160969418 + 3 COLCHONES IMPERIAL'
KING_CON_ESTANTES = 'COMBO CAMA KING CON ESTANTES 1062010753-54N + COLCHON IMPERIAL'
NEGRO_908 = 'COMBO CAMA KING COLOR BLACK 908KBK + COLCHON FIRST CLASS'
GRIS_908 = 'COMBO CAMA KING COLOR GREY 908KGR + COLCHON FIRST CLASS'
SOFAS = 'COMBO DE 2 SOFÁS BLANCOS DE 2 Y 3 PUESTOS 77090'


@tagged('post_install', '-at_install')
class TestLecturaDelArchivoReal(TransactionCase):

    def test_se_lee_completo_sin_errores(self):
        combos, errores = RC.filas_combos(COMBOS_REALES)
        self.assertEqual(errores, [])
        self.assertEqual(len(combos), 71)
        self.assertEqual(sum(len(c['grupos']) for c in combos), 145)
        self.assertEqual([c['codigo'] for c in combos if c['codigo']], ['C-W160969417'],
                         'Solo uno trae código: los demás se identifican por su nombre')

    def test_los_tres_combos_con_opcion_de_colchon_y_el_camarote_de_cuatro_grupos(self):
        combos = {c['nombre']: c for c in RC.filas_combos(COMBOS_REALES)[0]}
        con_opciones = sorted(n for n, c in combos.items() if any(g['a_escoger'] for g in c['grupos']))
        self.assertEqual(len(con_opciones), 3)
        grupo = next(g for g in combos[UP_TWIN]['grupos'] if g['a_escoger'])
        self.assertEqual([(o['codigo'], o['extra']) for o in grupo['opciones']], [('IM-2001', 0.0), ('T101', 15.0)])
        camarote = combos[CAMAROTE]['grupos']
        self.assertEqual([[o['codigo'] for o in g['opciones']] for g in camarote],
                         [['IM-2001', 'T101'], ['IM-2001'], ['IM-2001'], ['W160969418']])
        self.assertEqual([g['a_escoger'] for g in camarote], [True, False, False, False])

    def test_una_pieza_con_cantidad_2_son_dos_grupos_del_mismo_producto(self):
        combo = next(c for c in RC.filas_combos(COMBOS_REALES)[0] if 'ESTANTES 1062010736N' in c['nombre'])
        self.assertEqual([[o['codigo'] for o in g['opciones']] for g in combo['grupos']],
                         [['CSOK-10'], ['1062010736N'], ['1062010736N']])

    def test_las_seis_piezas_sin_codigo_se_leen_con_su_nombre(self):
        sin_codigo = {o['nombre'] for c in RC.filas_combos(COMBOS_REALES)[0] for g in c['grupos']
                      for o in g['opciones'] if not o['codigo']}
        self.assertEqual(sin_codigo, {
            'CAMA FELPA KING BEIGE 888', 'CAMA FELPA KING WHITE HK-HK-BF-022-N-K-1-W',
            'CAMA FELPA QUEEN WHITE XHT022-Q-W', 'CAMA KING COLOR BLAK LTSC-01-6877 K BL',
            'CAMA KING CON ESTANTES 1062010753'})   # 5: la sexta (Y0300300) es del combo archivado, que ya no viene


@tagged('post_install', '-at_install')
class TestCargaDelArchivoReal(TransactionCase):

    def setUp(self):
        super().setUp()
        self.combos, _errores = RC.filas_combos(COMBOS_REALES)

    def cargar(self, **opciones):
        return C.cargar_combos(self.env, self.combos, **opciones)[0]

    def producto(self, nombre):
        return self.env['product.template'].search([('name', '=', nombre)])

    def piezas(self, plantilla):
        return [[i.product_id.default_code for i in g.combo_item_ids] for g in plantilla.combo_ids.sorted('sequence')]

    def test_69_de_los_71_resuelven_contra_el_catalogo_y_2_quedan_con_su_pieza_que_falta(self):
        resumen = self.cargar()
        self.assertEqual(len(resumen['convertidos']), 47, 'Los que ya estaban como producto suelto')
        self.assertEqual(len(resumen['creados']), 22, 'Los que no estaban: se crean sin publicar')
        self.assertEqual([c[0] for c in resumen['con_error']], [KING_CON_ESTANTES, SOFAS])
        self.assertEqual(sorted(p for p, _n in resumen['piezas_faltantes']), [
            '77090-2: no hay un producto con ese código', '77090-3: no hay un producto con ese código',
            'CAMA KING CON ESTANTES 1062010753: no hay un producto con ese nombre '
            '(la pieza no tiene código: se busca por su nombre exacto)'])
        self.assertEqual((resumen['necesitan_revision'], resumen['posibles_duplicados'], resumen['otra_estructura']),
                         ([], [], []))

    def test_los_combos_convertidos_conservan_id_nombre_y_precio_y_los_nuevos_no_se_publican(self):
        antes = {p.name: (p.id, p.list_price) for p in self.env['product.template'].search(
            [('name', 'like', 'COMBO %'), ('type', '=', 'consu')])}
        self.assertEqual(len(antes), 49)
        resumen = self.cargar()
        for nombre in resumen['convertidos']:
            combo = self.producto(nombre)
            self.assertEqual((combo.id, combo.list_price, combo.type), (*antes[nombre], 'combo'))
            self.assertFalse(combo.is_published)
        nuevos = [self.producto(n) for n in resumen['creados']]
        self.assertEqual({(c.type, c.is_published, c.sale_ok) for c in nuevos}, {('combo', False, True)})
        self.assertTrue(all(c.list_price > 0 for c in nuevos), 'Con el precio del archivo')

    def test_el_informe_marca_lo_que_no_coincide_con_el_nombre(self):
        no_coinciden = dict(self.cargar()['no_coinciden'])
        self.assertEqual(sorted(no_coinciden), sorted([NEGRO_908, GRIS_908, KING_CON_ESTANTES]))
        self.assertIn('el nombre dice la cama [908KBK]', no_coinciden[NEGRO_908])
        self.assertIn('trae [908KBE]', no_coinciden[NEGRO_908])
        self.assertIn('el nombre dice la cama [908KGR]', no_coinciden[GRIS_908])
        self.assertIn('colchón «IMPERIAL»', no_coinciden[KING_CON_ESTANTES])
        self.assertIn('FIRST CLASS', no_coinciden[KING_CON_ESTANTES])
        self.assertIn('no se cargó', no_coinciden[KING_CON_ESTANTES])
        self.assertEqual(self.piezas(self.producto(NEGRO_908)), [['908KBE'], ['CSOK-10']], 'Tal cual el archivo')

    def test_con_la_casilla_se_corrige_la_cama_por_el_codigo_del_nombre(self):
        resumen = self.cargar(corregir_cama=True)
        self.assertEqual(sorted(c[0] for c in resumen['corregidos']), sorted([NEGRO_908, GRIS_908]))
        self.assertEqual(self.piezas(self.producto(NEGRO_908)), [['908KBK'], ['CSOK-10']])
        self.assertEqual(self.piezas(self.producto(GRIS_908)), [['908KGR'], ['CSOK-10']])
        self.assertEqual(self.piezas(self.producto('COMBO CAMA KING COLOR BEIGE 908KBE + COLCHON FIRST CLASS')),
                         [['908KBE'], ['CSOK-10']], 'El beige no se toca: su código sí es 908KBE')
        self.assertEqual([c[0] for c in resumen['no_coinciden']], [KING_CON_ESTANTES])

    def test_el_precio_del_archivo_solo_se_aplica_si_no_habia_y_se_informa_lo_que_difiere(self):
        resumen = self.cargar()
        self.assertEqual(resumen['precio_puesto'], [])
        gris = 'COMBO CAMA KING COLOR GREY N-F12002-K-GR + COLCHON FIRST CLASS'
        diferencias = {c[0]: c[1:] for c in resumen['precio_distinto']}
        self.assertEqual(diferencias[gris], (389.99, 139.99))
        self.assertEqual(self.producto(gris).list_price, 139.99, 'No se pisa el precio que ya tenía')
        nuevo = self.producto('COMBO CAMA KING COLOR BEIGE 908KBE + COLCHON FIRST CLASS')
        self.assertEqual((nuevo.type, nuevo.list_price), ('combo', 439.99), 'No estaba: se creó con el del archivo')

    def test_un_producto_sin_precio_recibe_el_del_archivo(self):
        combo = self.producto('COMBO CAMA TWIN WHITE BF039-T-WH + COLCHÓN IMPERIAL')
        combo.list_price = 0
        resumen = self.cargar()
        self.assertEqual(combo.list_price, 175.99)
        self.assertIn('COMBO CAMA TWIN WHITE BF039-T-WH + COLCHÓN IMPERIAL', resumen['precio_puesto'])

    def test_volver_a_cargar_no_cambia_nada(self):
        self.cargar()
        grupos = self.env['product.combo'].search_count([])
        resumen = self.cargar()
        self.assertEqual((len(resumen['ya_estaban']), resumen['creados'], resumen['convertidos']), (69, [], []))
        self.assertEqual(self.env['product.combo'].search_count([]), grupos)

    def test_con_las_tres_piezas_que_faltan_creadas_se_cargan_los_71(self):
        """Productos de prueba para lo que el catálogo del repo no trae (en producción vienen de productos.csv)."""
        itbms = self.env.ref('base.main_company').account_sale_tax_id
        for codigo, nombre, precio in (('77090-2', 'SOFÁ DE 2 PUESTOS COLOR BLANCO 77090-2', 120.0),
                                       ('77090-3', 'SOFÁ DE 3 PUESTOS COLOR BLANCO 77090-3', 150.0),
                                       ('', 'CAMA KING CON ESTANTES 1062010753', 160.0)):
            self.env['product.product'].create({
                'name': nombre, 'default_code': codigo or False, 'type': 'consu', 'is_storable': True,
                'list_price': precio, 'taxes_id': [(6, 0, itbms.ids)]})
        resumen = self.cargar()
        self.assertEqual((len(resumen['creados']), len(resumen['convertidos']), resumen['con_error']), (23, 48, []))
        self.assertEqual(resumen['piezas_faltantes'], [])
        self.assertEqual(self.piezas(self.producto(SOFAS)), [['77090-2'], ['77090-3']])
        camarote = self.producto(CAMAROTE)
        self.assertEqual(self.piezas(camarote), [['IM-2001', 'T101'], ['IM-2001'], ['IM-2001'], ['W160969418']])
        self.assertEqual(self.piezas(self.producto(UP_TWIN)), [['IM-2001', 'T101'], ['SKU: HDSF-SF-T-BK']])
        estantes = self.producto('COMBO CAMA KING GREY CON ESTANTES 1062010736N Y 37N + COLCHON FIRST CLASS')
        self.assertEqual(self.piezas(estantes), [['CSOK-10'], ['1062010736N'], ['1062010736N']])
        todos = self.env['product.template'].search([('name', 'like', 'COMBO %'), ('type', '=', 'combo')])
        self.assertEqual(len(todos), 71)
        self.assertTrue(all(len(t.combo_ids) >= 2 for t in todos))

    def test_el_informe_del_asistente_separa_lo_resuelto_de_lo_que_falta(self):
        admin = self.env.ref('base.user_admin')
        asistente = self.env['dcasa.migracion.carga'].with_user(admin).create({
            'archivo_combos': base64.b64encode(ejemplos.como_bytes(COMBOS_REALES))})
        asistente.action_revisar()
        informe = asistente.informe
        self.assertFalse(self.producto(SOFAS), 'Revisar no crea nada')
        self.assertIn('Combos de cama y colchón (combos.csv)', informe)
        self.assertIn('No se cargaron porque les falta una pieza en el catálogo: <b>2</b>', informe)
        self.assertIn('Piezas que faltan en el catálogo', informe)
        self.assertIn('77090-2', informe)
        self.assertIn('No coincide con el nombre', informe)
        self.assertIn('908KBK', informe)
        self.assertIn('Corregir la cama por el código del nombre', informe)
        self.assertEqual(self.env['product.template'].search_count([('type', '=', 'combo')]), 0,
                         'Revisar no cambia nada')


@tagged('post_install', '-at_install')
class TestVenderLosCombosDelArchivo(TransactionCase):
    """Con el archivo real cargado: el reparto del precio es el del sistema anterior y las opciones funcionan."""

    def setUp(self):
        super().setUp()
        combos, _errores = RC.filas_combos(COMBOS_REALES)
        C.cargar_combos(self.env, combos)
        self.cliente = self.env['res.partner'].create({'name': 'Cliente de Prueba Archivo Real'})

    def combo(self, nombre):
        return self.env['product.template'].search([('name', '=', nombre)]).product_variant_id

    def test_el_reparto_del_precio_es_como_en_el_sistema_anterior(self):
        """BOX SPRING FULL + COLCHON IMPERIAL 146.99, con piezas de 96.99 y 59.99: 90.82 + 56.17 = 146.99."""
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        linea = orden._dcasa_agregar_producto(self.combo(BOX_SPRING), 1)
        piezas = orden.order_line - linea
        self.assertEqual({p.product_id.default_code: p.price_unit for p in piezas},
                         {'IM-2002': 90.82, 'N-F10018-F-BK-FULL': 56.17})
        self.assertEqual((linea.price_subtotal, orden.amount_untaxed), (0.0, 146.99))
        self.assertEqual((orden.amount_tax, orden.amount_total), (10.29, 157.28), 'ITBMS 7 % en las piezas')

    def test_la_factura_lleva_el_combo_en_cero_como_titulo_y_las_piezas_debajo(self):
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        orden._dcasa_agregar_producto(self.combo(BOX_SPRING), 1)
        orden.action_confirm()
        factura = orden._create_invoices()
        factura.action_post()
        self.assertEqual(factura.invoice_line_ids.mapped('display_type'), ['line_section', 'product', 'product'])
        self.assertEqual(factura.invoice_line_ids[0].name, BOX_SPRING + ' x 1')
        self.assertEqual((factura.amount_untaxed, factura.amount_total), (146.99, 157.28))

    def test_el_combo_con_opcion_de_colchon_cobra_el_extra_del_que_se_escoge(self):
        combo = self.combo(UP_TWIN)
        grupo = combo.combo_ids.filtered(lambda g: len(g.combo_item_ids) > 1)
        flex = grupo.combo_item_ids.filtered(lambda i: i.product_id.default_code == 'T101').product_id
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        with self.assertRaisesRegex(Exception, 'hay que escoger'):
            orden._dcasa_agregar_producto(combo, 1)
        linea = orden._dcasa_agregar_producto(combo, 1, elecciones={grupo.id: flex.id})
        piezas = orden.order_line - linea
        self.assertIn('T101', piezas.product_id.mapped('default_code'))
        self.assertEqual(sum(piezas.mapped('price_subtotal')), 155.99 + 15.0)

    def test_el_camarote_lleva_tres_colchones_y_el_camarote(self):
        combo = self.combo(CAMAROTE)
        grupo = combo.combo_ids.filtered(lambda g: len(g.combo_item_ids) > 1)
        imperial = grupo.combo_item_ids.filtered(lambda i: i.product_id.default_code == 'IM-2001').product_id
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        linea = orden._dcasa_agregar_producto(combo, 1, elecciones={grupo.id: imperial.id})
        piezas = orden.order_line - linea
        self.assertEqual(sorted(piezas.mapped('product_id.default_code')),
                         ['IM-2001', 'IM-2001', 'IM-2001', 'W160969418'])
        self.assertEqual(sum(piezas.mapped('price_subtotal')), 418.99)
        orden.action_confirm()
        (entrega,) = orden.picking_ids
        self.assertEqual(sorted(entrega.move_ids.mapped('product_id.default_code')),
                         ['IM-2001', 'IM-2001', 'IM-2001', 'W160969418'])
