from odoo.addons.dcasa_invoice.models import formato
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFormato(TransactionCase):
    """Cómo se escriben montos, cédulas, teléfonos y URLs en un papel de D'CASA."""

    def test_numeros_en_letras(self):
        self.assertEqual(formato.numero_en_letras(0), 'cero')
        self.assertEqual(formato.numero_en_letras(21), 'veintiuno')
        self.assertEqual(formato.numero_en_letras(100), 'cien')
        self.assertEqual(formato.numero_en_letras(353), 'trescientos cincuenta y tres')
        self.assertEqual(formato.numero_en_letras(1_000_000), 'un millón')

    def test_telefono_de_panama(self):
        self.assertEqual(formato.telefono_fmt('61234567'), '6123-4567')

    def test_url_local_no_se_imprime(self):
        self.assertTrue(formato.url_es_local('http://localhost:8069'))
        self.assertTrue(formato.url_es_local('http://192.168.1.10'))
        self.assertFalse(formato.url_es_local('https://dcasapty.com'))
