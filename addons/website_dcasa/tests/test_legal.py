"""Páginas legales: existen, están enlazadas en el pie y dicen lo que el sistema hace de verdad."""
from odoo.tests import HttpCase, tagged

RUC = '155779346-2-2026 DV7'


@tagged('post_install', '-at_install')
class TestPaginasLegales(HttpCase):

    def test_privacidad(self):
        respuesta = self.url_open('/privacidad')
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.text
        self.assertIn('Política de privacidad', html)
        self.assertIn(RUC, html)
        self.assertIn('Ley 81 de 2019', html)
        # El uso de IA con entrenamiento (Meta «-contributor») tiene que estar dicho en claro.
        self.assertIn('id="inteligencia-artificial"', html)
        self.assertIn('Meta puede usar ese contenido para entrenar', html)
        self.assertIn('id="cookies"', html)

    def test_terminos(self):
        respuesta = self.url_open('/terminos')
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.text
        self.assertIn('Términos y condiciones', html)
        self.assertIn(RUC, html)
        self.assertIn('no incluyen el ITBMS', html)
        self.assertIn('href="/privacidad#inteligencia-artificial"', html)
        self.assertIn('href="/socios/terminos"', html)

    def test_pie_enlaza_paginas_legales_y_ruc(self):
        html = self.url_open('/').text
        self.assertIn('href="/privacidad"', html)
        self.assertIn('href="/terminos"', html)
        self.assertIn(f'RUC {RUC}', html)
