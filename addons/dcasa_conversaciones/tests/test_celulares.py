"""El celular es la llave del cliente: Panamá se normaliza a 8 dígitos; otro país no se confunde con Panamá."""
from odoo.tests import BaseCase, tagged

from ..models import celulares as C


@tagged('post_install', '-at_install')
class TestCelulares(BaseCase):

    def test_panama_con_y_sin_prefijo(self):
        for texto in ('50760261919', '+507 6026-1919', '6026-1919', '60261919', '507-6026-1919', ' 6026 1919 '):
            with self.subTest(texto=texto):
                self.assertEqual(C.interpretar(texto), ('pa', '60261919'))

    def test_otro_pais_no_se_corta_a_ocho_digitos(self):
        # Socios se quedaría con los últimos 8 dígitos y lo confundiría con un celular de Panamá.
        self.assertEqual(C.interpretar('13055550123'), ('intl', '13055550123'))
        self.assertEqual(C.interpretar('+57 300 123 4567'), ('intl', '573001234567'))
        self.assertNotEqual(C.interpretar('13055556026'), C.interpretar('60265556'))

    def test_lo_que_no_es_un_numero(self):
        for texto in ('', None, 'hola', '123', '1234567890123456', '+++', '0000'):
            with self.subTest(texto=texto):
                self.assertEqual(C.interpretar(texto), (None, ''))

    def test_mismo_numero(self):
        self.assertTrue(C.mismo_numero('50760261919', '6026-1919'))
        self.assertTrue(C.mismo_numero('+507 6026-1919', '60261919'))
        self.assertFalse(C.mismo_numero('50760261919', '50760261920'))
        self.assertFalse(C.mismo_numero('hola', 'hola'))
        self.assertFalse(C.mismo_numero('13055550123', '50760261919'))

    def test_para_mostrar(self):
        self.assertEqual(C.para_mostrar('pa', '60261919'), '+507 6026-1919')
        self.assertEqual(C.para_mostrar('intl', '13055550123'), '+13055550123')
        self.assertEqual(C.para_mostrar(None, ''), '')
