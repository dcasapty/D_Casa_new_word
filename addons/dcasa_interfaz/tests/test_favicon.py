"""El panel usa el favicon de D'CASA (el mismo de la página web) y no el círculo de Odoo."""
import os

from odoo.tests import HttpCase, tagged

FAVICON = '/dcasa_interfaz/static/src/img/favicon.png'
RAIZ = os.path.join(os.path.dirname(__file__), '..', '..')


def _leer(*ruta):
    with open(os.path.join(RAIZ, *ruta), 'rb') as f:
        return f.read()


@tagged('post_install', '-at_install')
class TestFavicon(HttpCase):

    def test_el_favicon_es_el_mismo_de_la_pagina_web(self):
        self.assertEqual(_leer('dcasa_interfaz', 'static', 'src', 'img', 'favicon.png'),
                         _leer('website_dcasa', 'static', 'src', 'img', 'favicon.png'),
                         "debe ser exactamente el favicon de website_dcasa")

    def test_el_panel_declara_el_favicon_de_dcasa(self):
        self.authenticate('admin', 'admin')
        html = self.url_open('/odoo').text
        self.assertIn(f'href="{FAVICON}"', html)
        self.assertNotIn('/web/static/img/favicon.ico', html)
        # al agregarlo a la pantalla de inicio del celular y el color de la barra: de la marca
        self.assertNotIn('odoo-icon-ios.png', html)
        self.assertIn('content="#1340B1"', html)
        self.assertNotIn('#71639e', html)

    def test_el_acceso_tambien_lleva_el_favicon_de_dcasa(self):
        html = self.url_open('/web/login').text
        self.assertNotIn('/web/static/img/favicon.ico', html)

    def test_el_archivo_se_sirve_como_imagen(self):
        respuesta = self.url_open(FAVICON)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Content-Type'], 'image/png')
        self.assertEqual(respuesta.content, _leer('website_dcasa', 'static', 'src', 'img', 'favicon.png'))

    def test_la_app_instalable_es_de_dcasa(self):
        manifiesto = self.url_open('/web/manifest.webmanifest').json()
        self.assertEqual(manifiesto['name'], "D'CASA Panamá")
        self.assertEqual(manifiesto['theme_color'], '#1340B1')
        self.assertEqual(manifiesto['background_color'], '#1340B1')
        self.assertEqual([i['sizes'] for i in manifiesto['icons']], ['192x192', '512x512'])
        for icono in manifiesto['icons']:
            self.assertTrue(icono['src'].startswith('/dcasa_interfaz/'), icono['src'])
            self.assertEqual(self.url_open(icono['src']).status_code, 200)
