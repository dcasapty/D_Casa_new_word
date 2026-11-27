"""Lote 1 de la web (aprobado por la dueña el 2026-11-13): buscar, Google, /catalogo, el carrito vacío y la foto.

* Las páginas para entrar no salen en Google (``noindex``) y los resultados de búsqueda tampoco
  (``noindex, follow``), en la cabecera ``X-Robots-Tag`` y en ``<meta name="robots">``; nada de eso va al mapa del
  sitio. Los datos estructurados dicen un solo logo.
* ``/catalogo`` y ``/tienda`` llevan al catálogo (301).
* La cabecera busca en el catálogo (/shop?search=…) y en el celular la lupa está a la vista; una tilde ya no da
  «no coincidió…»; sin resultados, las categorías y WhatsApp.
* Carrito vacío en tuteo; «Reordenado rápido» no se le muestra a quien no tiene cuenta.
* La foto de la ficha se ve en grande (la opción de Odoo, siempre encendida) y hay un sitio para botones extra en la
  caja de búsqueda (la cámara de «Busca con una foto»).
"""
import base64
import io
import json
import re

from PIL import Image

from odoo.addons.website_dcasa.models.buscador import (
    BUSQUEDA,
    SIN_INDICE,
    robots_de,
    sin_tildes,
    solo_cambia_una_tilde,
)
from odoo.tests import BaseCase, HttpCase, new_test_user, tagged


def _json_ld(html):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _metas_robots(html):
    return re.findall(r'<meta name="robots" content="([^"]*)"', html)


def _foto(ancho=1200, alto=900):
    salida = io.BytesIO()
    Image.new('RGB', (ancho, alto), (200, 180, 160)).save(salida, 'JPEG')
    return base64.b64encode(salida.getvalue())


@tagged('post_install', '-at_install')
class TestReglas(BaseCase):

    def test_que_paginas_no_salen_en_google(self):
        casos = [
            ('/web/login', {}, SIN_INDICE), ('/web/signup', {}, SIN_INDICE), ('/web/reset_password', {}, SIN_INDICE),
            ('/es/web/login', {}, SIN_INDICE), ('/web/login/totp', {}, SIN_INDICE),
            ('/shop', {'search': 'sofa'}, BUSQUEDA), ('/shop/page/2', {'search': 'sofa'}, BUSQUEDA),
            ('/shop/category/salas-3', {'search': 'sofa'}, BUSQUEDA), ('/en/shop', {'search': 'sofa'}, BUSQUEDA),
            ('/website/search', {'search': 'sofa'}, BUSQUEDA), ('/website/search', {}, BUSQUEDA),
            # Lo que sí se indexa.
            ('/', {}, None), ('/shop', {}, None), ('/shop', {'search': '  '}, None),
            ('/shop/category/salas-3', {}, None), ('/shop/sofa-gris-12', {'search': 'sofa'}, None),
            ('/shop/cart', {'search': 'x'}, None), ('/web/loginx', {}, None), ('/socios', {}, None),
        ]
        for ruta, parametros, esperado in casos:
            with self.subTest(ruta=ruta, parametros=parametros):
                self.assertEqual(robots_de(ruta, parametros), esperado)

    def test_una_tilde_no_es_otra_busqueda(self):
        self.assertEqual(sin_tildes('Sofá CAMÁ'), 'sofa cama')
        self.assertTrue(solo_cambia_una_tilde('sofa', 'sofá'))
        self.assertTrue(solo_cambia_una_tilde('Colchon', 'colchón'))
        self.assertFalse(solo_cambia_una_tilde('sofas', 'sofá'), 'otra palabra: el aviso se queda')
        self.assertFalse(solo_cambia_una_tilde('mesa', 'meza'))
        self.assertFalse(solo_cambia_una_tilde('', 'sofá'))
        self.assertFalse(solo_cambia_una_tilde('sofa', False))


@tagged('post_install', '-at_install')
class TestLoQueGoogleNoMuestra(HttpCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        param = self.env['ir.config_parameter'].sudo()
        param.set_param('auth_signup.invitation_scope', 'b2c')   # que /web/signup exista (en producción puede no)
        param.set_param('auth_signup.reset_password', 'True')
        self.cama = self.env['product.template'].create({
            'name': 'Cama de prueba de Google', 'list_price': 120.0, 'is_published': True,
            'public_categ_ids': [(6, 0, self.env.ref('website_dcasa.public_category_recamaras').ids)]})

    def test_paginas_para_entrar_noindex(self):
        for ruta in ('/web/login', '/web/signup', '/web/reset_password'):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.headers.get('X-Robots-Tag'), SIN_INDICE)
                self.assertEqual(_metas_robots(respuesta.text), [SIN_INDICE], 'un solo <meta name="robots">')

    def test_resultados_de_busqueda_noindex_follow(self):
        recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        categoria = f"/shop/category/{self.env['ir.http']._slug(recamaras)}"
        for ruta in ('/shop?search=cama', f'{categoria}?search=cama'):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.headers.get('X-Robots-Tag'), BUSQUEDA)
                self.assertEqual(_metas_robots(respuesta.text), [BUSQUEDA])

    def test_el_catalogo_y_las_fichas_si_se_indexan(self):
        for ruta in ('/', '/shop', self.cama.website_url, '/visitanos'):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertNotIn('X-Robots-Tag', respuesta.headers)
                self.assertEqual(_metas_robots(respuesta.text), [])

    def test_nada_de_eso_en_el_mapa_del_sitio(self):
        self.env['ir.attachment'].sudo().search([('type', '=', 'binary'), ('url', '=like', '/sitemap-%.xml')]).unlink()
        mapa = self.url_open('/sitemap.xml').text
        self.assertIn(self.cama.website_url, mapa, 'el mapa se armó')
        for prohibido in ('/web/login', '/web/signup', '/web/reset_password', '/website/search', 'search=',
                          '/catalogo', '/tienda'):
            self.assertNotIn(prohibido, mapa)

    def test_un_solo_logo_en_los_datos_estructurados(self):
        self.website.domain = False
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://dcasapty.com')
        logo = f'https://dcasapty.com/web/image/website/{self.website.id}/logo'
        bloques = _json_ld(self.url_open('/').text)
        logos = {b['logo'] for b in bloques if isinstance(b, dict) and b.get('logo')}
        self.assertEqual(logos, {logo}, 'Organization y FurnitureStore dicen el mismo logo')
        self.assertEqual(json.loads(self.website._dcasa_json_ld_organizacion())['logo'], logo)


@tagged('post_install', '-at_install')
class TestBuscarComoElCatalogo(HttpCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        self.sofa = self.env['product.template'].create({
            'name': 'ZZSOFÁ DE PRUEBA DEL BUSCADOR', 'list_price': 189.99, 'is_published': True,
            'public_categ_ids': [(6, 0, self.recamaras.ids)]})

    def _modal(self, html):
        return re.search(r'id="o_search_modal".*?</form>', html, re.S).group(0)

    def test_la_cabecera_busca_en_el_catalogo(self):
        modal = self._modal(self.url_open('/').text)
        self.assertIn('action="/shop"', modal)
        self.assertIn('data-search-type="products"', modal, 'la lista mientras se escribe se queda (solo productos)')
        self.assertIn('placeholder="Busca un mueble"', modal)
        self.assertNotIn('/website/search', modal)

    def test_lupa_a_la_vista_en_el_celular(self):
        html = self.url_open('/').text
        movil = re.search(r'<nav[^>]*o_header_mobile.*?</nav>', html, re.S).group(0)
        botones = re.search(r'o_header_mobile_buttons_wrap.*?</ul>', movil, re.S).group(0)
        lupa = re.search(r'<a[^>]*o_dcasa_lupa_movil[^>]*>', botones).group(0)
        self.assertIn('data-bs-target="#o_search_modal"', lupa, 'abre la misma búsqueda que la computadora')
        self.assertIn('aria-label="Buscar en el catálogo"', lupa)
        self.assertIn('href="/shop"', lupa, 'sin JavaScript, al catálogo')
        self.assertLess(botones.index('o_dcasa_lupa_movil'), botones.index('o_wsale_my_cart'), 'junto al carrito')

    def test_la_busqueda_general_lleva_al_catalogo(self):
        for ruta, destino in (('/website/search?search=sofa', '/shop?search=sofa'),
                              ('/website/search?search=colch%C3%B3n+queen', '/shop?search=colch%C3%B3n+queen'),
                              ('/website/search', '/shop'),
                              ('/website/search/products?search=mesa', '/shop?search=mesa')):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta, allow_redirects=False)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.headers['Location'].endswith(destino), respuesta.headers['Location'])
        self.assertEqual(self.url_open('/website/search/pages?search=socios', allow_redirects=False).status_code, 200,
                         'buscar páginas sigue siendo lo de Odoo')

    def test_catalogo_y_tienda_llevan_al_catalogo(self):
        for ruta, destino in (('/catalogo', '/shop'), ('/tienda', '/shop'),
                              ('/catalogo?search=cama&utm_source=ig', '/shop?search=cama&utm_source=ig')):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta, allow_redirects=False)
                self.assertEqual(respuesta.status_code, 301)
                self.assertTrue(respuesta.headers['Location'].endswith(destino), respuesta.headers['Location'])
        self.assertEqual(self.url_open('/catalogo').url.split('?')[0], self.base_url() + '/shop')

    def test_resultados_como_el_catalogo(self):
        html = self.url_open('/shop?search=ZZSOFÁ').text
        self.assertIn(self.sofa.website_url, html)
        self.assertIn('o_wsale_products_grid_table', html, 'la rejilla del catálogo, con fotos grandes')
        self.assertIn('o_dcasa_mas_itbms', html, 'precio con «+ ITBMS»')

    def test_una_tilde_no_da_no_coincidio(self):
        """«zzsofa» solo existe como «zzsofá»: se muestran sus resultados sin el aviso de «se muestran los de…»."""
        opciones = {'allowFuzzy': True, 'displayImage': False, 'displayDescription': False,
                    'displayExtraLink': False, 'displayDetail': False}
        conteo, _resultados, parecido = self.website._search_with_fuzzy(
            'products_only', 'zzsofa', limit=None, order='name asc', options=opciones)
        self.assertEqual(conteo, 1)
        self.assertFalse(parecido)
        html = self.url_open('/shop?search=zzsofa').text
        self.assertIn(self.sofa.website_url, html)
        self.assertNotIn('o_dcasa_parecido', html)
        self.assertNotIn('No se encontraron resultados', html)

    def test_sin_resultados_ofrece_categorias_y_whatsapp(self):
        html = self.url_open('/shop?search=zzqqxxlampara').text
        bloque = re.search(r'class="o_dcasa_sin_resultados".*?</div>\s*</div>', html, re.S).group(0)
        self.assertIn('No encontramos “zzqqxxlampara”', bloque)
        self.assertIn(self.website._dcasa_categoria_url('recamaras'), bloque, 'la categoría con productos')
        self.assertIn('https://api.whatsapp.com/send?phone=', bloque)
        self.assertIn('busco%3A%20zzqqxxlampara', bloque, 'WhatsApp con lo que buscó ya escrito')
        self.assertIn('Escríbenos por WhatsApp', bloque)
        self.assertNotIn('o_wsale_price_range_option', html, 'sin el rango de precio de «$ 0.00»')

    def test_carrito_vacio_en_tuteo(self):
        html = self.url_open('/shop/cart').text
        self.assertIn('Tu carrito está vacío', html)
        self.assertIn('>Ver el catálogo</a>', html)
        self.assertNotIn('Su carrito', html)
        envoltura = re.search(r'<div class="([^"]*)">\s*<span[^>]*>\s*<button[^>]*id="quick_reorder_button"', html)
        self.assertIn('d-none', envoltura.group(1), 'sin cuenta, «Reordenado rápido» no se ve')
        self.assertIn('id="quick_reorder_sidebar"', html, 'pero sigue en la página: el JavaScript del carrito lo usa')

    def test_con_cuenta_volver_a_pedir(self):
        new_test_user(self.env, login='cliente_buscador', groups='base.group_portal', password='cliente_buscador')
        self.authenticate('cliente_buscador', 'cliente_buscador')
        html = self.url_open('/shop/cart').text
        envoltura = re.search(r'<div class="([^"]*)">\s*<span[^>]*>\s*<button[^>]*id="quick_reorder_button"', html)
        self.assertNotIn('d-none', envoltura.group(1))
        self.assertIn('Volver a pedir', html)
        self.assertNotIn('Reordenado rápido', html)

    def test_la_foto_se_ve_en_grande(self):
        self.assertTrue(self.env.ref('website_sale.product_picture_magnify_click').active)
        self.sofa.image_1920 = _foto()
        html = self.url_open(self.sofa.website_url).text
        self.assertRegex(html, r'class="[^"]*o_wsale_product_page[^"]*ecom-zoomable')
        self.assertIn('data-ecom-zoom-click="1"', html)
        boton = re.search(r'<button[^>]*o_dcasa_ver_grande[^>]*>', html).group(0)
        self.assertIn('aria-label="Ver la foto en grande"', boton)

    def test_sitio_para_botones_extra_del_buscador(self):
        """Un módulo (la cámara de «Busca con una foto») hereda una plantilla vacía y su botón sale en la caja de la
        cabecera y en la barra del catálogo, dentro de la caja, antes de la lupa de enviar."""
        self.env['ir.ui.view'].create({
            'name': 'Botón extra de prueba', 'type': 'qweb', 'mode': 'extension',
            'inherit_id': self.env.ref('website_dcasa.buscador_botones_extra').id,
            'arch': '<xpath expr="." position="inside">'
                    '<button t-if="search_type == \'products\'" type="button" class="o_prueba_extra"/></xpath>',
        })
        modal = self._modal(self.url_open('/').text)
        self.assertRegex(modal, r'(?s)o_prueba_extra.*?oe_search_button', 'en la cabecera, antes de enviar')
        tienda = self.url_open('/shop').text
        barra = re.search(r'<form[^>]*o_wsale_products_searchbar_form.*?</form>', tienda, re.S).group(0)
        self.assertIn('o_prueba_extra', barra, 'y en la barra de /shop')

    def test_con_el_editor_del_sitio_las_paginas_abren(self):
        """Quien puede editar el sitio (admin, Gerencia con ese permiso) recibe las plantillas con las marcas del
        editor. El sitio de botones extra estaba en una parte que Odoo no reparte y el t-call se quedaba con ellas:
        error 500 en todas las páginas con la cabecera (atrapado por dcasa_tienda_borde, test_logueado…)."""
        self.authenticate('admin', 'admin')
        self.sofa.image_1920 = _foto()
        for ruta in ('/', '/shop', '/shop?search=ZZSOFÁ', '/shop?search=zzqqxx', self.sofa.website_url, '/shop/cart',
                     self.website._dcasa_categoria_url('recamaras')):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn('o_dcasa_buscador_extra', respuesta.text)

    def test_la_barra_de_la_tienda_dice_lo_mismo(self):
        tienda = self.url_open('/shop').text
        barra = re.search(r'<form[^>]*o_wsale_products_searchbar_form.*?</form>', tienda, re.S).group(0)
        self.assertIn('placeholder="Busca un mueble"', barra)
        categoria = self.url_open(self.website._dcasa_categoria_url('recamaras')).text
        barra = re.search(r'<form[^>]*o_wsale_products_searchbar_form.*?</form>', categoria, re.S).group(0)
        self.assertNotIn('placeholder="Busca un mueble"', barra, 'en una categoría, el «Buscar en …» de Odoo')
