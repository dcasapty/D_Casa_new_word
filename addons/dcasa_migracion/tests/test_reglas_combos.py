"""Combos: lectura de combos.csv, lectura de los nombres y búsqueda de la cama y el colchón (reglas puras)."""
from odoo.addons.dcasa_catalogo.inventario_anterior import leer_inventario_anterior
from odoo.addons.dcasa_catalogo.reglas import clase_de_fila_inventario
from odoo.addons.dcasa_migracion import reglas
from odoo.addons.dcasa_migracion import reglas_combos as RC
from odoo.tests import BaseCase, tagged

BOM = '﻿'
CABECERA = 'codigo_combo,nombre_combo,precio_combo,codigo_componente,nombre_componente,cantidad,precio_extra'


def _csv(*filas):
    return BOM + '\n'.join([CABECERA, *filas, ''])


def _pieza(id_, codigo, nombre, tamano, precio=100.0, origen='catalogo', existencias=0.0):
    return {'id': id_, 'codigo': codigo, 'nombre': nombre, 'tamano': tamano, 'precio': precio,
            'existencias': existencias, 'origen': origen}


@tagged('post_install', '-at_install')
class TestLecturaDeCombosCsv(BaseCase):

    def test_una_pieza_es_un_grupo_de_una_sola_opcion(self):
        combos, errores = RC.filas_combos(_csv(
            'CB-P1,COMBO CAMA PRUEBA KING + COLCHON PRUEBA,300,CAMA-P-K,CAMA PRUEBA KING,1,0',
            'CB-P1,COMBO CAMA PRUEBA KING + COLCHON PRUEBA,300,COL-P-K,COLCHON PRUEBA KING,1,'))
        self.assertEqual(errores, [])
        (combo,) = combos
        self.assertEqual((combo['clave'], combo['codigo'], combo['precio'], combo['sin_piezas']),
                         ('CB-P1', 'CB-P1', 300.0, False))
        self.assertEqual([g['nombre'] for g in combo['grupos']], ['Cama', 'Colchón'])
        self.assertEqual([[o['codigo'] for o in g['opciones']] for g in combo['grupos']], [['CAMA-P-K'], ['COL-P-K']])
        self.assertEqual([g['a_escoger'] for g in combo['grupos']], [False, False])

    def test_sin_codigo_el_combo_se_identifica_por_su_nombre(self):
        combos, _ = RC.filas_combos(_csv(
            ',COMBO SIN CODIGO,150.5,CAMA-P-T,CAMA PRUEBA TWIN,1,', ',COMBO SIN CODIGO,150.5,COL-P-T,COLCHON TWIN,1,'))
        self.assertEqual((combos[0]['clave'], combos[0]['codigo'], combos[0]['nombre']),
                         ('COMBO SIN CODIGO', '', 'COMBO SIN CODIGO'))
        self.assertEqual(len(combos), 1, 'Las dos filas son un solo combo')

    def test_precio_cero_o_vacio_es_no_se_registro(self):
        combos, _ = RC.filas_combos(_csv('CB-1,N,0,A,Cama,1,', 'CB-2,N2,,A,Cama,1,'))
        self.assertEqual([c['precio'] for c in combos], [None, None])

    def test_una_pieza_con_cantidad_son_varios_grupos_iguales(self):
        """Odoo no tiene cantidad por opción: 3 colchones son 3 grupos del mismo colchón."""
        combos, _ = RC.filas_combos(_csv(
            'CB-3,COMBO CAMAROTE,418.99,CAM-3,CAMAROTE TRIPLE,1,0',
            'CB-3,COMBO CAMAROTE,418.99,COL-T,COLCHON TWIN,3,0'))
        grupos = combos[0]['grupos']
        self.assertEqual([g['nombre'] for g in grupos], ['Cama', 'Colchón 1 de 3', 'Colchón 2 de 3', 'Colchón 3 de 3'])
        self.assertEqual({g['opciones'][0]['codigo'] for g in grupos[1:]}, {'COL-T'})

    def test_las_piezas_marcadas_opcion_son_un_solo_grupo_para_escoger(self):
        combos, errores = RC.filas_combos(_csv(
            'CB-4,COMBO CON OPCIONES,500,CAMA-Q,CAMA QUEEN,1,0',
            'CB-4,,,COL-1,COLCHON UNO [opción],1,0',
            'CB-4,,,COL-2,COLCHON DOS [Opcion],1,25.5'))
        self.assertEqual(errores, [])
        cama, colchon = combos[0]['grupos']
        self.assertFalse(cama['a_escoger'])
        self.assertTrue(colchon['a_escoger'])
        self.assertEqual(colchon['nombre'], 'Colchón (a escoger)')
        self.assertEqual([(o['codigo'], o['nombre'], o['extra']) for o in colchon['opciones']],
                         [('COL-1', 'COLCHON UNO', 0.0), ('COL-2', 'COLCHON DOS', 25.5)])

    def test_la_columna_grupo_separa_varios_grupos_de_opciones(self):
        cabecera = CABECERA + ',grupo'
        texto = BOM + '\n'.join([
            cabecera,
            'CB-5,COMBO DOS GRUPOS,500,COL-1,COLCHON UNO [opción],1,0,colchon',
            'CB-5,,,COL-2,COLCHON DOS [opción],1,0,colchon',
            'CB-5,,,ALM-1,ALMOHADA UNO [opción],1,0,almohada',
            'CB-5,,,ALM-2,ALMOHADA DOS [opción],1,0,almohada', ''])
        combos, errores = RC.filas_combos(texto)
        self.assertEqual(errores, [])
        self.assertEqual([[o['codigo'] for o in g['opciones']] for g in combos[0]['grupos']],
                         [['COL-1', 'COL-2'], ['ALM-1', 'ALM-2']])

    def test_filas_seguidas_con_la_marca_son_un_grupo_y_una_pieza_fija_en_medio_lo_parte(self):
        (combo,), errores = RC.filas_combos(_csv(
            'CB-8,COMBO,100,A,COL UNO [opción],1,0', 'CB-8,,,B,COL DOS [opción],1,15',
            'CB-8,,,C,CAMA FIJA,1,0',
            'CB-8,,,D,ALMOHADA UNO [opción],1,0', 'CB-8,,,E,ALMOHADA DOS [opción],1,0'))
        self.assertEqual(errores, [])
        self.assertEqual([[o['codigo'] for o in g['opciones']] for g in combo['grupos']],
                         [['A', 'B'], ['C'], ['D', 'E']])

    def test_un_combo_sin_piezas_se_lista_pero_no_tiene_grupos(self):
        combos, errores = RC.filas_combos(_csv('CB-6,COMBO VACIO,99,,,,'))
        self.assertEqual(errores, [])
        self.assertEqual((combos[0]['sin_piezas'], combos[0]['grupos']), (True, []))

    def test_un_combo_mal_escrito_no_se_carga_y_los_demas_si(self):
        combos, errores = RC.filas_combos(_csv(
            'MAL-1,Combo cantidad cero,100,A,Cama,0,0',
            'MAL-2,Combo cantidad con decimales,100,A,Cama,1.5,0',
            'MAL-3,Combo extra negativo,100,A,Cama,1,-5',
            'MAL-4,Combo dos precios,100,A,Cama,1,0', 'MAL-4,Combo dos precios,200,B,Colchon,1,0',
            'MAL-5,Combo con cantidad sola,100,,,2,',
            ',,,A,Cama,1,0',
            'BUENO,Combo bueno,100,A,Cama,1,0'))
        self.assertEqual([c['clave'] for c in combos], ['BUENO'])
        motivos = dict(errores)
        self.assertIn('cantidad', motivos['MAL-1'])
        self.assertIn('cantidad', motivos['MAL-2'])
        self.assertIn('extra', motivos['MAL-3'])
        self.assertIn('precio del combo', motivos['MAL-4'])
        self.assertIn('ninguna pieza', motivos['MAL-5'])
        self.assertIn('fila 8', [k for k in motivos if k.startswith('fila')][0])

    def test_las_opciones_de_un_grupo_piden_la_misma_cantidad(self):
        _combos, errores = RC.filas_combos(_csv(
            'CB-7,Combo,100,A,COL UNO [opción],1,0', 'CB-7,Combo,100,B,COL DOS [opción],2,0'))
        self.assertIn('misma cantidad', errores[0][1])

    def test_un_archivo_que_no_es_el_de_combos_se_explica(self):
        with self.assertRaisesRegex(reglas.ErrorDeArchivo, 'columna «codigo_componente»'):
            RC.filas_combos('codigo_combo,nombre_combo\nA,B\n')
        with self.assertRaisesRegex(reglas.ErrorDeArchivo, 'no es un número en la columna cantidad'):
            RC.filas_combos(_csv('A,B,10,C,D,mucho,0'))
        with self.assertRaisesRegex(reglas.ErrorDeArchivo, 'vacío'):
            RC.filas_combos('')


@tagged('post_install', '-at_install')
class TestLecturaDeNombres(BaseCase):

    def test_se_lee_la_cama_el_colchon_y_el_tamano(self):
        a = RC.analizar_nombre('COMBO CAMA FELPA KING WHITE XHT022-K-W + COLCHÓN FIRST')
        self.assertEqual((a['ok'], a['cama'], a['tamano'], a['marca'], a['cantidad_colchones']),
                         (True, 'CAMA FELPA KING WHITE XHT022-K-W', 'king', 'first', 1))

    def test_las_variantes_con_errores_del_sistema_anterior(self):
        marcas = {
            'COMBO CAMA BUTTERFLY UP TWIN + COLCHO IMPERIAL': 'imperial',
            'COMBO CAMA KING COLOR BROWN N-F12002-K-BR +COLCHON FIRST CLASS': 'first class',
            'COMBO CAMA FULL COLOR GREY 2071 / J02HF-BF-2208GF + COLCHON BUEN SUEÑO': 'buen sueno',
            'COMBO CAMA FELPA QUEEN WHITE XHT022-Q-W + COLCHON DULCES SUEÑOS': 'dulces suenos',
        }
        for nombre, marca in marcas.items():
            with self.subTest(nombre):
                analisis = RC.analizar_nombre(nombre)
                self.assertTrue(analisis['ok'])
                self.assertEqual(analisis['marca'], marca)

    def test_un_error_de_dedo_en_la_palabra_colchon_se_entiende(self):
        analisis = RC.analizar_nombre('COMBO CAMA FELPA KING WHITE HK-HK-BF-022-N-K-1-W + CPLCHON FIRST CLASS')
        self.assertTrue(analisis['ok'])
        self.assertEqual((analisis['marca'], analisis['tamano']), ('first class', 'king'))
        self.assertTrue(RC.analizar_nombre('COMBO CAMA KING COLOR BEIGE 811KBE+ COLCHON FIRST CLASS')['ok'])

    def test_varios_colchones_y_box_spring(self):
        a = RC.analizar_nombre('COMBO CAMAROTE TRIPLE 3 TWIN W160969418 + 3 COLCHONES IMPERIAL')
        self.assertEqual((a['cantidad_colchones'], a['tamano'], a['marca']), (3, 'twin', 'imperial'))
        b = RC.analizar_nombre('COMBO BOX SPRING DE METAL SENCILLO TAMAÑO FULL / N-F10018-F-BK + COLCHON IMPERIAL')
        self.assertEqual((b['tamano'], b['cama']), ('full', 'BOX SPRING DE METAL SENCILLO TAMAÑO FULL / N-F10018-F-BK'))

    def test_un_nombre_que_no_es_de_combo_no_se_lee(self):
        for nombre, problema in (('CAMA FULL 1893F', 'COMBO'), ('COMBO CAMA FULL SIN COLCHON', '+'),
                                 ('COMBO CAMA FULL + ALMOHADA', 'colchón'), ('COMBO + COLCHON IMPERIAL', 'cama'),
                                 ('COMBO CAMA FULL + COLCHON', 'marca')):
            with self.subTest(nombre):
                analisis = RC.analizar_nombre(nombre)
                self.assertFalse(analisis['ok'])
                self.assertIn(problema, analisis['problema'])

    def test_todos_los_combos_del_inventario_anterior_se_leen(self):
        """Los 49 nombres reales del CSV del repositorio (copia de las capturas del sistema anterior)."""
        nombres = [f['nombre'] for f in leer_inventario_anterior() if clase_de_fila_inventario(f['nombre']) == 'combo']
        self.assertEqual(len(nombres), 49)
        analisis = [RC.analizar_nombre(n) for n in nombres]
        self.assertTrue(all(a['ok'] for a in analisis), [a['problema'] for a in analisis if not a['ok']])
        self.assertTrue(all(a['tamano'] for a in analisis), 'Todos dicen el tamaño de la cama')
        self.assertEqual(sorted({a['marca'] for a in analisis}),
                         ['buen sueno', 'dulces suenos', 'first', 'first class', 'imperial'])
        self.assertEqual([a['cantidad_colchones'] for a in analisis if a['cantidad_colchones'] != 1], [3])

    def test_los_colores_se_entienden_en_ingles_y_en_espanol(self):
        self.assertEqual(RC.color_de('CAMA KING COLOR BLAK'), 'black')
        self.assertEqual(RC.color_de('Cama king negra, cabecero'), 'black')
        self.assertEqual(RC.color_de('COLOR LIGTH GREY'), 'light grey')
        self.assertEqual(RC.color_de('gris oscuro'), 'dark grey')
        self.assertEqual(RC.color_de('COLOR GREY'), 'grey')
        self.assertIsNone(RC.color_de('CAMA FULL CON ESTANTES'))

    def test_el_tamano_de_un_colchon_tambien_se_lee_de_4_6_3_4_y_letras(self):
        self.assertEqual(RC.tamano_de_colchon('COLCHON IMPERIAL FULL 4/6 BUEN SUEÑO'), 'full')
        self.assertEqual(RC.tamano_de_colchon('COLCHON DULCES SUEÑOS RESORTES 4/6 / DSRSO4/6'), 'full')
        self.assertEqual(RC.tamano_de_colchon('COLCHON IMPERIAL TWIN 3/4'), 'twin')
        self.assertEqual(RC.tamano_de_colchon('COLCHON DULCESUENOS SEMI RESORTE Q (A) / DSRSOQ'), 'queen')
        self.assertEqual(RC.tamano_de_colchon('Colchón First Class semiortopédico (King)'), 'king')
        self.assertIsNone(RC.tamano_de_colchon('COLCHON SIN MEDIDA'))

    def test_las_marcas_mal_escritas_dan_la_misma_forma(self):
        self.assertEqual(RC.forma_de_marca('DULCES SUEÑOS'), RC.forma_de_marca('DULCESUENOS'))
        self.assertNotEqual(RC.forma_de_marca('IMPERIAL'), RC.forma_de_marca('FIRST'))


@tagged('post_install', '-at_install')
class TestBusquedaDeLaCama(BaseCase):

    def setUp(self):
        super().setUp()
        self.camas = [
            _pieza(1, 'PRU-100-K', 'CAMA PRUEBA KING PRU-100-K', 'king', 150),
            _pieza(2, 'PRU-200-FULL', 'Cama de prueba marfil (Full)', 'full', 120),
            _pieza(3, 'PRU-200-KING', 'Cama de prueba marfil (King)', 'king', 160),
            _pieza(4, 'PRU-300', 'CAMA PRUEBA QUEEN PRU-300', 'queen', 130),
            _pieza(5, 'PRU-300 DG', 'CAMA PRUEBA QUEEN DARK GREY PRU-300 DG', 'queen', 130),
            _pieza(6, 'AB-1-bg', 'Cama de prueba twin beige', 'twin', 90, origen='catalogo'),
            _pieza(7, 'AB-1-BG', 'CAMA PRUEBA TWIN BEIGE AB-1-BG', 'twin', 90, origen='inventario'),
            _pieza(8, '', 'CAMA PRUEBA MARINA KING', 'king', 140),
            _pieza(9, 'MAR-5002', 'CAMA KING COLOR BEIGE MAR-6002', 'king', 140),
            _pieza(10, 'MAR', 'Cama king de prueba (King)', 'king', 99),
            _pieza(11, 'ZZ-9', 'Cama full negra de prueba', 'full', 80),
            _pieza(12, 'LUZ-7777', 'CAMA TWIN UP BLACK LUZ-7777', 'twin', 70),
            _pieza(13, 'LUZ-8888', 'Cama de metal twin UP negra', 'twin', 70),
            _pieza(14, 'LTS-6877', 'Cama king negra de prueba LTS-6877', 'king', 129),
            _pieza(15, 'LTS-01-6877-K-BE', 'Cama king beige de prueba LTS-01-6877-K-BE', 'king', 129),
        ]

    def cama(self, texto, tamano=None):
        return RC.resolver_cama(texto, tamano or RC.tamano_de_cama(texto), self.camas)

    def test_por_el_codigo_que_trae_el_nombre(self):
        r = self.cama('CAMA PRUEBA KING PRU-100-K')
        self.assertEqual((r['estado'], r['elegida']['id'], r['motivo']), ('claro', 1, 'por su código'))

    def test_el_codigo_de_una_variante_con_sufijo_de_tamano_se_encuentra_sin_el_sufijo(self):
        self.assertEqual(self.cama('CAMA FULL PRU-200')['elegida']['id'], 2)
        self.assertEqual(self.cama('CAMA KING PRU-200')['elegida']['id'], 3)

    def test_el_codigo_mas_largo_gana(self):
        r = self.cama('CAMA QUEEN DARK GREY PRU-300 DG')
        self.assertEqual((r['estado'], r['elegida']['id']), ('claro', 5))
        self.assertEqual(self.cama('CAMA QUEEN PRU-300')['elegida']['id'], 4)

    def test_el_codigo_puede_venir_con_otros_separadores(self):
        self.assertEqual(self.cama('CAMA QUEEN pru 300')['elegida']['id'], 4)

    def test_un_codigo_mas_largo_no_se_confunde_con_el_corto(self):
        """«MAR» (código de otra cama) no está en «MAR-6002», un código distinto: se busca por el nombre exacto."""
        r = self.cama('CAMA KING COLOR BEIGE MAR-6002')
        self.assertEqual((r['estado'], r['elegida']['id'], r['motivo']), ('claro', 9, 'por su nombre exacto'))

    def test_dos_camas_con_el_mismo_codigo_se_desempatan_por_las_mayusculas_o_por_el_origen(self):
        r = self.cama('CAMA PRUEBA TWIN BEIGE AB-1-BG')
        self.assertEqual((r['estado'], r['elegida']['id']), ('claro', 7))
        self.assertIn('hay otro', r['nota'])
        self.assertEqual([o['id'] for o in r['otras']], [6])

    def test_sin_codigo_vale_el_nombre_exacto(self):
        r = self.cama('CAMA PRUEBA MARINA KING')
        self.assertEqual((r['estado'], r['elegida']['id'], r['motivo']), ('claro', 8, 'por su nombre exacto'))

    def test_el_tamano_del_nombre_tiene_que_ser_el_de_la_cama(self):
        r = self.cama('CAMA QUEEN PRU-100-K')
        self.assertEqual(r['estado'], 'dudoso')
        self.assertIn('King', r['motivo'])
        self.assertEqual([o['id'] for o in r['opciones']], [1])

    def test_una_suposicion_es_dudosa_y_dice_las_opciones(self):
        r = self.cama('CAMA TWIN UP')
        self.assertEqual(r['estado'], 'dudoso')
        self.assertEqual(sorted(o['id'] for o in r['opciones']), [12, 13])

    def test_sin_codigo_ni_nombre_se_acota_por_numero_tamano_y_color(self):
        r = self.cama('CAMA KING COLOR BLAK LTS-01-6877 K BL')
        self.assertEqual((r['estado'], [o['id'] for o in r['opciones']]), ('dudoso', [14]))
        self.assertEqual(r['elegida'], None, 'Una suposición nunca se carga sola')

    def test_lo_que_no_existe_queda_sin_resolver(self):
        r = self.cama('CAMA KING INEXISTENTE QQQ-000')
        self.assertEqual(r['estado'], 'sin_resolver')


@tagged('post_install', '-at_install')
class TestBusquedaDelColchon(BaseCase):

    def setUp(self):
        super().setUp()
        self.colchones = [
            _pieza(1, 'IM-1', 'COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO / IM-1', 'twin', 82, 'inventario'),
            _pieza(2, 'IM-2', 'COLCHON IMPERIAL FULL 4/6 BUEN SUEÑO / IM-2', 'full', 97, 'inventario'),
            _pieza(3, 'FC-K', 'COLCHON FIRST CLASS SEMIORT KING DE 10 / FC-K', 'king', 244, 'inventario'),
            _pieza(4, 'FCAT-K', 'Colchón First Class semiortopédico gris (King)', 'king', 244, 'catalogo'),
            _pieza(5, 'DS-Q', 'COLCHON DULCESUENOS SEMI RESORTE Q (A) / DS-Q', 'queen', 185, 'inventario'),
            _pieza(6, 'DSCAT-Q', 'Colchón Dulces Sueños spring gris (Queen)', 'queen', 185, 'catalogo'),
            _pieza(7, 'FLEX-A', 'COLCHON FLEX QUEEN ORTOPEDICO', 'queen', 285, 'inventario'),
            _pieza(8, 'FLEX-B', 'COLCHON FLEX QUEEN SEMI ORTOPEDICO', 'queen', 211, 'inventario'),
        ]

    def colchon(self, marca, tamano):
        return RC.resolver_colchon(marca, tamano, self.colchones)

    def test_un_solo_producto_es_claro(self):
        r = self.colchon('imperial', 'full')
        self.assertEqual((r['estado'], r['elegida']['id'], r['otras']), ('claro', 2, []))

    def test_buen_sueno_es_parte_del_nombre_del_imperial(self):
        self.assertEqual(self.colchon('buen sueno', 'twin')['elegida']['id'], 1)

    def test_first_es_first_class(self):
        self.assertEqual(self.colchon('first', 'king')['elegida']['id'], 3)

    def test_si_hay_dos_iguales_se_usa_el_del_inventario_anterior_y_se_anota_el_otro(self):
        r = self.colchon('first class', 'king')
        self.assertEqual((r['estado'], r['elegida']['id'], [o['id'] for o in r['otras']]), ('claro', 3, [4]))
        self.assertIn('inventario del sistema anterior', r['nota'])

    def test_dulces_suenos_mal_escrito_en_el_producto_tambien_se_encuentra(self):
        r = self.colchon('dulces suenos', 'queen')
        self.assertEqual((r['estado'], r['elegida']['id'], [o['id'] for o in r['otras']]), ('claro', 5, [6]))

    def test_dos_modelos_de_la_misma_marca_y_tamano_son_dudosos(self):
        r = self.colchon('flex', 'queen')
        self.assertEqual((r['estado'], sorted(o['id'] for o in r['opciones'])), ('dudoso', [7, 8]))

    def test_sin_colchon_de_ese_tamano_o_marca_no_se_resuelve(self):
        r = self.colchon('imperial', 'king')
        self.assertEqual(r['estado'], 'sin_resolver')
        self.assertIn('solo hay Twin, Full', r['motivo'])
        self.assertEqual(self.colchon('marca inexistente', 'king')['estado'], 'sin_resolver')
        self.assertEqual(self.colchon('imperial', None)['estado'], 'sin_resolver')
        self.assertEqual(self.colchon('', 'king')['estado'], 'sin_resolver')


@tagged('post_install', '-at_install')
class TestCombosPorNombre(BaseCase):

    def setUp(self):
        super().setUp()
        self.camas = [_pieza(1, 'PRU-K', 'CAMA PRUEBA KING PRU-K', 'king', 150),
                      _pieza(2, 'PRU-T', 'CAMA PRUEBA TWIN PRU-T', 'twin', 90)]
        self.colchones = [_pieza(10, 'COL-K', 'COLCHON MARCAPRUEBA KING', 'king', 200),
                          _pieza(11, 'COL-T', 'COLCHON MARCAPRUEBA TWIN', 'twin', 80)]

    def combo(self, nombre, precio=None):
        return RC.resolver_combo(nombre, self.camas, self.colchones, precio)

    def test_claro_cuando_las_dos_piezas_son_claras(self):
        r = self.combo('COMBO CAMA PRUEBA KING PRU-K + COLCHON MARCAPRUEBA')
        self.assertEqual((r['estado'], r['cama']['elegida']['id'], r['colchon']['elegida']['id']), ('claro', 1, 10))

    def test_el_combo_es_tan_dudoso_como_su_pieza_mas_dudosa(self):
        r = self.combo('COMBO CAMA PRUEBA TWIN PRU-ZZ + COLCHON MARCAPRUEBA')
        self.assertEqual(r['estado'], 'sin_resolver')
        self.assertIn('cama:', r['motivo'])
        r = self.combo('COMBO CAMA PRUEBA KING PRU-K + COLCHON OTRA MARCA')
        self.assertEqual((r['estado'], r['cama']['estado'], r['colchon']['estado']),
                         ('sin_resolver', 'claro', 'sin_resolver'))

    def test_un_nombre_ilegible_no_se_resuelve(self):
        r = self.combo('MUEBLE QUE NO ES COMBO')
        self.assertEqual((r['estado'], r['cama']), ('sin_resolver', None))

    def test_varios_colchones_se_anotan(self):
        r = self.combo('COMBO CAMAROTE PRUEBA TWIN PRU-T + 3 COLCHONES MARCAPRUEBA')
        self.assertEqual((r['estado'], r['cantidad_colchones'], r['colchon']['elegida']['id']), ('claro', 3, 11))

    def test_avisos_de_precio(self):
        """Más barato que una sola pieza o más caro que todas juntas: se avisa, no se cambia."""
        barato = self.combo('COMBO CAMA PRUEBA KING PRU-K + COLCHON MARCAPRUEBA', precio=139.99)
        self.assertIn('menos que una sola', barato['avisos_de_precio'][0])
        caro = self.combo('COMBO CAMA PRUEBA KING PRU-K + COLCHON MARCAPRUEBA', precio=400)
        self.assertIn('más que sus piezas', caro['avisos_de_precio'][0])
        bien = self.combo('COMBO CAMA PRUEBA KING PRU-K + COLCHON MARCAPRUEBA', precio=319.99)
        self.assertEqual(bien['avisos_de_precio'], [])
        self.assertEqual(RC.aviso_de_precio(None, [100]), [])


@tagged('post_install', '-at_install')
class TestLecturaTolerante(BaseCase):
    """El archivo de Cowork puede traer BOM, comillas, otro orden de columnas, mayúsculas o espacios."""

    def test_columnas_por_nombre_en_cualquier_orden_con_comillas_y_mayusculas(self):
        texto = BOM + '\n'.join([
            '"Nombre Combo","CÓDIGO_COMBO","Nombre_Componente","Codigo Componente","Cantidad","Precio Extra",'
            '"Precio_Combo"',
            '"COMBO, CON COMA + COLCHON","CB-1"," CAMA PRUEBA ","CAMA-1"," 2 ","0"," $1,250.50 "', ''])
        (combo,), errores = RC.filas_combos(texto)
        self.assertEqual(errores, [])
        self.assertEqual((combo['nombre'], combo['codigo'], combo['precio']),
                         ('COMBO, CON COMA + COLCHON', 'CB-1', 1250.5))
        self.assertEqual([g['opciones'][0]['nombre'] for g in combo['grupos']], ['CAMA PRUEBA', 'CAMA PRUEBA'])

    def test_separador_punto_y_coma_o_tabulador(self):
        for separador in (';', '\t'):
            with self.subTest(repr(separador)):
                texto = '\n'.join([separador.join(CABECERA.split(',')),
                                   separador.join(['CB-1', 'COMBO', '100', 'CAMA-1', 'CAMA', '1', '0']), ''])
                (combo,), _errores = RC.filas_combos(texto)
                self.assertEqual(combo['precio'], 100.0)

    def test_la_marca_de_opcion_se_acepta_con_mayusculas_tildes_y_espacios(self):
        for marca in ('[opción]', '[OPCION]', ' [Opcion] ', '\xa0[opción]', '(opción)'):
            with self.subTest(marca):
                (combo,), _ = RC.filas_combos(_csv(
                    'CB-1,COMBO,100,A,CAMA,1,0', f'CB-1,,,B,COLCHON UNO {marca},1,0',
                    f'CB-1,,,C,COLCHON DOS {marca},1,15'))
                self.assertEqual(combo['grupos'][1]['a_escoger'], True)
                self.assertEqual([o['nombre'] for o in combo['grupos'][1]['opciones']], ['COLCHON UNO', 'COLCHON DOS'])

    def test_la_columna_activo_cero_archiva_el_combo(self):
        texto = BOM + '\n'.join([CABECERA + ',activo',
                                 'CB-1,COMBO UNO,100,A,CAMA,1,0,1', 'CB-2,COMBO DOS,100,A,CAMA,1,0,0',
                                 'CB-3,COMBO TRES,100,A,CAMA,1,0,False', 'CB-4,COMBO CUATRO,100,A,CAMA,1,0,', ''])
        combos, _ = RC.filas_combos(texto)
        self.assertEqual({c['clave']: c['archivado'] for c in combos},
                         {'CB-1': False, 'CB-2': True, 'CB-3': True, 'CB-4': False})

    def test_los_mensajes_dicen_que_columna_falta_y_cuales_trae(self):
        with self.assertRaisesRegex(reglas.ErrorDeArchivo,
                                    r'combos.csv le falta la columna «codigo_combo».*opcion, precio_base'):
            RC.filas_combos('Opcion,Precio Base\nA,10\n')


@tagged('post_install', '-at_install')
class TestContrasteConElNombre(BaseCase):
    """El nombre del combo dice una cosa y el archivo trae otras piezas: se marca para revisar."""

    def setUp(self):
        super().setUp()
        self.camas = [_pieza(1, '908KBE', 'CAMA KING COLOR BEIGE 908KBE', 'king'),
                      _pieza(2, '908KBK', 'CAMA KING COLOR BLACK 908KBK', 'king'),
                      _pieza(3, '908KGR', 'CAMA KING COLOR GREY 908KGR', 'king'),
                      _pieza(4, 'T-1', 'CAMA TWIN T-1', 'twin')]
        self.first = _pieza(10, 'FC-K', 'COLCHON FIRST CLASS KING', 'king')
        self.imperial = _pieza(11, 'IM-T', 'COLCHON IMPERIAL TWIN', 'twin')
        self.flex = _pieza(12, 'FX-T', 'COLCHON FLEX TWIN', 'twin')

    def contraste(self, nombre, *grupos):
        return RC.contrastar_con_el_nombre(nombre, [list(g) for g in grupos], self.camas)

    def test_si_todo_coincide_no_se_marca_nada(self):
        self.assertEqual(self.contraste('COMBO CAMA KING COLOR BLACK 908KBK + COLCHON FIRST CLASS',
                                        [self.camas[1]], [self.first]), [])

    def test_la_misma_cama_beige_en_el_combo_del_color_negro_no_coincide(self):
        problemas = self.contraste('COMBO CAMA KING COLOR BLACK 908KBK + COLCHON FIRST CLASS',
                                   [self.camas[0]], [self.first])
        self.assertEqual(len(problemas), 1)
        self.assertIn('el nombre dice la cama [908KBK]', problemas[0])
        self.assertIn('trae [908KBE]', problemas[0])

    def test_el_nombre_dice_imperial_y_el_archivo_trae_otra_marca(self):
        problemas = self.contraste('COMBO CAMA TWIN T-1 + COLCHON IMPERIAL', [self.camas[3]], [self.flex])
        self.assertEqual(len(problemas), 1)
        self.assertIn('colchón «IMPERIAL»', problemas[0])
        self.assertIn('COLCHON FLEX TWIN', problemas[0])

    def test_una_opcion_que_coincide_basta(self):
        self.assertEqual(self.contraste('COMBO CAMA TWIN T-1 + COLCHON IMPERIAL',
                                        [self.camas[3]], [self.flex, self.imperial]), [])

    def test_el_tamano_del_colchon_y_la_cantidad(self):
        problemas = self.contraste('COMBO CAMA KING COLOR BLACK 908KBK + COLCHON IMPERIAL',
                                   [self.camas[1]], [self.imperial])
        self.assertTrue(any('tamaño King' in p for p in problemas), problemas)
        problemas = self.contraste('COMBO CAMA TWIN T-1 + 3 COLCHONES IMPERIAL', [self.camas[3]], [self.imperial])
        self.assertEqual(problemas, ['el nombre dice 3 colchón(es) y el archivo trae 1'])

    def test_sin_colchon_o_sin_cama_en_el_archivo(self):
        self.assertIn('el archivo no trae la cama',
                      ' '.join(self.contraste('COMBO CAMA TWIN T-1 + COLCHON IMPERIAL', [self.imperial])))
        self.assertTrue(self.contraste('COMBO CAMA TWIN T-1 + COLCHON IMPERIAL', [self.camas[3]]))

    def test_si_el_nombre_no_alcanza_para_saber_la_cama_se_compara_color_y_tamano(self):
        camas = self.camas + [_pieza(5, 'ZZ-1', 'CAMA KING COLOR GREY ZZ-1', 'king')]
        problemas = RC.contrastar_con_el_nombre(
            'COMBO CAMA KING COLOR BLACK SIN CODIGO CONOCIDO + COLCHON FIRST CLASS',
            [[camas[4]], [self.first]], camas)
        self.assertEqual(len(problemas), 1)
        self.assertIn('color black', problemas[0])

    def test_un_nombre_que_no_se_lee_no_se_contrasta(self):
        self.assertEqual(self.contraste('MESA GRANDE', [self.camas[0]]), [])
