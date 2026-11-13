"""La etiqueta de existencias que ve el cliente (``dcasa_base/disponibilidad.py``): una sola regla para Juan, la ficha
de la tienda, el catálogo de Meta y el Escáner. Nunca el número."""
import sys

from odoo.tests import BaseCase, tagged

from .. import disponibilidad as D


@tagged('post_install', '-at_install')
class TestDisponibilidad(BaseCase):

    def test_tres_etiquetas_nunca_el_numero(self):
        casos = [(0, 'agotado'), (-3, 'agotado'), (None, 'agotado'), (0.4, 'pocas'), (1, 'pocas'), (5, 'pocas'),
                 (5.5, 'disponible'), (6, 'disponible'), (500, 'disponible')]
        for libres, etiqueta in casos:
            with self.subTest(libres=libres):
                self.assertEqual(D.etiqueta_existencias(libres), etiqueta)
        for libres in (0, 1, 7, 99, 1000):
            self.assertIn(D.etiqueta_existencias(libres), D.ETIQUETAS_EXISTENCIAS)
            self.assertNotIn(str(libres), D.etiqueta_existencias(libres))

    def test_umbral_del_producto(self):
        self.assertEqual(D.UMBRAL_POCAS, 5)
        self.assertEqual(D.etiqueta_existencias(8, umbral=10), 'pocas')
        self.assertEqual(D.etiqueta_existencias(11, umbral=10), 'disponible')
        self.assertEqual(D.etiqueta_existencias(5, umbral=None), 'pocas', 'sin umbral, el de siempre')

    def test_sin_control_de_inventario_es_disponible(self):
        self.assertEqual(D.etiqueta_existencias(0, controla_inventario=False), 'disponible')
        self.assertEqual(D.etiqueta_existencias(None, controla_inventario=False), 'disponible')

    def test_juan_meta_y_el_escaner_usan_esta_regla(self):
        """Una sola fuente: los tres módulos que antes tenían su copia la importan de aquí (los que estén cargados)."""
        for modulo in ('odoo.addons.dcasa_conversaciones.models.publico', 'odoo.addons.dcasa_barras.models.barras',
                       'odoo.addons.dcasa_meta_catalogo.models.reglas_meta'):
            copia = sys.modules.get(modulo)
            if copia is None:
                continue
            with self.subTest(modulo=modulo):
                self.assertIs(copia.etiqueta_existencias, D.etiqueta_existencias)
