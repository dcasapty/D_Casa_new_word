"""Fase 0 del sitio: LCP, datos estructurados, textos en español y promesas sin respaldo."""
import json
import re

from markupsafe import Markup

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
