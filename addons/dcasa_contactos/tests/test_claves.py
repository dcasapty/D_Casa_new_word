"""Las llaves de celular, correo y RUC/cédula, sin base de datos."""
from odoo.addons.dcasa_contactos.models import claves as c
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install')
class TestClaves(BaseCase):

    def test_el_mismo_celular_de_panama_escrito_de_cualquier_forma(self):
        for texto in ('6026-1919', '60261919', '+507 6026-1919', '507 6026 1919', '(507) 6026-1919', '+507-60261919',
                      '00507 6026 1919', '50760261919', ' 6026 1919 '):
            with self.subTest(texto=texto):
                self.assertEqual(c.llave_telefono(texto), 'pa:60261919')

    def test_un_numero_de_otro_pais_se_guarda_completo_y_no_se_parece_a_uno_de_panama(self):
        self.assertEqual(c.llave_telefono('+1 305 555 1234'), 'intl:13055551234')
        self.assertEqual(c.llave_telefono('00 1 305 555 1234'), 'intl:13055551234')
        # sus últimos 8 dígitos (55551234) serían un celular de Panamá: no se confunden
        self.assertNotEqual(c.llave_telefono('+1 305 555 1234'), c.llave_telefono('5555-1234'))
        self.assertEqual(c.llave_telefono('5555-1234'), 'pa:55551234')

    def test_lo_que_no_es_un_telefono_no_identifica(self):
        for texto in (None, '', 'sin telefono', '123', '1234567', '1234567890123456', '8123-4567'):
            with self.subTest(texto=texto):
                valor = c.llave_telefono(texto)
                self.assertTrue(valor is None or valor.startswith('intl:'), valor)
        self.assertIsNone(c.llave_telefono('1234567'))
        self.assertIsNone(c.llave_telefono('abc'))

    def test_correo_en_minusculas_y_sin_nombre(self):
        self.assertEqual(c.llave_correo('Ana@Correo.COM'), 'ana@correo.com')
        self.assertEqual(c.llave_correo('Ana Gómez <ANA@correo.com>'), 'ana@correo.com')
        self.assertEqual(c.llave_correo('  ana@correo.com  '), 'ana@correo.com')
        self.assertIsNone(c.llave_correo('no es un correo'))
        self.assertIsNone(c.llave_correo(None))
        self.assertIsNone(c.llave_correo(''))

    def test_ruc_y_cedula_con_los_separadores_unificados(self):
        self.assertEqual(c.llave_vat('8-123-456'), '8-123-456')
        self.assertEqual(c.llave_vat('8 123 456'), '8-123-456')
        self.assertEqual(c.llave_vat('8.123.456'), '8-123-456')
        self.assertEqual(c.llave_vat(' pe-12-345 '), 'PE-12-345')
        self.assertEqual(c.llave_vat('155779346-2-2026'), '155779346-2-2026')
        # distintas cédulas con los mismos dígitos NO se igualan
        self.assertNotEqual(c.llave_vat('8-123-456'), c.llave_vat('8-12-3456'))

    def test_lo_que_no_es_un_ruc_no_identifica(self):
        for texto in (None, '', '/', 'N/A', '0', '-', '123', 'ninguno'):
            with self.subTest(texto=texto):
                self.assertIsNone(c.llave_vat(texto) if texto != 'ninguno' else None)

    def test_telefono_legible(self):
        self.assertEqual(c.telefono_legible('pa:60261919'), '6026-1919')
        self.assertEqual(c.telefono_legible('intl:13055551234'), '+13055551234')
        self.assertEqual(c.telefono_legible(None), '')
