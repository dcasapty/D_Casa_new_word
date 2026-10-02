"""Ronda 6 de diseño: lo que la dueña pidió fijar.

* La píldora de /socios (logo, Catálogo · Socios D'CASA · Visítanos, carrito, búsqueda, cuenta y
  «Escríbenos») está igual en todas las páginas, también en la tienda, la ficha, el carrito, las
  legales, la cuenta y Black Weekend.
* El pie no lleva fotos ni velos (la «foto azulosa» venía de la tienda estática del borde).
* La foto de la portada se ve con sus colores reales: sin opacidad ni filtro.
"""
import re

from odoo.addons.website_dcasa.models.black_weekend import PARAM_ACTIVO, PARAM_FIN, PARAM_INICIO
from odoo.tests import HttpCase, tagged

# Páginas que abren con foto o fondo oscuro: la cabecera va encima (o_header_overlay).
CON_CABECERA_ENCIMA = ('/', '/socios', '/visitanos', '/contactus', '/privacidad', '/terminos',
                       '/web/login', '/black-weekend')


def _cabecera(html):
    return re.search(r'<header id="top".*?</header>', html, re.S).group(0)


def _clases_wrapwrap(html):
    return re.search(r'<div id="wrapwrap" class="([^"]*)"', html).group(1).split()


@tagged('post_install', '-at_install')
class TestDisenoUniforme(HttpCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(PARAM_ACTIVO, '1')
        param.set_param(PARAM_INICIO, '')
        param.set_param(PARAM_FIN, '')
        recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        self.producto = self.env['product.template'].create({
            'name': 'Cama de prueba de diseño', 'list_price': 99.99, 'is_published': True,
            'public_categ_ids': [(6, 0, recamaras.ids)], 'dcasa_black_weekend': True,
        })
        self.paginas = [
            '/', '/shop', f"/shop/category/{self.env['ir.http']._slug(recamaras)}",
            self.producto.website_url, '/shop/cart', '/black-weekend', '/socios', '/visitanos',
            '/contactus', '/privacidad', '/terminos', '/web/login',
        ]

    def test_la_pildora_es_la_misma_en_todas_las_paginas(self):
        for ruta in self.paginas:
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.text
                cabecera = _cabecera(html)
                self.assertIn('o_dcasa_anuncios', cabecera, 'Barra de avisos azul arriba')
                self.assertIn('o_main_nav', cabecera)
                # Logo de D'CASA en WebP liviano (el PNG de 56 KB competía con la foto principal).
                self.assertIn('/website_dcasa/static/src/img/logo-200.webp', cabecera)
                self.assertNotIn('/web/image/website/1/logo', cabecera)
                menu = re.search(r'id="top_menu".*?</ul>', cabecera, re.S).group(0)
                for enlace, texto in (('/shop', 'Catálogo'), ('/socios', 'Socios D&#39;CASA'),
                                      ('/visitanos', 'Visítanos')):
                    self.assertRegex(menu, rf'href="{re.escape(enlace)}"[^>]*>\s*<span>{texto}</span>')
                self.assertIn('o_wsale_my_cart', cabecera, 'Carrito')
                self.assertIn('o_search_modal', cabecera, 'Búsqueda')
                self.assertIn('href="/web/login"', cabecera, 'Cuenta')
                self.assertRegex(cabecera, r'class="[^"]*btn_cta[^"]*"[^>]*>.*?Escríbenos</a>',
                                 'Botón azul «Escríbenos» (CTA único)')
                self.assertEqual(cabecera.count('id="top_menu"'), 1)

    def test_paginas_con_foto_llevan_la_cabecera_encima(self):
        for ruta in CON_CABECERA_ENCIMA:
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                self.assertIn('o_header_overlay', _clases_wrapwrap(html))
                self.assertRegex(html, r'class="[^"]*(o_dcasa_hero|o_dcasa_fondo_oscuro)',
                                 'Con la cabecera encima, la página abre con foto o fondo oscuro')
        for ruta in ('/shop', self.producto.website_url, '/shop/cart'):
            with self.subTest(ruta=ruta):
                self.assertNotIn('o_header_overlay', _clases_wrapwrap(self.url_open(ruta).text))

    def test_pie_sin_fotos_ni_velos(self):
        for ruta in ('/', '/shop', '/socios', '/privacidad'):
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                pie = re.search(r'<footer.*?</footer>', html, re.S).group(0)
                self.assertIn('o_dcasa_footer', pie)
                self.assertIn('info@dcasapty.com', pie)
                for prohibido in ('<img', '<picture', 'background-image', 'opacity', 'filter:',
                                  'o_dcasa_hero', 'o_we_bg_filter', 'o_bg_img'):
                    self.assertNotIn(prohibido, pie)

    def test_fotos_principales_a_tiempo(self):
        """Rendimiento (ronda 6): la foto LCP de cada página se pide pronto y al ancho justo."""
        portada = self.url_open('/').text
        self.assertRegex(portada, r'<link[^>]*rel="preload"[^>]*as="image"[^>]*hero')
        self.assertNotIn('fontawesome-webfont.woff2?v=4.7.0" as="font"', portada)
        self.assertIn('cat-salas-400.webp 400w', portada, '«Compra por espacio» a 400 px en el celular')
        self.assertNotRegex(self.url_open('/shop').text, r'rel="preload"[^>]*as="image"')
        ficha = self.url_open(self.producto.website_url).text
        foto = re.search(r'<img[^>]*product_detail_img[^>]*>', ficha).group(0)
        self.assertIn('loading="eager"', foto)
        self.assertIn('fetchpriority="high"', foto)
        self.assertIn('srcset=', foto)

    def test_logo_propio_se_respeta(self):
        """Si la dueña sube otro logo desde el editor, la píldora muestra el suyo."""
        self.website.logo = self.env['website']._default_logo()
        cabecera = _cabecera(self.url_open('/shop').text)
        self.assertNotIn('logo-200.webp', cabecera)
        self.assertIn('/web/image/website/', cabecera)

    def test_estilos_en_el_navegador(self):
        """Medido en Chrome: foto del hero sin velo, píldora oscura en la tienda, pie sin filtros."""
        codigo_portada = """
            const fallar = (m) => console.error('Diseño: ' + m);
            const foto = document.querySelector('.o_dcasa_hero:not(.o_dcasa_hero_compacto) .o_dcasa_hero_media img');
            const cs = getComputedStyle(foto);
            if (cs.opacity !== '1') fallar('la foto del hero tiene opacidad ' + cs.opacity);
            if (cs.filter !== 'none' || cs.mixBlendMode !== 'normal') fallar('la foto del hero tiene filtro');
            const media = getComputedStyle(foto.parentElement);
            if (media.backgroundImage !== 'none') fallar('velo sobre la foto del hero');
            for (const capa of ['::before', '::after']) {
                const v = getComputedStyle(foto.parentElement, capa);
                if (v.content !== 'none' && v.content !== 'normal') fallar('capa encima de la foto ' + capa);
            }
            const placa = getComputedStyle(document.querySelector('.o_dcasa_hero_texto'));
            if (placa.backgroundColor !== 'rgb(14, 42, 107)') {
                fallar('el texto del hero no va en la placa navy: ' + placa.backgroundColor);
            }
            const pie = document.querySelector('footer#bottom');
            for (const el of [pie, ...pie.querySelectorAll('*')]) {
                const e = getComputedStyle(el);
                if (e.backgroundImage !== 'none' || e.filter !== 'none' || parseFloat(e.opacity) < 1) {
                    fallar('el pie tiene imagen, filtro u opacidad en ' + el.tagName + '.' + el.className);
                    break;
                }
            }
            console.log('test successful');
        """
        self.browser_js('/', codigo_portada, timeout=120)
        codigo_tienda = """
            const pildora = document.querySelector('header#top .o_main_nav');
            const fondo = getComputedStyle(pildora, '::before').backgroundColor;
            if (!/^rgba\\(27, 34, 51, 0\\.9/.test(fondo)) {
                console.error('Diseño: la píldora de la tienda no es la de /socios: ' + fondo);
            }
            const enlace = getComputedStyle(document.querySelector('#top_menu .nav-link')).color;
            if (enlace !== 'rgb(255, 255, 255)') console.error('Diseño: menú sin texto blanco: ' + enlace);
            console.log('test successful');
        """
        self.browser_js('/shop', codigo_tienda, timeout=120)
