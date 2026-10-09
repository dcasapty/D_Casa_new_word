"""La vista pública del catálogo: búsqueda por palabras, etiquetas de existencias y precio «+ ITBMS»."""
from odoo.tests import BaseCase, tagged

from ..models import publico as P


@tagged('post_install', '-at_install')
class TestBusqueda(BaseCase):

    def test_normalizar_quita_acentos_y_mayusculas(self):
        self.assertEqual(P.normalizar('Colchón QUEEN'), 'colchon queen')
        self.assertEqual(P.normalizar(None), '')

    def test_raiz_singulariza(self):
        self.assertEqual(P.raiz('colchones'), 'colchon')
        self.assertEqual(P.raiz('camas'), 'cama')
        self.assertEqual(P.raiz('sofas'), 'sofa')
        self.assertEqual(P.raiz('mesa'), 'mesa')
        self.assertEqual(P.raiz('es'), 'es')

    def test_palabras_ignoran_signos(self):
        self.assertEqual(P.palabras('¿Tienen camas QUEEN?'), ['tienen', 'cama', 'queen'])
        self.assertEqual(P.palabras('SOF-001'), ['sof', '001'])
        self.assertEqual(P.palabras('???'), [])

    def test_puntuar_exige_todas_las_palabras(self):
        self.assertGreater(P.puntuar('cama queen', 'CAMA TAPIZADA GREY', '888Q', 'Camas Queen'), 0)
        self.assertEqual(P.puntuar('cama king', 'CAMA TAPIZADA GREY', '888Q', 'Camas Queen'), 0)
        self.assertEqual(P.puntuar('', 'CAMA', '', ''), 0)

    def test_puntuar_no_distingue_acentos_ni_plural(self):
        self.assertGreater(P.puntuar('colchón queen', 'COLCHON FIRST CLASS', 'LTSC-07', 'Colchones Queen'), 0)
        self.assertGreater(P.puntuar('colchones', 'COLCHON FIRST CLASS', '', ''), 0)

    def test_el_codigo_exacto_gana(self):
        exacto = P.puntuar('SOF-001', 'Sofá gris', 'SOF-001 SOF-001-G', '')
        por_nombre = P.puntuar('sofa', 'Sofá gris', 'SOF-001', '')
        self.assertEqual(exacto, 1000)
        self.assertGreater(exacto, por_nombre)

    def test_el_nombre_pesa_mas_que_las_categorias(self):
        self.assertGreater(P.puntuar('sofa', 'SOFA GRIS', '', ''), P.puntuar('sofa', 'Mesa', '', 'Sofas'))

    def test_limite_seguro(self):
        self.assertEqual(P.limite_seguro(None), P.LIMITE_POR_DEFECTO)
        self.assertEqual(P.limite_seguro('abc'), P.LIMITE_POR_DEFECTO)
        self.assertEqual(P.limite_seguro(0), 1)
        self.assertEqual(P.limite_seguro(100), P.LIMITE_MAXIMO)
        self.assertEqual(P.limite_seguro('3'), 3)


@tagged('post_install', '-at_install')
class TestEtiquetas(BaseCase):

    def test_existencias_son_una_etiqueta_nunca_el_numero(self):
        self.assertEqual(P.etiqueta_existencias(0), 'agotado')
        self.assertEqual(P.etiqueta_existencias(-3), 'agotado')
        self.assertEqual(P.etiqueta_existencias(None), 'agotado')
        self.assertEqual(P.etiqueta_existencias(3), 'pocas')
        self.assertEqual(P.etiqueta_existencias(5), 'pocas')       # el umbral cuenta como «pocas»
        self.assertEqual(P.etiqueta_existencias(6), 'disponible')
        self.assertEqual(P.etiqueta_existencias(500), 'disponible')
        for libres in (0, 1, 7, 99, 1000):
            self.assertIn(P.etiqueta_existencias(libres), P.ETIQUETAS_EXISTENCIAS)

    def test_el_umbral_es_el_de_la_tienda(self):
        self.assertEqual(P.etiqueta_existencias(8, umbral=10), 'pocas')
        self.assertEqual(P.etiqueta_existencias(11, umbral=10), 'disponible')

    def test_sin_inventario_se_muestra_como_la_tienda(self):
        self.assertEqual(P.etiqueta_existencias(0, controla_inventario=False), 'disponible')

    def test_precio_siempre_con_itbms(self):
        self.assertEqual(P.precio_texto(349.99), '$349.99 + ITBMS')
        self.assertEqual(P.precio_texto(1299.5), '$1,299.50 + ITBMS')
        self.assertEqual(P.precio_texto(10, mas_itbms=False), '$10.00')

    def test_recortar(self):
        self.assertEqual(P.recortar('  hola   mundo  '), 'hola mundo')
        self.assertEqual(len(P.recortar('x' * 1000, 50)), 50)
        self.assertTrue(P.recortar('x' * 1000, 50).endswith('…'))
