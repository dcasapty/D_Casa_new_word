"""Ronda 6 de diseño: lo que la dueña pidió fijar.

* La píldora de /socios (logo, Catálogo · Socios D'CASA · Visítanos, carrito, búsqueda, cuenta y
  «Escríbenos») está igual en todas las páginas, también en la tienda, la ficha, el carrito, las
  legales, la cuenta y Black Weekend, y es el vidrio líquido original (desenfoque, saturación,
  filos de luz y refracción): claro sobre fondo claro, ahumado sobre una foto.
* El pie no lleva fotos ni velos (la «foto azulosa» venía de la tienda estática del borde).
* Portada (corrección de la dueña): el texto va directamente sobre la foto, sin placa ni tarjeta,
  con la foto un poco oscurecida (velo negro plano del 35-45 %), también en el celular.
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
        """Medido en Chrome: portada sin placa y con velo moderado; píldora líquida en todas partes."""
        codigo_portada = """
            (async () => {
            const fallar = (m) => console.error('Diseño: ' + m);
            const solapa = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
            const lin = (c) => { c /= 255; return c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; };
            // Contraste del blanco contra la foto velada que queda detrás de una caja de texto
            // (mediana de los píxeles; «cover» centrado, como object-fit).
            const contraste = (img, opacidad, caja) => {
                const marco = img.getBoundingClientRect();
                const escala = Math.max(marco.width / img.naturalWidth, marco.height / img.naturalHeight);
                const dx = (img.naturalWidth * escala - marco.width) / 2;
                const dy = (img.naturalHeight * escala - marco.height) / 2;
                const lienzo = document.createElement('canvas');
                lienzo.width = Math.max(1, Math.round(caja.width / 4));
                lienzo.height = Math.max(1, Math.round(caja.height / 4));
                const ctx = lienzo.getContext('2d');
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, lienzo.width, lienzo.height);
                ctx.globalAlpha = opacidad;
                ctx.drawImage(img, (caja.left - marco.left + dx) / escala, (caja.top - marco.top + dy) / escala,
                              caja.width / escala, caja.height / escala, 0, 0, lienzo.width, lienzo.height);
                const d = ctx.getImageData(0, 0, lienzo.width, lienzo.height).data;
                const lums = [];
                for (let i = 0; i < d.length; i += 4) {
                    lums.push(.2126 * lin(d[i]) + .7152 * lin(d[i + 1]) + .0722 * lin(d[i + 2]));
                }
                lums.sort((a, b) => a - b);
                return 1.05 / (lums[Math.floor(lums.length / 2)] + .05);
            };
            const revisar = (doc, win, donde) => {
                const hero = doc.querySelector('.o_dcasa_hero:not(.o_dcasa_hero_compacto)');
                const foto = hero.querySelector('.o_dcasa_hero_media img');
                const cs = win.getComputedStyle(foto);
                const velo = 1 - parseFloat(cs.opacity);
                if (velo < .35 - 1e-6 || velo > .45 + 1e-6) fallar(donde + ': velo fuera de 35-45 %: ' + cs.opacity);
                if (cs.filter !== 'none' || cs.mixBlendMode !== 'normal') fallar(donde + ': la foto tiene filtro');
                if (win.getComputedStyle(hero).backgroundColor !== 'rgb(0, 0, 0)') {
                    fallar(donde + ': el velo no es negro plano');
                }
                const media = win.getComputedStyle(foto.parentElement);
                if (media.backgroundImage !== 'none') fallar(donde + ': degradado o imagen sobre la foto');
                if (media.position !== 'absolute') {
                    fallar(donde + ': la foto no va detrás del texto (' + media.position + ')');
                }
                for (const capa of ['::before', '::after']) {
                    const v = win.getComputedStyle(foto.parentElement, capa);
                    if (v.content !== 'none' && v.content !== 'normal') {
                        fallar(donde + ': capa encima de la foto ' + capa);
                    }
                }
                // Sin placa: el bloque de texto es transparente y se superpone a la foto.
                const texto = hero.querySelector('.o_dcasa_hero_texto');
                const fondo = win.getComputedStyle(texto);
                if (fondo.backgroundColor !== 'rgba(0, 0, 0, 0)' || fondo.backgroundImage !== 'none') {
                    fallar(donde + ': placa detrás del texto: ' + fondo.backgroundColor);
                }
                if (!solapa(texto.getBoundingClientRect(), foto.getBoundingClientRect())) {
                    fallar(donde + ': el texto no está sobre la foto');
                }
                const titulo = hero.querySelector('.o_dcasa_display');
                const sub = hero.querySelector('.o_dcasa_hero_sub');
                for (const el of [titulo, sub]) {
                    const e = win.getComputedStyle(el);
                    if (e.color !== 'rgb(255, 255, 255)') fallar(donde + ': texto no blanco: ' + e.color);
                    if (e.textShadow === 'none') fallar(donde + ': texto sin halo de contraste');
                }
                // AA: 4.5:1 para el subtítulo y 3:1 para el titular (texto grande), contra la foto velada.
                const cSub = contraste(foto, 1 - velo, sub.getBoundingClientRect());
                const cTit = contraste(foto, 1 - velo, titulo.getBoundingClientRect());
                if (cSub < 4.5) fallar(donde + ': subtítulo bajo AA sobre la foto: ' + cSub.toFixed(2) + ':1');
                if (cTit < 3) fallar(donde + ': titular bajo AA sobre la foto: ' + cTit.toFixed(2) + ':1');
                console.log(donde + ': velo ' + Math.round(velo * 100) + ' %, subtítulo ' + cSub.toFixed(2)
                    + ':1, titular ' + cTit.toFixed(2) + ':1');
            };
            const foto = document.querySelector('.o_dcasa_hero:not(.o_dcasa_hero_compacto) .o_dcasa_hero_media img');
            if (!foto.complete) await new Promise((ok) => { foto.onload = ok; foto.onerror = ok; });
            revisar(document, window, 'escritorio');
            // El vidrio «fluye» donde hay refracción (Chromium): ruido animado, 18 s.
            if (document.documentElement.classList.contains('o_dcasa_refraccion')
                    && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
                const anim = document.querySelector('#dcasa-liquido feTurbulence animate');
                if (!anim || anim.getAttribute('dur') !== '18s') {
                    fallar('el vidrio no fluye (sin animación del ruido)');
                }
            }
            const pie = document.querySelector('footer#bottom');
            for (const el of [pie, ...pie.querySelectorAll('*')]) {
                const e = getComputedStyle(el);
                if (e.backgroundImage !== 'none' || e.filter !== 'none' || parseFloat(e.opacity) < 1) {
                    fallar('el pie tiene imagen, filtro u opacidad en ' + el.tagName + '.' + el.className);
                    break;
                }
            }
            // Celular: la misma portada en un marco de 390 px; el texto también va sobre la foto.
            const marco = document.createElement('iframe');
            marco.style.cssText = 'position:fixed;left:0;top:0;width:390px;height:844px;border:0;';
            document.body.appendChild(marco);
            await new Promise((ok) => { marco.onload = ok; marco.src = '/'; });
            const fotoM = marco.contentDocument.querySelector(
                '.o_dcasa_hero:not(.o_dcasa_hero_compacto) .o_dcasa_hero_media img');
            if (!fotoM.complete) await new Promise((ok) => { fotoM.onload = ok; fotoM.onerror = ok; });
            revisar(marco.contentDocument, marco.contentWindow, 'celular');
            console.log('test successful');
            })();
        """
        self.browser_js('/', codigo_portada, timeout=120)

        # La misma píldora líquida en todas partes: clara con texto en tinta sobre fondo claro
        # (tienda), ahumada con texto blanco sobre una foto (/socios, al cargar).
        codigo_pildora = """
            const fallar = (m) => console.error('Diseño: ' + m);
            const vidrio = getComputedStyle(document.querySelector('header#top .o_main_nav'), '::before');
            const filtro = vidrio.backdropFilter || vidrio.webkitBackdropFilter || 'none';
            // Blur + saturación + brillo del vidrio líquido, o la refracción (url(#dcasa-liquido)) en Chromium.
            if (!/^blur\\(16px\\) saturate\\(2\\.1\\) brightness\\(1\\.08\\)$|^url\\(/.test(filtro)) {
                fallar('la píldora no es de vidrio líquido: ' + filtro);
            }
            if ((vidrio.boxShadow.match(/inset/g) || []).length < 2) fallar('la píldora no tiene los filos de luz');
            if (vidrio.backgroundColor !== '%(fondo)s') fallar('tinte del vidrio: ' + vidrio.backgroundColor);
            const enlace = getComputedStyle(document.querySelector('#top_menu .nav-link:not(.active)')).color;
            if (enlace !== '%(texto)s') fallar('color del menú: ' + enlace);
            console.log('test successful');
        """
        self.browser_js('/shop', codigo_pildora % {
            'fondo': 'rgba(255, 255, 255, 0.62)', 'texto': 'rgb(27, 34, 51)'}, timeout=120)
        self.browser_js('/socios', codigo_pildora % {
            'fondo': 'rgba(0, 0, 0, 0.26)', 'texto': 'rgb(255, 255, 255)'}, timeout=120)
