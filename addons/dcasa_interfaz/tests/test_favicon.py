"""El ícono de D'CASA en el panel y en el sitio: estrictamente el logo (pedido de la dueña, 2026-10-22).

«El ícono que se crea cuando se guarda la página o panel administrativo en los celulares en pantallas de inicio debe ser
estrictamente el logo». Se revisa cada camino que lo define: el manifiesto del panel (Android), el apple-touch-icon
(iPhone) del panel, del acceso (/web/login, /master) y del sitio, el favicon, y que cada imagen sea el logo entero,
centrado y, donde el celular no admite transparencia, sobre blanco."""
import base64
import io
import os

from PIL import Image, ImageChops

from odoo.tests import HttpCase, tagged
from odoo.tools.misc import file_open

CARPETA = '/dcasa_base/static/img/icono'
APPLE = f'{CARPETA}/apple-touch-icon.png'
FAVICON = f'{CARPETA}/logo-192.png'
LOGO = 'dcasa_base/static/img/logo.png'
RAIZ = os.path.join(os.path.dirname(__file__), '..', '..')
PROPORCION_DEL_LOGO = 892 / 405


def _leer(*ruta):
    with open(os.path.join(RAIZ, *ruta), 'rb') as f:
        return f.read()


@tagged('post_install', '-at_install')
class TestIconoDeLaMarca(HttpCase):

    def _imagen(self, url):
        respuesta = self.url_open(url)
        self.assertEqual(respuesta.status_code, 200, url)
        self.assertEqual(respuesta.headers['Content-Type'], 'image/png', url)
        return Image.open(io.BytesIO(respuesta.content))

    def assertEsElLogo(self, imagen, lado, opaca, nombre):
        """El logo entero, centrado y sin deformar en un cuadrado de ``lado``; ``opaca``: sobre blanco, sin
        transparencia (iPhone, «maskable»); si no, lo que no es logo es transparente."""
        self.assertEqual(imagen.size, (lado, lado), nombre)
        rgba = imagen.convert('RGBA')
        if opaca:
            self.assertEqual(rgba.getextrema()[3], (255, 255), f'{nombre}: sin transparencia (el iPhone, en negro)')
            self.assertEqual(rgba.getpixel((0, 0)), (255, 255, 255, 255), f'{nombre}: fondo blanco')
            # Lo que no es blanco: el logo (su borde azul fino lo delimita).
            fondo = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
            caja = ImageChops.difference(rgba, fondo).convert('L').point(lambda v: 255 if v > 24 else 0).getbbox()
        else:
            self.assertEqual(rgba.getpixel((0, 0))[3], 0, f'{nombre}: fondo transparente')
            caja = rgba.getchannel('A').point(lambda v: 255 if v > 24 else 0).getbbox()
        izquierda, arriba, derecha, abajo = caja
        ancho, alto = derecha - izquierda, abajo - arriba
        self.assertAlmostEqual(ancho / alto, PROPORCION_DEL_LOGO, delta=0.08, msg=f'{nombre}: el logo sin recortar')
        self.assertLessEqual(abs(izquierda - (lado - derecha)), 2, f'{nombre}: centrado a lo ancho')
        self.assertLessEqual(abs(arriba - (lado - abajo)), 2, f'{nombre}: centrado a lo alto')
        self.assertGreater(izquierda, 0, f'{nombre}: con margen, no pegado al borde')
        return caja

    def test_el_manifiesto_del_panel_trae_el_logo(self):
        """Android: «Agregar a la pantalla de inicio» desde el panel."""
        manifiesto = self.url_open('/web/manifest.webmanifest').json()
        self.assertEqual(manifiesto['name'], "D'CASA Panamá")
        self.assertEqual(manifiesto['theme_color'], '#1340B1')
        self.assertEqual(manifiesto['background_color'], '#FFFFFF', 'la pantalla de arranque, blanca como el ícono')
        iconos = {(i['sizes'], i['purpose']): i['src'] for i in manifiesto['icons']}
        self.assertEqual(set(iconos), {('192x192', 'any'), ('512x512', 'any'),
                                       ('192x192', 'maskable'), ('512x512', 'maskable')})
        for (tamano, uso), src in iconos.items():
            with self.subTest(src=src):
                self.assertTrue(src.startswith(CARPETA), src)
                lado = int(tamano.split('x')[0])
                caja = self.assertEsElLogo(self._imagen(src), lado, uso == 'maskable', src)
                if uso == 'maskable':
                    # La zona segura: el logo entero dentro del círculo de radio 40 % (Android lo recorta en círculo).
                    medio_ancho, medio_alto = (caja[2] - caja[0]) / 2, (caja[3] - caja[1]) / 2
                    self.assertLessEqual((medio_ancho ** 2 + medio_alto ** 2) ** 0.5, 0.4 * lado, src)
        for icono in manifiesto['icons']:
            self.assertNotIn('odoo-icon', icono['src'])

    def test_el_panel_declara_el_logo(self):
        """iPhone: apple-touch-icon del panel; y el favicon y el color de la barra."""
        self.authenticate('admin', 'admin')
        html = self.url_open('/odoo').text
        self.assertIn(f'<link rel="apple-touch-icon" href="{APPLE}"/>', html)
        self.assertIn(f'href="{FAVICON}"', html)
        self.assertIn('<link rel="manifest" href="/web/manifest.webmanifest"', html)
        for de_odoo in ('odoo-icon-ios.png', '/web/static/img/favicon.ico', '#71639e'):
            self.assertNotIn(de_odoo, html)
        self.assertIn('content="#1340B1"', html)

    def test_el_icono_del_iphone_es_el_logo_sobre_blanco(self):
        self.assertEsElLogo(self._imagen(APPLE), 180, True, APPLE)

    def test_el_favicon_es_el_logo(self):
        self.assertEsElLogo(self._imagen(FAVICON), 192, False, FAVICON)
        self.assertEsElLogo(self._imagen(f'{CARPETA}/logo-512.png'), 512, False, 'logo-512')

    def test_el_acceso_y_el_sitio_traen_el_logo(self):
        """El sitio, la tienda y el acceso (/web/login y /master) llevan el mismo apple-touch-icon: Odoo ponía el
        favicon del sitio, un .ico que el iPhone no acepta."""
        rutas = ['/', '/shop', '/web/login']
        if self.env['ir.module.module'].search_count([('name', '=', 'dcasa_seguridad'), ('state', '=', 'installed')]):
            rutas.append('/master')
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.status_code, 200, ruta)
                html = respuesta.text
                self.assertIn(f'<link rel="apple-touch-icon" sizes="180x180" href="{APPLE}"/>', html)
                self.assertIn(f'href="{CARPETA}/logo-512.png"', html)
                self.assertEqual(html.count('rel="apple-touch-icon"'), 1, 'uno solo: el iPhone toma el primero')
                self.assertNotIn('/web/static/img/favicon.ico', html)

    def test_las_imagenes_salen_del_logo_de_la_marca(self):
        """Hechas con scripts/iconos_de_la_marca.py a partir de dcasa_base/static/img/logo.png: el centro del ícono
        es el logo reducido (no otro dibujo)."""
        with file_open(LOGO, 'rb') as archivo:
            logo = Image.open(io.BytesIO(archivo.read())).convert('RGBA')
        icono = self._imagen(f'{CARPETA}/logo-512.png').convert('RGBA')
        ancho = round(512 * 0.94)
        alto = round(ancho * logo.height / logo.width)
        esperado = logo.resize((ancho, alto), Image.LANCZOS)
        recorte = icono.crop(((512 - ancho) // 2, (512 - alto) // 2, (512 - ancho) // 2 + ancho,
                              (512 - alto) // 2 + alto))
        diferencia = sum(abs(a - b) for pa, pb in zip(recorte.getdata(), esperado.getdata(), strict=True)
                         for a, b in zip(pa, pb, strict=True)) / (ancho * alto * 4)
        self.assertLess(diferencia, 2, 'el ícono es el logo de la marca tal cual')

    def test_el_favicon_del_sitio_es_el_logo(self):
        website = self.env.ref('website.default_website')
        self.assertEqual(_leer('website_dcasa', 'static', 'src', 'img', 'favicon.png'),
                         _leer('dcasa_base', 'static', 'img', 'icono', 'logo-512.png'),
                         'el favicon del sitio sale del mismo logo')
        favicon = Image.open(io.BytesIO(base64.b64decode(website.favicon)))
        self.assertEqual(favicon.format, 'ICO', 'Odoo lo guarda como .ico')
        self.assertEsElLogo(favicon, favicon.size[0], False, 'favicon del sitio')
