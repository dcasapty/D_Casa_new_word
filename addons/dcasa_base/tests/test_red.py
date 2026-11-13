"""La llave de una conexión (dcasa_base/red.py): la usan el freno de los choferes y «Busca con una foto»."""
from odoo.addons.dcasa_base.red import llave_ip
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install')
class TestRed(BaseCase):

    def test_llave_ip_ipv4_entera_e_ipv6_por_su_red_64(self):
        self.assertEqual(llave_ip('190.1.2.3'), '190.1.2.3')
        self.assertNotEqual(llave_ip('190.1.2.4'), llave_ip('190.1.2.3'), 'Otra IPv4 de la misma /24 es otra llave')
        self.assertEqual(llave_ip('2001:db8:1:2::1'), '2001:db8:1:2::/64')
        self.assertEqual(llave_ip('2001:db8:1:2:ffff:ffff:ffff:ffff'), '2001:db8:1:2::/64')
        self.assertNotEqual(llave_ip('2001:db8:1:3::1'), llave_ip('2001:db8:1:2::1'))
        self.assertEqual(llave_ip('::ffff:190.1.2.3'), '190.1.2.3', 'Una IPv4 mapeada es su IPv4')

    def test_lo_que_no_es_una_direccion_queda_como_antes(self):
        """Igual que la función que tenían los choferes: lo que no se entiende, tal cual (o «-» si viene vacío)."""
        self.assertEqual(llave_ip('no-es-ip'), 'no-es-ip')
        self.assertEqual(llave_ip(' 190.1.2.3 '), ' 190.1.2.3 ')
        self.assertEqual(llave_ip(''), '-')
        self.assertEqual(llave_ip(None), '-')
