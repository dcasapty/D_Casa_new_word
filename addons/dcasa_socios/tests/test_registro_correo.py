"""El correo al registrarse en Socios: sigue siendo opcional, pero si se escribe, bien escrito (2026-10-16).

Mismas reglas que la ficha del cliente (``models/bien_escrito.py``): un error de dedo trae «¿Quisiste decir…?», lo de
relleno («sincorreo@…») se pide dejarlo vacío y se guarda limpio y en minúsculas."""
import os
import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestRegistroCorreo(HttpCase):

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.Partner = self.env['res.partner']
        self.authenticate(None, None)  # sesión de visitante (la del QR en la tienda)

    def registrar(self, correo):
        pagina = self.url_open('/socios/terminos').text
        datos = {'nombre': 'Luis', 'apellido': 'Correo', 'celular': '6000-0301', 'pin': '482915', 'pin2': '482915',
                 'cumple_dia': '14', 'cumple_mes': '2', 'acepta': 'on', 'correo': correo,
                 'csrf_token': re.search(r'csrf_token: "([^"]+)"', pagina).group(1)}
        return self.url_open('/socios/registro', data=datos)

    def socio(self):
        return self.Partner.search([('dcasa_celular', '=', '60000301')])

    def test_un_error_de_dedo_sugiere_el_bueno_y_no_registra(self):
        self.assertIn('¿Quisiste decir luis@gmail.com?', self.registrar('luis@gmial.com').text)
        self.assertFalse(self.socio())

    def test_un_correo_de_relleno_pide_dejarlo_vacio(self):
        self.assertIn('Si no tienes correo, deja ese campo vacío.', self.registrar('sincorreo@gmail.com').text)
        self.assertFalse(self.socio())

    def test_un_correo_incompleto_no_pasa(self):
        self.assertIn('Ese correo no parece un correo.', self.registrar('luis@gmail').text)
        self.assertFalse(self.socio())

    def test_bien_escrito_se_guarda_limpio(self):
        self.assertIn('Ya eres socio', self.registrar(' Luis@Gmail.com ').text)
        self.assertEqual(self.socio().email, 'luis@gmail.com')

    def test_sin_correo_tambien_se_registra(self):
        self.assertIn('Ya eres socio', self.registrar('').text)
        self.assertTrue(self.socio())
        self.assertFalse(self.socio().email)
