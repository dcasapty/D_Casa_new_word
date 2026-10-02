"""Fase 0 del sitio: LCP, datos estructurados, textos en español y promesas sin respaldo."""
import base64
import io
import json
import re

from markupsafe import Markup
from PIL import Image

from odoo.addons.website_dcasa.controllers.main import _sin_disponibilidad
from odoo.addons.website_dcasa.models.website import SEO_PORTADA
from odoo.tests import HttpCase, TransactionCase, tagged

PAGINAS_PUBLICAS = ('/', '/shop', '/visitanos', '/socios', '/contactus', '/privacidad', '/terminos')


def _json_ld(html):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _texto_visible(html):
    """Texto entre etiquetas, sin scripts ni estilos (no cuenta atributos como placeholder)."""
    return re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S)


@tagged('post_install', '-at_install')
class TestSitioFase0(HttpCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        valores = {
            'name': 'Cama de prueba', 'list_price': 150.0, 'is_published': True,
            'public_categ_ids': [(6, 0, self.recamaras.ids)],
        }
        if 'is_storable' in self.env['product.template']._fields:
            valores['is_storable'] = True  # con website_sale_stock, Odoo le pondría «InStock/OutOfStock»
        self.cama = self.env['product.template'].create(valores)

    def _dominio_real(self):
        self.website.domain = False
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://dcasapty.com')

    # -- Hero / LCP ---------------------------------------------------------------------------

    def test_imagen_principal_no_es_perezosa(self):
        """Odoo pone loading="lazy" a toda <img> sin atributo: la imagen LCP lo lleva explícito."""
        casos = (('/', 'hero.webp'), ('/visitanos', 'insp-3.webp'))  # la foto del hero de cada página
        for ruta, foto in casos:
            img = re.search(rf'<img[^>]*src="/website_dcasa/static/src/img/{re.escape(foto)}"[^>]*>',
                            self.url_open(ruta).text)
            self.assertTrue(img, ruta)
            etiqueta = img.group(0)
            self.assertIn('loading="eager"', etiqueta, ruta)
            self.assertIn('fetchpriority="high"', etiqueta, ruta)
            self.assertNotIn('loading="lazy"', etiqueta, ruta)

    # -- Rendimiento (auditoría ronda 4): fuentes locales y fotos de la tienda ----------------

    def _css_del_sitio(self, html):
        enlace = re.search(r'href="([^"]*web\.assets_frontend[^"]*\.css)"', html)
        self.assertTrue(enlace, 'La página debe enlazar el bundle CSS del sitio')
        return self.url_open(enlace.group(1)).text

    def test_fuentes_autoalojadas_sin_google(self):
        """Anton, Oswald e Inter salen del módulo: ni @import ni preconnect a Google Fonts."""
        for ruta in ('/', '/shop'):
            html = self.url_open(ruta).text
            self.assertNotIn('fonts.googleapis.com', html, ruta)
            self.assertNotIn('fonts.gstatic.com', html, ruta)
        css = self._css_del_sitio(self.url_open('/').text)
        self.assertNotIn('fonts.googleapis.com', css)
        self.assertNotIn('fonts.gstatic.com', css)
        fuentes = (('anton-latin', 'Anton'), ('oswald-latin-var', 'Oswald'), ('inter-latin-var', 'Inter'))
        for archivo, familia in fuentes:
            regla = re.search(r'@font-face\s*\{[^}]*font-family:\s*["\']?' + familia + r'["\']?;[^}]*\}', css)
            self.assertTrue(regla, familia)
            # La URL tiene que quedar absoluta: el empaquetador de Odoo vuelve relativa a la hoja
            # (…/static/src/scss//website_dcasa/…) toda url() que no empiece por «/» en el fuente.
            url = re.search(r'src:\s*url\(["\']?([^"\')]+)["\']?\)', regla.group(0))
            self.assertTrue(url, familia)
            self.assertEqual(url.group(1), f'/website_dcasa/static/src/fonts/{archivo}.woff2')
            self.assertRegex(regla.group(0), r'font-display:\s*swap')
            fuente = self.url_open(f'/website_dcasa/static/src/fonts/{archivo}.woff2')
            self.assertEqual(fuente.status_code, 200, archivo)
            self.assertEqual(fuente.content[:4], b'wOF2', archivo)
        # La licencia viaja con las fuentes (SIL OFL 1.1).
        for familia in ('Anton', 'Oswald', 'Inter'):
            licencia = self.url_open(f'/website_dcasa/static/src/fonts/OFL-{familia}.txt')
            self.assertEqual(licencia.status_code, 200, familia)
            self.assertIn('SIL OPEN FONT LICENSE', licencia.text)

    def test_precarga_de_las_fuentes_del_primer_pantallazo(self):
        html = self.url_open('/').text
        for archivo in ('anton-latin', 'inter-latin-var'):
            enlace = re.search(r'<link[^>]*href="/website_dcasa/static/src/fonts/' + archivo + r'\.woff2"[^>]*>', html)
            self.assertTrue(enlace, archivo)
            for atributo in ('rel="preload"', 'as="font"', 'type="font/woff2"', 'crossorigin'):
                self.assertIn(atributo, enlace.group(0), archivo)

    def _foto(self, color):
        salida = io.BytesIO()
        Image.new('RGB', (1200, 1200), color).save(salida, format='JPEG')
        return base64.b64encode(salida.getvalue())

    def test_tarjetas_de_la_tienda_con_foto_a_su_tamano(self):
        """/shop: srcset 256/512/1024 con `sizes`, width/height (CLS) y solo la 1.ª fila «eager»."""
        for nombre, color in (('Colchón de prueba', 'blue'), ('Zapatera de prueba', 'yellow')):
            self.env['product.template'].create({
                'name': nombre, 'list_price': 99.0, 'is_published': True, 'image_1920': self._foto(color),
                'public_categ_ids': [(6, 0, self.recamaras.ids)],
            })
        html = self.url_open('/shop').text
        fotos = re.findall(r'<img[^>]*class="[^"]*\boe_product_image_img\b[^"]*"[^>]*>', html)
        self.assertGreaterEqual(len(fotos), 3, 'una foto por producto publicado')
        for foto in fotos:
            self.assertIn('width="512"', foto)
            self.assertIn('height="512"', foto)
            self.assertRegex(foto, r'src="/web/image/product\.(?:template|product)/\d+/image_512/[^"]*\?unique=')
            self.assertRegex(foto, r'srcset="[^"]*/image_256/[^" ]*\?unique=\w+ 256w, [^"]*/image_512/[^" ]* 512w, '
                                   r'[^"]*/image_1024/[^" ]* 1024w"')
            self.assertRegex(foto, r'sizes="[^"]*vw"')
        # La primera fila del celular (dos tarjetas, ahí está la LCP) no espera; el resto sí.
        for foto in fotos[:2]:
            self.assertIn('loading="eager"', foto)
            self.assertIn('fetchpriority="high"', foto)
        for foto in fotos[2:]:
            self.assertIn('loading="lazy"', foto)
            self.assertNotIn('fetchpriority', foto)
        self.assertEqual(html.count('fetchpriority="high"'), 2)

    def test_tarjetas_de_la_tienda_sin_salto_del_paginador(self):
        """CLS 0,126: las tarjetas fuera de pantalla nacían con alto 0 (content-visibility: auto)."""
        css = self._css_del_sitio(self.url_open('/shop').text)
        self.assertRegex(css, r'#o_wsale_products_grid \.oe_product_cart\s*\{\s*contain-intrinsic-size:\s*auto \d+px')

    def test_carril_de_la_portada_con_srcset(self):
        mesa = self.env['product.template'].create({
            'name': 'Mesa de prueba', 'list_price': 59.0, 'is_published': True, 'image_1920': self._foto('red'),
            'public_categ_ids': [(6, 0, self.recamaras.ids)],
        })
        html = self.url_open('/').text
        fotos = re.findall(r'<a[^>]*class="o_dcasa_pcard_media"[^>]*>\s*<picture>.*?<img[^>]*>', html, re.S)
        self.assertTrue(fotos)
        # Con foto: WebP desde /dcasa/img; sin foto, solo la <img> de Odoo (su marcador).
        con_foto = [f for f in fotos if f'href="{mesa.website_url}"' in f]
        self.assertTrue(con_foto)
        self.assertIn('<source type="image/webp"', con_foto[0])
        self.assertRegex(con_foto[0], r'srcset="/dcasa/img/product\.template/\d+/image_1920/'
                                      r'256\.webp\?v=\w{12} 256w, [^"]*/512\.webp\?v=\w{12} 512w"')
        for foto in fotos:
            self.assertRegex(foto, r'srcset="[^"]*image_256[^"]* 256w, [^"]*image_512[^"]* 512w"')
            self.assertIn('sizes="', foto)
            self.assertIn('width="512"', foto)
            self.assertIn('loading="lazy"', foto)

    # -- JSON-LD ------------------------------------------------------------------------------

    def test_json_ld_sin_entidades_html_ni_localhost(self):
        self._dominio_real()
        for ruta in ('/', '/shop', self.cama.website_url):
            html = self.url_open(ruta).text
            bloques = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
            self.assertTrue(bloques, ruta)
            for bloque in bloques:
                self.assertNotIn('&#39;', bloque, ruta)
                self.assertNotIn('&amp;', bloque, ruta)
                self.assertNotIn('localhost', bloque, ruta)
                self.assertNotIn('127.0.0.1', bloque, ruta)
            organizacion = next(b for b in _json_ld(html) if b.get('@type') == 'Organization')
            self.assertEqual(organizacion['name'], self.website.company_id.name, ruta)
            self.assertEqual(organizacion['url'], 'https://dcasapty.com', ruta)

    def test_url_local_nunca_sale_en_el_json_ld(self):
        self.website.domain = False
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'http://localhost:8069')
        self.assertEqual(self.website._dcasa_url_publica(), '')
        for texto in (self.website._dcasa_json_ld_organizacion(), self.website._dcasa_json_ld()):
            self.assertNotIn('localhost', texto)
            self.assertNotIn('"url"', texto)
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'http://127.0.0.1:8069')
        self.assertEqual(self.website._dcasa_url_publica(), '')
        # website.domain manda sobre web.base.url.
        self.website.domain = 'https://dcasapty.com'
        self.assertEqual(self.website._dcasa_url_publica(), 'https://dcasapty.com')
        self.assertEqual(json.loads(self.website._dcasa_json_ld())['url'], 'https://dcasapty.com')

    def test_json_ld_organizacion_seguro_en_script(self):
        self.website.company_id.name = "D'CASA </script><script>alert(1)</script>"
        texto = str(self.website._dcasa_json_ld_organizacion().__html__())
        self.assertNotIn('<', texto)
        self.assertEqual(json.loads(texto)['name'], self.website.company_id.name)

    def test_producto_sin_disponibilidad_inventada_y_migas_en_espanol(self):
        html = self.url_open(self.cama.website_url).text
        bloques = _json_ld(html)
        producto = next(b for grupo in bloques for b in (grupo if isinstance(grupo, list) else [grupo])
                        if b.get('@type') in ('Product', 'ProductGroup'))
        self.assertNotIn('availability', json.dumps(producto), 'El stock está sin confirmar: no se publica')
        migas = next(b for grupo in bloques for b in (grupo if isinstance(grupo, list) else [grupo])
                     if b.get('@type') == 'BreadcrumbList')
        self.assertEqual(migas['itemListElement'][0]['name'], 'Todos los productos')
        self.assertNotIn('All Products', html)

    def test_sin_disponibilidad_quita_todas_las_ofertas(self):
        datos = [{'@type': 'ProductGroup', 'hasVariant': [
            {'offers': {'price': 1, 'availability': 'https://schema.org/InStock'}},
            {'offers': {'price': 2, 'availability': 'https://schema.org/OutOfStock'}},
        ]}]
        limpio = _sin_disponibilidad(datos)
        self.assertNotIn('availability', json.dumps(limpio))
        self.assertEqual(limpio[0]['hasVariant'][1]['offers']['price'], 2)

    # -- Textos en español ----------------------------------------------------------------------

    def test_tienda_y_migas_en_espanol(self):
        for ruta in ('/shop', self.cama.website_url):
            visible = _texto_visible(self.url_open(ruta).text)
            self.assertIn('Todos los productos', visible, ruta)
            self.assertNotRegex(visible, r'>\s*All [Pp]roducts\s*<', ruta)
            self.assertNotIn('aria-label="Main"', visible, ruta)
            self.assertNotIn('aria-label="Mobile"', visible, ruta)
        self.assertRegex(self.url_open('/shop').text, r'<title>Catálogo \| D')

    def test_seo_de_la_portada_en_todas_sus_copias(self):
        html = self.url_open('/').text
        titulo = SEO_PORTADA['website_meta_title'].replace("'", '&#39;')
        self.assertIn(f'<title>{titulo}</title>', html)
        descripcion = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        self.assertEqual(descripcion, SEO_PORTADA['website_meta_description'])
        self.assertNotIn('This is the homepage', html)
        paginas = self.env['website.page'].search([('url', '=', '/')])
        for pagina in paginas:
            self.assertEqual(pagina.with_context(lang='es_419').website_meta_description,
                             SEO_PORTADA['website_meta_description'])

    def test_seo_de_la_portada_respeta_lo_escrito_por_la_duena(self):
        pagina = self.env['website.page'].search([('url', '=', '/')], limit=1)
        pagina.with_context(lang='es_419').website_meta_description = 'Texto propio de la dueña'
        self.env['website']._dcasa_seo_portada()
        self.assertEqual(pagina.with_context(lang='es_419').website_meta_description, 'Texto propio de la dueña')

    # -- SW-03: promesas sin respaldo -------------------------------------------------------------

    def test_ninguna_pagina_publica_promete_financiamiento(self):
        for ruta in (*PAGINAS_PUBLICAS, self.cama.website_url):
            html = self.url_open(ruta).text
            self.assertNotIn('financiamiento', html.lower(), ruta)
            self.assertNotIn('crédito flexible', html.lower(), ruta)
        portada = self.url_open('/').text
        descripcion = re.search(r'<meta name="description" content="([^"]*)"', portada).group(1)
        self.assertNotIn('comedores', descripcion.lower(), 'El catálogo no tiene comedores')

    def test_pago_al_recibir_no_promete_tarjeta(self):
        cod = self.env.ref('delivery.payment_provider_cod')
        self.assertNotIn('tarjeta', str(cod.with_context(lang='es_419').pending_msg).lower())

    # -- SW-07 --------------------------------------------------------------------------------

    def test_enlace_activo_del_menu_en_navy(self):
        html = self.url_open('/').text
        css_link = re.search(r'href="([^"]*web\.assets_frontend[^"]*\.css)"', html).group(1)
        css = self.url_open(css_link).text
        self.assertRegex(css, r'(?i)#top_menu \.nav-link\.active\s*\{\s*color:\s*#0e2a6b')


@tagged('post_install', '-at_install')
class TestRetirarPromesas(TransactionCase):
    """La migración 19.0.1.8.0 limpia las copias por sitio que traían las promesas viejas."""

    def test_copia_por_sitio_y_mensaje_de_pago(self):
        website = self.env.ref('website.default_website')
        vista = self.env['ir.ui.view'].create({
            'name': 'Copia vieja', 'type': 'qweb', 'key': 'website_dcasa.prueba_copia_vieja',
            'website_id': website.id,
            'arch_db': '<t t-name="website_dcasa.prueba_copia_vieja"><div>'
                       '<span class="d-none d-md-inline"><i class="fa fa-credit-card me-2" aria-hidden="true"/>'
                       'Financiamiento flexible</span>'
                       '<p>Varias, y también financiamiento flexible. Escríbenos y te explicamos la que mejor '
                       'te sirve.</p></div></t>',
        })
        cod = self.env.ref('delivery.payment_provider_cod')
        cod.with_context(lang='es_419').pending_msg = Markup(
            '<p>Pagas al recibir o en la tienda: efectivo, Yappy o tarjeta. '
            'Te escribimos por WhatsApp para confirmar la fecha.</p>')

        self.assertGreaterEqual(self.env['website']._dcasa_retirar_promesas(), 2)

        for idioma in ('en_US', 'es_419'):
            arch = vista.with_context(lang=idioma).arch_db
            self.assertNotIn('inanciamiento', arch, idioma)
            self.assertIn('Tienda en La Chorrera', arch, idioma)
            self.assertIn('Transferencia bancaria, Yappy', arch, idioma)
        self.assertNotIn('tarjeta', str(cod.with_context(lang='es_419').pending_msg))
        self.assertEqual(self.env['website']._dcasa_retirar_promesas(), 0, 'Se puede volver a correr')
