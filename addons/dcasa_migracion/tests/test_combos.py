"""Combos de cama + colchón en Odoo: cargar combos.csv, convertir los que ya estaban,
armarlos desde su nombre y venderlos.

Todo con productos y precios inventados («PRUEBA-…»), salvo la prueba de los nombres reales del inventario anterior, que
usa el catálogo del propio módulo ``dcasa_catalogo`` (sin datos de personas).
"""
import base64

from odoo.addons.dcasa_catalogo.catalogo import atributo_tamano
from odoo.addons.dcasa_migracion import combos as C
from odoo.addons.dcasa_migracion import reglas_combos as RC
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from . import ejemplos

BOM = '﻿'
CABECERA = 'codigo_combo,nombre_combo,precio_combo,codigo_componente,nombre_componente,cantidad,precio_extra'
NOMBRE_VIEJO = 'COMBO CAMA PRUEBA KING PRUEBA-CAMA-K + COLCHON MARCAPRUEBA'
FILAS_VIEJO = (f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-CAMA-K,CAMA PRUEBA KING,1,0',
               f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-COL-K,COLCHON,1,0')


def _csv(*filas):
    return BOM + '\n'.join([CABECERA, *filas, ''])


def _b64(texto):
    return base64.b64encode(ejemplos.como_bytes(texto))


class CombosCase(TransactionCase):
    """Camas y colchones inventados y un combo viejo (producto suelto, sin estructura), como el del sistema anterior."""

    def setUp(self):
        super().setUp()
        self.company = self.env.ref('base.main_company')
        self.admin = self.env.ref('base.user_admin')
        self.Carga = self.env['dcasa.migracion.carga'].with_user(self.admin)
        self.itbms = self.env['account.tax'].search([
            ('company_id', '=', self.company.id), ('type_tax_use', '=', 'sale'), ('amount', '=', 7),
            ('price_include', '=', False)], limit=1)
        self.cama_k = self._producto('PRUEBA-CAMA-K', 'CAMA PRUEBA KING PRUEBA-CAMA-K', 150.0)
        self.col_k = self._producto('PRUEBA-COL-K', 'COLCHON MARCAPRUEBA KING', 200.0)
        self.cama_t = self._producto('PRUEBA-CAMA-T', 'CAMA PRUEBA TWIN PRUEBA-CAMA-T', 90.0)
        self.col_t = self._producto('PRUEBA-COL-T', 'COLCHON MARCAPRUEBA TWIN', 80.0)
        self.viejo = self._combo_viejo(NOMBRE_VIEJO, 320.0)

    def _producto(self, codigo, nombre, precio, **valores):
        return self.env['product.product'].create({
            'name': nombre, 'default_code': codigo, 'type': 'consu', 'is_storable': True, 'list_price': precio,
            'taxes_id': [(6, 0, self.itbms.ids)], **valores})

    def _combo_viejo(self, nombre, precio, codigo=False, tamano='King'):
        """Como los que dejó la carga del inventario anterior: tipo bien, sin publicar, con su línea «Tamaño»."""
        atributo, valores = atributo_tamano(self.env)
        return self.env['product.template'].create({
            'name': nombre, 'default_code': codigo, 'type': 'consu', 'is_storable': True, 'list_price': precio,
            'taxes_id': [(6, 0, self.itbms.ids)], 'is_published': False,
            'attribute_line_ids': [(0, 0, {'attribute_id': atributo.id, 'value_ids': [(6, 0, valores[tamano].ids)]})]})

    def cargar(self, *filas, actualizar_precios=False):
        combos, errores = RC.filas_combos(_csv(*filas))
        resumen, _tratados = C.cargar_combos(self.env, combos, actualizar_precios)
        resumen['con_error'] = errores + resumen['con_error']
        return resumen

    def _poner_stock(self, variante, cantidad):
        ubicacion = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1).lot_stock_id
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': variante.id, 'location_id': ubicacion.id, 'inventory_quantity': cantidad,
        })._apply_inventory()

    def piezas(self, plantilla):
        """[[códigos de las opciones de cada grupo]] de un combo."""
        return [[i.product_id.default_code for i in g.combo_item_ids] for g in plantilla.combo_ids.sorted('sequence')]


@tagged('post_install', '-at_install')
class TestCargaDeCombosCsv(CombosCase):

    def test_un_combo_que_ya_estaba_pasa_a_tipo_combo_conservando_todo(self):
        id_plantilla, id_variante = self.viejo.id, self.viejo.product_variant_id.id
        self.assertTrue(self.viejo.attribute_line_ids)
        resumen = self.cargar(*FILAS_VIEJO)
        self.assertEqual((resumen['convertidos'], resumen['creados'], resumen['con_error']), (['PRB-1'], [], []))
        combo = self.env['product.template'].browse(id_plantilla)
        self.assertEqual(combo.type, 'combo')
        self.assertEqual((combo.id, combo.product_variant_id.id), (id_plantilla, id_variante), 'Conserva sus ids')
        self.assertEqual((combo.name, combo.list_price), (NOMBRE_VIEJO, 320.0))
        self.assertEqual(self.piezas(combo), [['PRUEBA-CAMA-K'], ['PRUEBA-COL-K']])
        self.assertEqual(combo.combo_ids.sorted('sequence').mapped('name'), ['Cama', 'Colchón'])
        self.assertFalse(combo.attribute_line_ids, 'Un combo no puede tener atributos')
        self.assertFalse(combo.is_storable)
        self.assertFalse(combo.purchase_ok)
        self.assertFalse(combo.is_published)
        self.assertEqual(combo.default_code, 'PRB-1', 'El combo viejo no tenía código: se le pone el del archivo')
        self.assertEqual(resumen['codigo_puesto'], ['PRB-1'])

    def test_volver_a_cargar_el_mismo_archivo_no_cambia_nada(self):
        self.cargar(*FILAS_VIEJO)
        grupos = self.env['product.combo'].search_count([])
        productos = self.env['product.template'].with_context(active_test=False).search_count([])
        resumen = self.cargar(*FILAS_VIEJO)
        self.assertEqual((resumen['ya_estaban'], resumen['convertidos'], resumen['creados']), (['PRB-1'], [], []))
        self.assertEqual(self.env['product.combo'].search_count([]), grupos, 'No se crean grupos nuevos')
        self.assertEqual(self.env['product.template'].with_context(active_test=False).search_count([]), productos)

    def test_un_combo_nuevo_se_crea_sin_publicar_con_el_precio_del_archivo_y_el_itbms(self):
        nombre = 'COMBO CAMA PRUEBA TWIN NUEVO + COLCHON MARCAPRUEBA'
        resumen = self.cargar(f'NUEVO-1,{nombre},170,PRUEBA-CAMA-T,CAMA,1,0',
                              f'NUEVO-1,{nombre},170,PRUEBA-COL-T,COL,1,0')
        self.assertEqual((resumen['creados'], resumen['con_error']), (['NUEVO-1'], []))
        combo = self.env['product.template'].search([('default_code', '=', 'NUEVO-1')])
        self.assertEqual((combo.type, combo.list_price, combo.is_published, combo.sale_ok),
                         ('combo', 170.0, False, True))
        self.assertEqual(combo.taxes_id, self.itbms, 'ITBMS que se suma; nada de impuesto escrito a mano en el precio')
        self.assertEqual(combo.categ_id, self.env.ref('dcasa_base.product_category_recamaras'))
        self.assertEqual(self.piezas(combo), [['PRUEBA-CAMA-T'], ['PRUEBA-COL-T']])
        self.assertEqual(resumen['avisos_de_precio'], [], '170 = 90 + 80: cuadra')

    def test_sin_precio_un_combo_nuevo_queda_en_cero_y_el_viejo_conserva_el_suyo(self):
        self.cargar('NUEVO-2,COMBO NUEVO SIN PRECIO,0,PRUEBA-CAMA-T,CAMA,1,')
        self.assertEqual(self.env['product.template'].search([('default_code', '=', 'NUEVO-2')]).list_price, 0.0)
        self.cargar(f'PRB-1,{NOMBRE_VIEJO},,PRUEBA-CAMA-K,CAMA,1,', f'PRB-1,{NOMBRE_VIEJO},,PRUEBA-COL-K,COL,1,')
        self.assertEqual(self.viejo.list_price, 320.0)

    def test_el_precio_de_un_combo_que_ya_existe_solo_cambia_si_se_pide(self):
        resumen = self.cargar(*(f.replace(',320,', ',299.99,') for f in FILAS_VIEJO))
        self.assertEqual(self.viejo.list_price, 320.0)
        self.assertEqual(resumen['precio_distinto'], [('PRB-1', 299.99, 320.0)])
        self.cargar(*(f.replace(',320,', ',299.99,') for f in FILAS_VIEJO), actualizar_precios=True)
        self.assertEqual(self.viejo.list_price, 299.99)

    def test_un_componente_que_no_existe_deja_el_combo_sin_cargar_y_se_dice_cual(self):
        resumen = self.cargar(FILAS_VIEJO[0], f'PRB-1,{NOMBRE_VIEJO},320,NO-EXISTE-77,COLCHON QUE NO ESTA,1,0')
        self.assertEqual((resumen['convertidos'], resumen['creados']), ([], []))
        ((clave, motivo),) = resumen['con_error']
        self.assertEqual(clave, 'PRB-1')
        self.assertIn('NO-EXISTE-77', motivo)
        self.assertEqual(self.viejo.type, 'consu', 'No se tocó')
        self.assertFalse(self.viejo.combo_ids)
        self.assertFalse(self.env['product.template'].search([('default_code', '=', 'PRB-1')]), 'Ni se inventó otro')

    def test_una_pieza_sin_codigo_se_busca_por_nombre_exacto_y_si_hay_dos_no_se_adivina(self):
        resumen = self.cargar(f'PRB-1,{NOMBRE_VIEJO},320,,CAMA PRUEBA KING PRUEBA-CAMA-K,1,',
                              f'PRB-1,{NOMBRE_VIEJO},320,,COLCHON MARCAPRUEBA KING,1,')
        self.assertEqual(resumen['convertidos'], ['PRB-1'])
        self._producto('PRUEBA-COL-K2', 'COLCHON REPETIDO', 100.0)
        self._producto('PRUEBA-COL-K3', 'COLCHON REPETIDO', 100.0)
        resumen = self.cargar('PRB-9,COMBO REPETIDO,100,,COLCHON REPETIDO,1,')
        self.assertIn('varios productos con ese nombre', resumen['con_error'][0][1])

    def test_un_codigo_con_el_sufijo_de_tamano_de_las_variantes_se_encuentra(self):
        """El inventario anterior trae «XHT022-F-W»; el catálogo tiene «XHT022-F-W-FULL» (lo dice el nombre)."""
        self._producto('PRUEBA-FELPA-F-W-FULL', 'Cama de felpa de prueba (Full)', 129.99)
        resumen = self.cargar('PRB-F,COMBO FELPA FULL,200,PRUEBA-FELPA-F-W,CAMA FELPA PRUEBA FULL,1,0',
                              'PRB-F,COMBO FELPA FULL,200,PRUEBA-COL-T,COLCHON,1,0')
        self.assertEqual((resumen['creados'], resumen['con_error']), (['PRB-F'], []))
        combo = self.env['product.template'].search([('default_code', '=', 'PRB-F')])
        self.assertEqual(self.piezas(combo)[0], ['PRUEBA-FELPA-F-W-FULL'])

    def test_una_pieza_archivada_o_que_es_otro_combo_no_se_acepta(self):
        self.cama_t.active = False
        resumen = self.cargar('PRB-A,COMBO A,100,PRUEBA-CAMA-T,CAMA,1,0')
        self.assertIn('archivado', resumen['con_error'][0][1])
        self.cargar(*FILAS_VIEJO)
        resumen = self.cargar('PRB-B,COMBO B,100,PRB-1,UN COMBO,1,0')
        self.assertIn('es otro combo', resumen['con_error'][0][1])

    def test_una_pieza_con_cantidad_son_varios_grupos(self):
        resumen = self.cargar('CAMAROTE-1,COMBO CAMAROTE PRUEBA,300,PRUEBA-CAMA-T,CAMAROTE,1,0',
                              'CAMAROTE-1,COMBO CAMAROTE PRUEBA,300,PRUEBA-COL-T,COLCHON TWIN,3,0')
        self.assertEqual(resumen['creados'], ['CAMAROTE-1'])
        combo = self.env['product.template'].search([('default_code', '=', 'CAMAROTE-1')])
        self.assertEqual(self.piezas(combo), [['PRUEBA-CAMA-T'], ['PRUEBA-COL-T'], ['PRUEBA-COL-T'], ['PRUEBA-COL-T']])
        self.assertEqual(combo.combo_ids.sorted('sequence').mapped('name'),
                         ['Cama', 'Colchón 1 de 3', 'Colchón 2 de 3', 'Colchón 3 de 3'])

    def test_un_grupo_con_opciones_y_recargo(self):
        resumen = self.cargar('OPC-1,COMBO CON OPCIONES,350,PRUEBA-CAMA-T,CAMA TWIN,1,0',
                              'OPC-1,,,PRUEBA-COL-T,COLCHON TWIN [opción],1,0',
                              'OPC-1,,,PRUEBA-COL-K,COLCHON KING [opción],1,40')
        self.assertEqual((resumen['creados'], resumen['con_error']), (['OPC-1'], []))
        combo = self.env['product.template'].search([('default_code', '=', 'OPC-1')])
        self.assertEqual(self.piezas(combo), [['PRUEBA-CAMA-T'], ['PRUEBA-COL-T', 'PRUEBA-COL-K']])
        colchon = combo.combo_ids.sorted('sequence')[1]
        self.assertEqual(sorted(colchon.combo_item_ids.mapped('extra_price')), [0.0, 40.0])
        self.assertEqual(colchon.name, 'Colchón (a escoger)')

    def test_sin_piezas_en_el_archivo_no_se_carga(self):
        resumen = self.cargar('VACIO-1,COMBO VACIO,99,,,,')
        self.assertEqual((resumen['sin_piezas'], resumen['creados']), (['VACIO-1'], []))
        self.assertFalse(self.env['product.template'].search([('default_code', '=', 'VACIO-1')]))

    def test_un_combo_que_ya_tiene_otras_piezas_no_se_pisa(self):
        self.cargar(*FILAS_VIEJO)
        resumen = self.cargar(f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-CAMA-T,CAMA,1,0')
        self.assertEqual(resumen['otra_estructura'], ['PRB-1'])
        self.assertEqual(self.piezas(self.viejo), [['PRUEBA-CAMA-K'], ['PRUEBA-COL-K']])

    def test_un_codigo_que_es_de_un_producto_que_no_es_combo_no_lo_convierte(self):
        self._producto('PRB-1', 'Mesa de prueba que usa ese código', 10.0)
        resumen = self.cargar(*FILAS_VIEJO)
        self.assertEqual(resumen['convertidos'], [])
        self.assertIn('no parece un combo', resumen['con_error'][0][1])

    def test_dos_productos_con_el_mismo_nombre_no_se_adivinan(self):
        self._combo_viejo(NOMBRE_VIEJO, 320.0)
        resumen = self.cargar(f',{NOMBRE_VIEJO},320,PRUEBA-CAMA-K,CAMA,1,0',
                              f',{NOMBRE_VIEJO},320,PRUEBA-COL-K,COL,1,0')
        self.assertEqual(resumen['convertidos'], [])
        self.assertIn('varios productos con ese nombre', resumen['con_error'][0][1])

    def test_sin_codigo_en_el_archivo_el_combo_se_identifica_por_su_nombre(self):
        resumen = self.cargar(f',{NOMBRE_VIEJO},320,PRUEBA-CAMA-K,CAMA,1,0',
                              f',{NOMBRE_VIEJO},320,PRUEBA-COL-K,COL,1,0')
        self.assertEqual(resumen['convertidos'], [NOMBRE_VIEJO])
        self.assertEqual(self.viejo.type, 'combo')

    def test_el_precio_que_no_cuadra_con_las_piezas_se_avisa(self):
        resumen = self.cargar('NUEVO-3,COMBO MUY BARATO,100,PRUEBA-CAMA-K,CAMA,1,0',
                              'NUEVO-3,COMBO MUY BARATO,100,PRUEBA-COL-K,COL,1,0')
        self.assertIn('menos que una sola', resumen['avisos_de_precio'][0][1])


    def test_archivados_y_auxiliares_no_se_cargan_y_se_listan(self):
        texto = BOM + '\n'.join([
            CABECERA + ',activo',
            'ARCH-1,COMBO ARCHIVADO,100,PRUEBA-CAMA-T,CAMA,1,0,0',
            ',X COLCHON IMPERIAL TWIN 2/3 PARA COMBO,0,PRUEBA-COL-T,COL,1,0,1',
            'OK-1,COMBO BUENO,100,PRUEBA-CAMA-T,CAMA,1,0,1', ''])
        combos, errores = RC.filas_combos(texto)
        resumen, _tratados = C.cargar_combos(self.env, combos)
        self.assertEqual((errores, resumen['archivados'], resumen['omitidos'], resumen['creados']),
                         ([], ['ARCH-1'], ['X COLCHON IMPERIAL TWIN 2/3 PARA COMBO'], ['OK-1']))
        self.assertFalse(self.env['product.template'].search([('default_code', '=', 'ARCH-1')]))

    def test_el_archivo_con_columnas_en_otro_orden_y_mayusculas_se_carga_igual(self):
        texto = BOM + '\n'.join([
            '"Nombre_Componente","CODIGO_COMPONENTE","precio_combo","Nombre_Combo","Codigo_Combo","Cantidad","Precio_Extra"',
            f'"CAMA PRUEBA KING","PRUEBA-CAMA-K","320","{NOMBRE_VIEJO}","PRB-1","1","0"',
            f'"COLCHON","PRUEBA-COL-K","320","{NOMBRE_VIEJO}","PRB-1","1","0"', ''])
        combos, _ = RC.filas_combos(texto)
        resumen, _tratados = C.cargar_combos(self.env, combos)
        self.assertEqual(resumen['convertidos'], ['PRB-1'])

    def test_si_el_nombre_dice_una_cosa_y_las_piezas_son_otras_se_marca_pero_se_carga_tal_cual(self):
        resumen = self.cargar(f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-CAMA-T,CAMA TWIN,1,0',
                              f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-COL-K,COLCHON,1,0')
        self.assertEqual(resumen['convertidos'], ['PRB-1'], 'Se cargó como dice el archivo')
        self.assertEqual(self.piezas(self.viejo), [['PRUEBA-CAMA-T'], ['PRUEBA-COL-K']])
        ((clave, motivo),) = resumen['no_coinciden']
        self.assertEqual(clave, 'PRB-1')
        self.assertIn('el nombre dice la cama [PRUEBA-CAMA-K]', motivo)
        self.assertIn('trae [PRUEBA-CAMA-T]', motivo)

    def test_si_todo_coincide_con_el_nombre_no_se_marca_nada(self):
        resumen = self.cargar(*FILAS_VIEJO)
        self.assertEqual(resumen['no_coinciden'], [])

    def test_el_nombre_dice_otra_marca_de_colchon(self):
        otro = self._producto('PRUEBA-COL-OTRO-K', 'COLCHON OTRAMARCA KING', 210.0)
        resumen = self.cargar(FILAS_VIEJO[0], f'PRB-1,{NOMBRE_VIEJO},320,{otro.default_code},COLCHON,1,0')
        self.assertIn('colchón «MARCAPRUEBA»', resumen['no_coinciden'][0][1])
        self.assertIn('COLCHON OTRAMARCA KING', resumen['no_coinciden'][0][1])


@tagged('post_install', '-at_install')
class TestUnComboQueNoSeDebeConvertir(CombosCase):
    """Con existencias, movimientos o en una venta abierta no se toca: el informe dice por qué y no se pierde nada."""

    def _revision(self):
        resumen = self.cargar(*FILAS_VIEJO)
        self.assertEqual((resumen['convertidos'], resumen['creados']), ([], []))
        ((clave, motivo),) = resumen['necesitan_revision']
        self.assertEqual(clave, 'PRB-1')
        self.assertEqual(self.viejo.type, 'consu', 'No se convirtió')
        self.assertTrue(self.viejo.attribute_line_ids, 'Ni se le quitó nada')
        self.assertFalse(self.viejo.combo_ids)
        return motivo

    def test_con_existencias_dice_que_hay_que_contarlas(self):
        self._poner_stock(self.viejo.product_variant_id, 3)
        motivo = self._revision()
        self.assertIn('3 unidades en existencia', motivo)
        self.assertIn('ajústalas a 0', motivo)

    def test_ajustadas_las_existencias_a_cero_ya_se_convierte(self):
        """El ajuste de inventario es solo un conteo: no impide convertirlo (si no, nunca se podría)."""
        self._poner_stock(self.viejo.product_variant_id, 3)
        self._revision()
        self._poner_stock(self.viejo.product_variant_id, 0)
        resumen = self.cargar(*FILAS_VIEJO)
        self.assertEqual(resumen['convertidos'], ['PRB-1'])
        self.assertEqual(self.viejo.type, 'combo')

    def test_con_una_entrega_o_recepcion_hecha_no_se_convierte(self):
        variante = self.viejo.product_variant_id
        self._poner_stock(variante, 1)
        cliente = self.env['res.partner'].create({'name': 'Cliente de Prueba Combos'})
        orden = self.env['sale.order'].create({
            'partner_id': cliente.id, 'order_line': [(0, 0, {'product_id': variante.id, 'product_uom_qty': 1})]})
        orden.action_confirm()
        for movimiento in orden.picking_ids.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
        orden.picking_ids.with_context(skip_backorder=True).button_validate()
        self._poner_stock(variante, 0)
        factura = orden._create_invoices()
        factura.action_post()
        self.assertIn('movimientos de inventario', self._revision())

    def test_en_una_cotizacion_abierta(self):
        cliente = self.env['res.partner'].create({'name': 'Cliente de Prueba Combos'})
        orden = self.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [(0, 0, {'product_id': self.viejo.product_variant_id.id, 'product_uom_qty': 1})]})
        self.assertIn(orden.name, self._revision())

    def test_con_varias_medidas_o_colores(self):
        _atributo, valores = atributo_tamano(self.env)
        self.viejo.attribute_line_ids.value_ids = [(6, 0, (valores['King'] | valores['Full']).ids)]
        self.assertEqual(self.viejo.product_variant_count, 2)
        self.assertIn('varias medidas', self._revision())


@tagged('post_install', '-at_install')
class TestAsistenteDeCombos(CombosCase):

    def _asistente(self, **valores):
        return self.Carga.create(valores)

    def test_revisar_no_cambia_nada_y_cargar_exige_haber_revisado(self):
        asistente = self._asistente(archivo_combos=_b64(_csv(*FILAS_VIEJO)))
        with self.assertRaisesRegex(UserError, 'pulsa «Revisar»'):
            asistente.action_cargar()
        asistente.action_revisar()
        self.assertEqual(self.viejo.type, 'consu', 'El ensayo no cambia nada')
        self.assertFalse(self.viejo.combo_ids)
        self.assertIn('Combos de cama y colchón', asistente.informe)
        self.assertIn('Ya existían y pasaron a tipo Combo', asistente.informe)
        asistente.action_cargar()
        self.assertEqual(self.viejo.type, 'combo')
        self.assertIn('CARGA HECHA', asistente.informe)

    def test_el_informe_lista_lo_que_falta_y_lo_que_necesita_revision(self):
        self._poner_stock(self.viejo.product_variant_id, 2)
        asistente = self._asistente(archivo_combos=_b64(_csv(
            *FILAS_VIEJO, 'MAL-1,COMBO CON PIEZA FALTANTE,100,NO-HAY-ESTA,UNA PIEZA,1,0')))
        asistente.action_revisar()
        self.assertIn('Necesitan revisión', asistente.informe)
        self.assertIn('2 unidades en existencia', asistente.informe)
        self.assertIn('NO-HAY-ESTA', asistente.informe)
        self.assertIn('lo que falta en el catálogo no se inventa', asistente.informe)

    def test_si_cambia_la_casilla_o_el_archivo_hay_que_revisar_otra_vez(self):
        asistente = self._asistente(armar_combos_desde_nombre=True)
        asistente.action_revisar()
        asistente.armar_combos_desde_nombre = False
        asistente.archivo_combos = _b64(_csv(*FILAS_VIEJO))
        with self.assertRaisesRegex(UserError, 'Revisar'):
            asistente.action_cargar()

    def test_solo_con_la_casilla_basta_y_sin_nada_se_avisa(self):
        with self.assertRaisesRegex(UserError, 'Armar los combos desde su nombre'):
            self._asistente().action_revisar()
        self._asistente(armar_combos_desde_nombre=True).action_revisar()

    def test_el_archivo_de_otro_tipo_se_explica(self):
        asistente = self._asistente(archivo_combos=_b64(ejemplos.CLIENTES))
        with self.assertRaisesRegex(UserError, 'combos.csv le falta la columna'):
            asistente.action_revisar()

    def test_con_el_archivo_y_la_casilla_juntos_manda_el_archivo(self):
        """Lo que nombra combos.csv no se vuelve a armar desde su nombre."""
        asistente = self._asistente(
            archivo_combos=_b64(_csv(f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-CAMA-T,CAMA TWIN,1,0',
                                     f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-COL-T,COLCHON TWIN,1,0')),
            armar_combos_desde_nombre=True)
        asistente.action_revisar()
        asistente.action_cargar()
        self.assertEqual(self.piezas(self.viejo), [['PRUEBA-CAMA-T'], ['PRUEBA-COL-T']], 'Lo que dice el archivo')

    def test_el_asistente_sigue_siendo_solo_de_administradores(self):
        for metodo in ('action_revisar', 'action_cargar'):
            self.assertTrue(hasattr(self.env['dcasa.migracion.carga'], metodo))
        gerencia = self.env['res.users'].create({
            'name': 'Gerencia Prueba', 'login': 'gerencia_combos_prueba',
            'group_ids': [(6, 0, [self.env.ref('sales_team.group_sale_manager').id])]})
        with self.assertRaises(Exception):  # noqa: B017 (AccessError de la tabla del asistente)
            self.env['dcasa.migracion.carga'].with_user(gerencia).create({'armar_combos_desde_nombre': True})


@tagged('post_install', '-at_install')
class TestArmarDesdeElNombre(CombosCase):

    def setUp(self):
        super().setUp()
        self.cama_q = self._producto('PRUEBA-CAMA-Q', 'CAMA PRUEBA QUEEN PRUEBA-CAMA-Q', 130.0)
        self.col_q = self._producto('PRUEBA-COL-Q', 'COLCHON MARCAPRUEBA QUEEN', 190.0)
        self._producto('PRUEBA-COL-Q2', 'COLCHON MARCAPRUEBA QUEEN', 195.0)  # dos iguales: dudoso
        self.claro = self.viejo
        self.dudoso = self._combo_viejo(
            'COMBO CAMA PRUEBA QUEEN PRUEBA-CAMA-Q + COLCHON MARCAPRUEBA', 330.0, tamano='Queen')
        self.sin_resolver = self._combo_viejo('COMBO CAMA PRUEBA KING PRUEBA-NO-HAY + COLCHON MARCAPRUEBA', 300.0)
        self.camarote = self._combo_viejo(
            'COMBO CAMAROTE PRUEBA TWIN PRUEBA-CAMA-T + 3 COLCHONES MARCAPRUEBA', 300.0, tamano='Twin')

    def armar(self):
        return C.armar_desde_nombre(self.env)

    def _de_prueba(self, lista):
        """Solo lo de esta prueba: los productos reales del catálogo también están en la base."""
        return [x for x in lista if 'PRUEBA' in (x[0] if isinstance(x, tuple) else x)]

    def test_solo_los_claros_se_arman_y_los_dudosos_y_sin_resolver_solo_se_listan(self):
        resumen = self.armar()
        self.assertEqual(sorted(c[0] for c in self._de_prueba(resumen['cargados'])),
                         sorted([self.claro.name, self.camarote.name]))
        self.assertEqual([d[0] for d in self._de_prueba(resumen['dudosos'])], [self.dudoso.name])
        self.assertEqual([s[0] for s in self._de_prueba(resumen['sin_resolver'])], [self.sin_resolver.name])
        self.assertEqual((self.claro.type, self.camarote.type), ('combo', 'combo'))
        self.assertEqual((self.dudoso.type, self.sin_resolver.type), ('consu', 'consu'), 'No se adivina')
        self.assertEqual(self.piezas(self.claro), [['PRUEBA-CAMA-K'], ['PRUEBA-COL-K']])

    def test_el_dudoso_lista_las_opciones_con_precio_y_existencias(self):
        self._poner_stock(self.col_q, 4)
        resumen = self.armar()
        ((_nombre, motivo, opciones),) = self._de_prueba(resumen['dudosos'])
        self.assertIn('hay más de un colchón', motivo)
        textos = [texto for rol, texto in opciones if rol == 'Colchón']
        self.assertEqual(len(textos), 2)
        self.assertTrue(any('PRUEBA-COL-Q]' in t and '$190.00' in t and '4 en existencia' in t for t in textos), textos)

    def test_tres_colchones_son_tres_grupos(self):
        self.armar()
        self.assertEqual(self.piezas(self.camarote),
                         [['PRUEBA-CAMA-T'], ['PRUEBA-COL-T'], ['PRUEBA-COL-T'], ['PRUEBA-COL-T']])

    def test_es_idempotente(self):
        self.armar()
        grupos = self.env['product.combo'].search_count([])
        resumen = self.armar()
        self.assertEqual(self._de_prueba(resumen['cargados']), [])
        self.assertEqual(self.env['product.combo'].search_count([]), grupos)
        self.assertIn(self.claro.name, resumen['ya_estaban'])

    def test_un_claro_con_existencias_necesita_revision_y_no_se_convierte(self):
        self._poner_stock(self.claro.product_variant_id, 1)
        resumen = self.armar()
        self.assertEqual([c[0] for c in self._de_prueba(resumen['necesitan_revision'])], [self.claro.name])
        self.assertEqual(self.claro.type, 'consu')
        self.assertEqual([c[0] for c in self._de_prueba(resumen['cargados'])], [self.camarote.name])

    def test_el_asistente_arma_y_el_ensayo_no_toca_nada(self):
        asistente = self.Carga.create({'armar_combos_desde_nombre': True})
        asistente.action_revisar()
        self.assertEqual(self.claro.type, 'consu')
        self.assertIn('Claros: armados', asistente.informe)
        self.assertIn('Dudosos', asistente.informe)
        self.assertIn(self.dudoso.name, asistente.informe)
        asistente.action_cargar()
        self.assertEqual(self.claro.type, 'combo')
        self.assertEqual(self.dudoso.type, 'consu')

    def test_los_que_ya_eran_combos_se_contrastan_con_su_nombre(self):
        self.cargar(f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-CAMA-T,CAMA TWIN,1,0',
                    f'PRB-1,{NOMBRE_VIEJO},320,PRUEBA-COL-K,COL,1,0')
        resumen = self.armar()
        self.assertEqual([n for n, _m in self._de_prueba(resumen['no_coinciden'])], [self.claro.name])
        self.assertIn('el nombre dice la cama', resumen['no_coinciden'][0][1])
        self.assertEqual(self.piezas(self.claro), [['PRUEBA-CAMA-T'], ['PRUEBA-COL-K']], 'No se toca: solo se avisa')

    def test_precio_y_nombre_del_combo_no_cambian(self):
        self.armar()
        self.assertEqual((self.claro.list_price, self.claro.name), (320.0, NOMBRE_VIEJO))


@tagged('post_install', '-at_install')
class TestLosCombosRealesDelInventarioAnterior(TransactionCase):
    """Con el catálogo real que trae el módulo ``dcasa_catalogo`` (49 combos «COMBO … + COLCHÓN», transcritos de las
    capturas del sistema anterior): cuántos quedan claros, dudosos y sin resolver, y que se pueden vender."""

    def _combos(self):
        pendientes, _ya = C.combos_por_nombre(self.env)
        return pendientes

    def piezas_de(self, plantilla):
        return [[i.product_id.default_code for i in g.combo_item_ids] for g in plantilla.combo_ids.sorted('sequence')]

    def test_los_49_combos_estan_como_productos_sueltos_sin_estructura(self):
        combos = self._combos()
        self.assertEqual(len(combos), 49)
        self.assertEqual(set(combos.mapped('type')), {'consu'})
        self.assertFalse(combos.combo_ids)
        self.assertFalse(any(combos.mapped('is_published')))

    def test_46_claros_2_dudosos_y_1_sin_resolver(self):
        resumen = C.armar_desde_nombre(self.env)
        self.assertEqual(
            (len(resumen['cargados']), len(resumen['dudosos']), len(resumen['sin_resolver']),
             len(resumen['necesitan_revision']), len(resumen['con_error'])), (46, 2, 1, 0, 0))
        self.assertEqual(sorted(d[0] for d in resumen['dudosos']), [
            'COMBO CAMA BUTTERFLY UP TWIN + COLCHO IMPERIAL', 'COMBO CAMA QUEEN W160969417 + COLCHÓN DULCES SUEÑOS'])
        self.assertEqual([s[0] for s in resumen['sin_resolver']],
                         ['COMBO CAMA KING CON ESTANTES 1062010753-54N + COLCHON IMPERIAL'])
        cargados = {c[0] for c in resumen['cargados']}
        self.assertIn('COMBO CAMA FELPA QUEEN WHITE XHT022-Q-W + COLCHON DULCES SUEÑOS', cargados,
                      'La cama Queen de felpa existe sin código: se encuentra por su nombre exacto')
        self.assertEqual(len(self._combos()), 3, 'Quedan sin estructura solo los 3 que no se pudieron armar')

    def test_el_colchon_se_elige_del_inventario_anterior_y_se_anota_el_otro_igual(self):
        resumen = C.armar_desde_nombre(self.env)
        alternativas = {a[0].split(']')[0].strip('['): a for a in resumen['con_alternativa']}
        self.assertEqual(sorted(alternativas), ['CSOK-10', 'DSRSOQ', 'XHT022-T-BG'])
        self.assertEqual(alternativas['CSOK-10'][3], 23, 'Los 23 combos con First Class King')
        self.assertIn('COLCHON-FIRST-CLASS-SEMIORTOPEDICO-KING', alternativas['CSOK-10'][2][0])

    def test_el_unico_precio_que_no_cuadra_se_avisa(self):
        resumen = C.armar_desde_nombre(self.env)
        self.assertEqual([a[0] for a in resumen['avisos_de_precio']],
                         ['COMBO CAMA KING COLOR GREY N-F12002-K-GR + COLCHON FIRST CLASS'])

    def test_ya_armados_no_se_repite(self):
        C.armar_desde_nombre(self.env)
        resumen = C.armar_desde_nombre(self.env)
        self.assertEqual((len(resumen['cargados']), len(resumen['ya_estaban'])), (0, 46))
        self.assertEqual((len(resumen['dudosos']), len(resumen['sin_resolver'])), (2, 1))

    def test_vender_un_combo_armado_de_punta_a_punta(self):
        """El combo de la cama felpa King con el colchón First Class: cotización, venta, entrega y factura."""
        C.armar_desde_nombre(self.env)
        combo = self.env['product.template'].search(
            [('name', '=', 'COMBO CAMA FELPA KING WHITE XHT022-K-W + COLCHÓN FIRST')])
        self.assertEqual((combo.type, combo.list_price), ('combo', 389.99))
        cama = self.env['product.product'].search([('default_code', '=', 'XHT022-K-W')])
        colchon = self.env['product.product'].search([('default_code', '=', 'CSOK-10')])
        self.assertEqual(self.piezas_de(combo), [['XHT022-K-W'], ['CSOK-10']])
        cliente = self.env['res.partner'].create({'name': 'Cliente de Prueba Combo Real'})
        orden = self.env['sale.order'].create({'partner_id': cliente.id})
        linea_combo = orden._dcasa_agregar_producto(combo.product_variant_id, 1)
        piezas = orden.order_line - linea_combo
        self.assertEqual(piezas.product_id, cama | colchon, 'Una línea por la cama y otra por el colchón')
        self.assertEqual((linea_combo.price_subtotal, linea_combo.tax_ids.ids), (0.0, []), 'La línea del combo no suma')
        self.assertEqual(sum(piezas.mapped('price_subtotal')), 389.99, 'El precio del combo va repartido en las piezas')
        self.assertEqual((orden.amount_untaxed, orden.amount_tax, orden.amount_total), (389.99, 27.30, 417.29))
        self.assertEqual(set(piezas.tax_ids.mapped('amount')), {7.0}, 'Cada pieza con su ITBMS de 7 %')
        orden.action_confirm()
        (entrega,) = orden.picking_ids
        self.assertEqual(sorted(entrega.move_ids.mapped('product_id.default_code')), ['CSOK-10', 'XHT022-K-W'],
                         'La entrega descuenta la cama y el colchón, nunca el combo')
        for movimiento in entrega.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
        entrega.with_context(skip_backorder=True).button_validate()
        self.assertEqual(entrega.state, 'done')
        factura = orden._create_invoices()
        factura.action_post()
        self.assertEqual((factura.amount_untaxed, factura.amount_tax, factura.amount_total), (389.99, 27.30, 417.29))
        self.assertEqual(factura.invoice_line_ids.mapped('display_type'), ['line_section', 'product', 'product'])
        seccion = factura.invoice_line_ids.filtered(lambda ln: ln.display_type == 'line_section')
        self.assertIn('COMBO CAMA FELPA KING WHITE', seccion.name)
