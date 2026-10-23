"""Qué es un celular y un correo «bien escrito» (funciones puras de ``dcasa_socios.models.bien_escrito``).

Pedido de la dueña (2026-10-16): «el vendedor siempre, obligatoriamente, debe capturar el número de teléfono y correo
electrónico, pero bien escrito». Sin base de datos: las tablas del diseño, una por una. El teléfono fijo (2026-10-22):
7 números en Panamá, en su propio campo."""
from odoo.addons.dcasa_contactos.models import claves
from odoo.addons.dcasa_socios.models import bien_escrito as B
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install')
class TestBienEscrito(BaseCase):

    def test_correos(self):
        casos = {
            'ana@gmail': ('formato', 'ana@gmail.com'),
            'ana@gmail,com': ('formato', 'ana@gmail.com'),
            'ana@@gmail.com': ('formato', 'ana@gmail.com'),
            'ana@gmail.com, pedro@gmail.com': ('varios', None),
            'ana@gmail.com pedro@hotmail.com': ('varios', None),
            'ana@hotmail..com': ('formato', 'ana@hotmail.com'),
            'ana@gmial.com': ('dedo', 'ana@gmail.com'),
            'ana@gmail.con': ('dedo', 'ana@gmail.com'),
            'ana@gmail.co': ('dedo', 'ana@gmail.com'),
            'ana@hotmial.com': ('dedo', 'ana@hotmail.com'),
            'ana@hotmail.con': ('dedo', 'ana@hotmail.com'),
            'ana.perez@yahoo.cmo': ('dedo', 'ana.perez@yahoo.com'),
            'ana@algo.co': (None, None),
            'ana@hotmail.es': (None, None),
            'ana@yahoo.es': (None, None),
            'ana@empresa.com.pa': (None, None),
            'ana@example.com': (None, None),
            'sincorreo@gmail.com': ('relleno', None),
            'no@no.com': ('relleno', None),
            'xxx@hotmail.com': ('relleno', None),
            'no.tiene@gmail.com': ('relleno', None),
            'sin_correo@hotmail.com': ('relleno', None),
            'prueba2@example.com': (None, None),
            'ana2015@gmail.com': (None, None),
            '': ('vacio', None),
            '   ': ('vacio', None),
        }
        for texto, esperado in casos.items():
            with self.subTest(texto):
                self.assertEqual(B.problema_del_correo(texto), esperado)

    def test_el_correo_se_guarda_limpio(self):
        self.assertEqual(B.correo_limpio(' Ana@Gmail.com '), 'ana@gmail.com')
        self.assertEqual(B.correo_limpio('Ana Gómez <Ana@Gmail.com>'), 'ana@gmail.com')
        self.assertIsNone(B.correo_limpio('ana@gmial.com'))
        self.assertIsNone(B.correo_limpio(''))

    def test_celulares(self):
        bien = {
            '6026-1919': '+507 6026-1919',
            '60261919': '+507 6026-1919',
            '6026 1919': '+507 6026-1919',
            '50760261919': '+507 6026-1919',
            '0050760261919': '+507 6026-1919',
            '+507 6026-1919': '+507 6026-1919',
            '+50760261919': '+507 6026-1919',
            '+1 305 555 1234': '+13055551234',
            '+86 138 0013 8000': '+8613800138000',
        }
        for texto, guardado in bien.items():
            with self.subTest(texto):
                self.assertIsNone(B.problema_del_telefono(texto))
                self.assertEqual(B.telefono_para_guardar(texto), guardado)
        mal = {
            '6026-19199': 'largo',
            '507 6026191': 'corto',
            '6026-191': 'corto',
            '2345678': 'fijo',
            '602-6191': 'corto',
            '60261919 / 2345678': 'varios',
            '13055551234': 'sin_mas',
            '+507 345-6789': 'fijo',
            '1234-5678': 'invalido',
            'abc': 'letras',
            '': 'vacio',
        }
        for texto, codigo in mal.items():
            with self.subTest(texto):
                self.assertEqual(B.problema_del_telefono(texto), codigo)
                self.assertIsNone(B.telefono_para_guardar(texto))

    def test_guardarlo_limpio_no_cambia_la_llave(self):
        """La llave de contactos (``claves.llave_telefono``) no cambia: «+507 6026-1919» sigue siendo pa:60261919."""
        for texto in ('6026-1919', '6026 1919', '+507 6026-1919', '0050760261919'):
            with self.subTest(texto):
                self.assertEqual(claves.llave_telefono(B.telefono_para_guardar(texto)), 'pa:60261919')
                self.assertEqual(claves.llave_telefono(B.telefono_para_guardar(texto)), claves.llave_telefono(texto))
        self.assertEqual(claves.llave_telefono(B.telefono_para_guardar('+1 305 555 1234')),
                         claves.llave_telefono('+1 305 555 1234'))

    def test_telefono_fijo(self):
        """«Hubo un cliente que no tenía WhatsApp sino teléfono fijo de 7 números» (2026-10-22): el fijo se guarda
        limpio en su campo; un celular escrito ahí (o un fijo escrito en «Celular») dice a dónde va."""
        bien = {
            '234-5678': '+507 234-5678',
            '2345678': '+507 234-5678',
            '234 5678': '+507 234-5678',
            '+507 234-5678': '+507 234-5678',
            '507 2345678': '+507 234-5678',
            '00507 234 5678': '+507 234-5678',
            '(507) 734-5678': '+507 734-5678',
            '+1 305 555 1234': '+13055551234',
        }
        for texto, guardado in bien.items():
            with self.subTest(texto):
                self.assertIsNone(B.problema_del_fijo(texto))
                self.assertEqual(B.fijo_para_guardar(texto), guardado)
                self.assertEqual(B.fijo_para_guardar(guardado), guardado, 'guardarlo dos veces no lo cambia')
        mal = {
            '6123-4567': 'celular',
            '+507 6123-4567': 'celular',
            '234-567': 'corto',
            '123-4567': 'invalido',
            '623-4567': 'invalido',
            '0234567': 'invalido',
            '1234-5678': 'largo',
            '234-5678 / 345-6789': 'varios',
            '234-5678 y 345-6789': 'varios',
            'casa': 'letras',
            '2345678901': 'sin_mas',
            '': 'vacio',
        }
        for texto, codigo in mal.items():
            with self.subTest(texto):
                self.assertEqual(B.problema_del_fijo(texto), codigo)
                self.assertIsNone(B.fijo_para_guardar(texto))
        # En «Celular», siete números de un fijo no son un celular corto: es un fijo (con su propio mensaje).
        self.assertEqual(B.problema_del_telefono('234-5678'), 'fijo')
        self.assertEqual(B.problema_del_telefono('602-6191'), 'corto', 'un celular al que le falta un número')
