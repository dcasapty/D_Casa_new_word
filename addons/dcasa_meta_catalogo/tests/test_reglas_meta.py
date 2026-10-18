"""Las reglas puras del catálogo (sin base de datos)."""
import re

from lxml import etree

from odoo.addons.dcasa_meta_catalogo.models import reglas_meta as R
from odoo.tests import BaseCase, tagged
from odoo.tools import file_open
from odoo.tools.safe_eval import safe_eval

ETIQUETA = re.compile(r'^[a-z0-9_]*$')


@tagged('post_install', '-at_install')
class TestReglasMeta(BaseCase):

    def test_etiquetas_sin_tildes_ni_enes(self):
        self.assertEqual(R.etiqueta_ascii('Habitación'), 'habitacion')
        self.assertEqual(R.etiqueta_ascii('Niños'), 'ninos')
        self.assertEqual(R.etiqueta_ascii('Habitación de Niños'), 'habitacion_de_ninos')
        self.assertEqual(R.etiqueta_ascii('  Sala & Comedor!! '), 'sala_comedor')
        self.assertEqual(R.etiqueta_ascii('Black Friday 2026'), 'black_friday_2026')
        self.assertEqual(R.etiqueta_ascii(''), '')
        self.assertEqual(R.etiqueta_ascii(None), '')
        largo = R.etiqueta_ascii('á' * 50 + ' ' + 'b' * 200)
        self.assertLessEqual(len(largo), 100)
        for texto in ('Ñandú', 'Recámaras', 'Sofás y sillones', '¿Qué?', 'ÀÉÎÕÜ ç'):
            with self.subTest(texto):
                self.assertRegex(R.etiqueta_ascii(texto), ETIQUETA)

    def test_franjas_coinciden_con_los_filtros_de_productos(self):
        """Las franjas de precio son los mismos cortes que los filtros «Hasta $100»… de dcasa_catalogo."""
        with file_open('dcasa_catalogo/views/backend_views.xml', 'rb') as archivo:
            raiz = etree.fromstring(archivo.read())
        filtros = {}
        for nombre, etiqueta in (('dcasa_precio_1', 'hasta_100'), ('dcasa_precio_2', '100_a_300'),
                                 ('dcasa_precio_3', '300_a_600'), ('dcasa_precio_4', 'mas_de_600')):
            [nodo] = raiz.xpath(f'//filter[@name="{nombre}"]')
            filtros[etiqueta] = safe_eval(nodo.get('domain'))

        def cumple(dominio, monto):
            operadores = {'<=': lambda a, b: a <= b, '<': lambda a, b: a < b,
                          '>': lambda a, b: a > b, '>=': lambda a, b: a >= b}
            return all(operadores[op](monto, valor) for campo, op, valor in dominio if campo == 'list_price')

        for monto in (0, 0.01, 50, 99.99, 100, 100.01, 150, 299.99, 300, 300.01, 450, 600, 600.01, 999, 5000):
            with self.subTest(monto=monto):
                esperadas = [etiqueta for etiqueta, dominio in filtros.items() if cumple(dominio, monto)]
                self.assertEqual(esperadas, [R.banda_precio(monto)])

    def test_pocas_son_cinco_o_menos(self):
        self.assertEqual(R.UMBRAL_POCAS, 5)
        self.assertEqual(R.nivel_existencias(6), 'disponible')
        self.assertEqual(R.nivel_existencias(5), 'pocas')
        self.assertEqual(R.nivel_existencias(1), 'pocas')
        self.assertEqual(R.nivel_existencias(0), 'agotado')
        self.assertEqual(R.nivel_existencias(-2), 'agotado')
        self.assertEqual(R.nivel_existencias(None), 'disponible', 'sin control de inventario: como el Escáner')

    def test_disponibilidad_con_espacio(self):
        self.assertEqual(R.disponibilidad('web', 0), 'in stock', 'como la web: todo lo publicado está disponible')
        self.assertEqual(R.disponibilidad('web', None), 'in stock')
        self.assertEqual(R.disponibilidad('existencias', 3), 'in stock')
        self.assertEqual(R.disponibilidad('existencias', 0), 'out of stock')
        self.assertEqual(R.disponibilidad('existencias', None), 'in stock')
        with self.assertRaises(ValueError):
            R.disponibilidad('otro', 1)

    def test_formato_de_precio_siempre_con_dos_decimales(self):
        self.assertEqual(R.formato_precio(40, 'USD'), '40.00 USD')
        self.assertEqual(R.formato_precio(40.0, 'USD'), '40.00 USD')
        self.assertEqual(R.formato_precio(399, 'USD'), '399.00 USD')
        self.assertEqual(R.formato_precio(39.99, 'USD'), '39.99 USD')
        self.assertEqual(R.formato_precio(1234.5, 'USD'), '1234.50 USD')
        self.assertEqual(R.formato_precio(0.125, 'USD'), '0.13 USD', 'redondeo comercial')
        self.assertEqual(R.formato_precio(10, 'JPY', 0), '10 JPY', 'los decimales de la moneda')

    def test_texto_plano_quita_html_enlaces_y_mayusculas(self):
        self.assertEqual(R.texto_plano('<p>Cama <b>king</b></p><p>Con cajones</p>'), 'Cama king Con cajones')
        self.assertEqual(R.texto_plano('<div>Hola<script>alert(1)</script></div>'), 'Hola')
        self.assertEqual(R.texto_plano('Mira https://otra.tienda/x?y=1 y www.ejemplo.com hoy'), 'Mira y hoy')
        self.assertEqual(R.texto_plano('<p>Ver <a href="https://x.com">aquí</a></p>'), 'Ver aquí')
        self.assertEqual(R.texto_plano('CAMA KING. CON CAJONES'), 'Cama king. Con cajones')
        self.assertEqual(R.texto_plano('Cama KING con cajones'), 'Cama KING con cajones', 'solo si todo es mayúscula')
        self.assertEqual(R.texto_plano('  uno \n\n  dos\t tres '), 'uno dos tres')
        self.assertEqual(R.texto_plano(''), '')
        self.assertEqual(R.texto_plano(False), '')
        largo = R.texto_plano('palabra ' * 2000)
        self.assertLessEqual(len(largo), 5000)
        self.assertTrue(largo.endswith('palabra'), 'cortado en una palabra')

    def test_titulo_corto_en_una_palabra(self):
        titulo = R.titulo('Cama ' + 'muy ' * 60 + 'larga')
        self.assertLessEqual(len(titulo), 150)
        self.assertFalse(titulo.endswith(' '))
        self.assertTrue(titulo.endswith('muy'))
        self.assertEqual(R.titulo('  Mesa \n de  noche '), 'Mesa de noche')
