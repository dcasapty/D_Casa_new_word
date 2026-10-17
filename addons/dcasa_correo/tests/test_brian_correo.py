"""Brian manda por correo la factura y la cotización, con los mismos frenos que la pantalla."""
from unittest.mock import patch

from odoo import Command
from odoo.tests import new_test_user, tagged

from .common import PDF, RUTA_PDF, CorreoCase


@tagged('post_install', '-at_install')
class TestBrianCorreo(CorreoCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cajera = new_test_user(
            cls.env, login='correo_cajera', name='Cajera Brian', email='cajera.brian@example.com',
            groups='base.group_user,account.group_account_invoice,sales_team.group_sale_salesman')
        cls.cama = cls.env['product.product'].create({'name': 'CAMA BRIAN', 'type': 'consu', 'list_price': 300.0})

    def brian(self, usuario, nombre, argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos)

    def test_las_herramientas_existen_con_su_permiso(self):
        todas = self.env['brian.herramientas']._todas()
        self.assertEqual(todas['enviar_factura_por_correo']['grupos'], ('account.group_account_invoice',))
        self.assertEqual(todas['enviar_factura_por_correo']['nivel'], 'construccion')
        self.assertEqual(todas['enviar_cotizacion_por_correo']['grupos'], ('sales_team.group_sale_salesman',))
        sin_factura = self.brian(self.vendedora, 'enviar_factura_por_correo', {'factura': 'x'})
        self.assertFalse(sin_factura['ok'], 'La vendedora sin Facturación no la tiene')

    def test_factura_apagado_y_encendido(self):
        factura = self.factura()
        resultado = self.brian(self.cajera, 'enviar_factura_por_correo', {'factura': factura.name})
        self.assertFalse(resultado['ok'])
        self.assertIn('Todavía no hay clave', resultado['error'])
        self.con_clave()
        resultado = self.brian(self.cajera, 'enviar_factura_por_correo', {'factura': factura.name})
        self.assertIn('apagados', resultado['error'])
        self.assertFalse(self.envios())
        self.encender()
        resultado = self.brian(self.cajera, 'enviar_factura_por_correo', {'factura': factura.name})
        self.assertTrue(resultado['ok'], resultado)
        self.assertEqual(resultado['datos']['correo_a'], 'ana@example.com')
        (envio,) = self.envios(move_id=factura.id)
        self.assertTrue(envio.huella.startswith(f'manual:{factura.id}:'))
        self.procesar()
        self.assertEqual(envio.estado, 'enviado')
        self.assertIn('TU FACTURA', self.correos_de(factura).body_html)

    def test_factura_sin_correo(self):
        self.encender()
        factura = self.factura(self.sin_correo)
        resultado = self.brian(self.cajera, 'enviar_factura_por_correo', {'factura': factura.name})
        self.assertEqual(resultado['error'],
                         'Carla Sin Correo no tiene correo. Escríbelo en su ficha o envíasela por WhatsApp.')

    def test_cotizacion_apagado_y_encendido(self):
        orden = self.env['sale.order'].with_user(self.cajera).create({
            'partner_id': self.ana.id, 'user_id': self.cajera.id,
            'order_line': [Command.create({'product_id': self.cama.id, 'product_uom_qty': 1})]})
        self.con_clave()
        resultado = self.brian(self.cajera, 'enviar_cotizacion_por_correo', {'venta': orden.name})
        self.assertIn('apagados', resultado['error'])
        self.encender()
        with patch(RUTA_PDF, return_value=PDF):
            resultado = self.brian(self.cajera, 'enviar_cotizacion_por_correo', {'venta': orden.name})
        self.assertTrue(resultado['ok'], resultado)
        self.assertEqual(orden.state, 'sent')
        self.assertEqual(self.envios(tipo='cotizacion').order_id, orden)
