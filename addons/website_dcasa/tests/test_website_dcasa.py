import base64
import json
import re

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools.misc import file_open


@tagged('post_install', '-at_install')
class TestWhatsappLink(TransactionCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')

    def test_whatsapp_url_uses_configured_number(self):
        self.website.dcasa_whatsapp_number = '+507 6026-1919'
        url = self.website._dcasa_whatsapp_url('Hola D\'CASA')
        self.assertTrue(url.startswith('https://wa.me/50760261919?text='))
        self.assertIn('Hola%20D%27CASA', url)

    def test_whatsapp_url_falls_back_to_company_phone(self):
        self.website.dcasa_whatsapp_number = False
        self.website.company_id.phone = '+507 6000-1111'
        self.assertTrue(self.website._dcasa_whatsapp_url().startswith('https://wa.me/50760001111'))

    def test_whatsapp_url_without_number_goes_to_contact(self):
        self.website.dcasa_whatsapp_number = False
        self.website.company_id.phone = False
        self.assertEqual(self.website._dcasa_whatsapp_url(), '/contactus')


@tagged('post_install', '-at_install')
class TestWebsitePages(HttpCase):

    def test_homepage(self):
        response = self.url_open('/')
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('Tu casa, bien amueblada.', html)
        self.assertIn('https://wa.me/50760261919', html)
        self.assertIn('o_dcasa_wa_float', html)
        salas = self.env.ref('website_dcasa.public_category_salas')
        self.assertIn(f"/shop/category/{self.env['ir.http']._slug(salas)}", html)
        self.assertIn('info@dcasapty.com', html, 'El pie de página muestra los datos reales')
        self.assertNotIn('555-555-5556', html, 'No debe quedar el teléfono de ejemplo de Odoo')
        self.assertNotIn('Company name', html, 'No debe quedar el copyright de ejemplo de Odoo')

    def test_socios_linked_from_site(self):
        home = self.url_open('/').text
        self.assertIn('href="/socios"', home)
        self.assertIn('Suma puntos y gana invitando', home)
        response = self.url_open('/socios')
        self.assertEqual(response.status_code, 200)
        self.assertIn('https://wa.me/50760261919', response.text, 'La app del socio usa el mismo sitio y pie')

    def test_shop(self):
        self.assertEqual(self.url_open('/shop').status_code, 200)

    def test_frontend_css_compiles_with_brand(self):
        html = self.url_open('/').text
        css_links = re.findall(r'href="([^"]*web\.assets_frontend[^"]*\.css)"', html)
        self.assertTrue(css_links, 'La página debe enlazar el bundle CSS del sitio')
        css = self.url_open(css_links[0]).text
        self.assertIn('o_dcasa_pcard', css)
        self.assertIn('o_dcasa_hero_texto', css)
        self.assertIn('o_dcasa_wa_float', css)
        self.assertRegex(css.lower(), r'#1340b1|rgb\(19,\s*64,\s*177\)')


@tagged('post_install', '-at_install')
class TestPortadaDinamica(HttpCase):
    """Carriles de productos, compra en 1 clic y SEO de la portada."""

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.salas = self.env.ref('website_dcasa.public_category_salas')
        self.colchones = self.env.ref('website_dcasa.public_category_colchones')
        Product = self.env['product.template']
        self.sofa = Product.create({
            'name': 'Sofá de prueba', 'list_price': 123.45, 'is_published': True,
            'website_sequence': -100, 'public_categ_ids': [(6, 0, self.salas.ids)],
        })
        self.colchon = Product.create({
            'name': 'Colchón de prueba', 'list_price': 99.0, 'is_published': True,
            'website_sequence': -99, 'public_categ_ids': [(6, 0, self.colchones.ids)],
        })
        self.oculto = Product.create({
            'name': 'Mueble sin publicar', 'list_price': 10.0, 'is_published': False,
            'website_sequence': -101,
        })

    def test_productos_de_la_portada(self):
        todos = [i['producto'] for i in self.website._dcasa_productos(limit=50)]
        self.assertIn(self.sofa, todos)
        self.assertNotIn(self.oculto, todos, 'La portada solo muestra lo publicado')
        descanso = [i['producto'] for i in self.website._dcasa_productos(limit=50, categorias=['colchones'])]
        self.assertIn(self.colchon, descanso)
        self.assertNotIn(self.sofa, descanso)

    def test_portada_muestra_productos_con_precio_y_agregar(self):
        html = self.url_open('/').text
        self.assertIn('Sofá de prueba', html)
        self.assertRegex(html, r'123[.,]45')
        self.assertIn('action="/dcasa/carrito/agregar"', html)
        self.assertNotIn('Mueble sin publicar', html)
        self.assertIn('Lo más buscado', html)
        self.assertIn('Para dormir mejor', html)

    def test_cifras_de_socios_salen_de_puntos_json(self):
        reglas = self.website._dcasa_reglas_socios()
        html = self.url_open('/').text
        self.assertIn('{:,}'.format(reglas['referido']['puntosAlPadrino']), html)
        self.assertIn('{:,}'.format(reglas['referido']['puntosAlAhijado']), html)

    def test_json_ld_tienda(self):
        html = self.url_open('/').text
        bloques = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        datos = next((b for b in bloques if b.get('@type') == 'FurnitureStore'), None)
        self.assertTrue(datos, 'La portada publica los datos de la tienda')
        self.assertEqual(datos['@type'], 'FurnitureStore')
        self.assertEqual(datos['address']['addressCountry'], 'PA')
        self.assertNotIn('FurnitureStore', self.url_open('/shop').text, 'Solo en la portada')

    def test_seo_de_la_portada(self):
        html = self.url_open('/').text
        self.assertIn('Mueblería en La Chorrera', html)
        self.assertIn('name="description"', html)

    def test_agregar_al_carrito_en_un_clic(self):
        self.authenticate(None, None)
        home = self.url_open('/').text
        token = re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', home).group(1)
        respuesta = self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token, 'product_template_id': self.sofa.id,
        }, allow_redirects=False)
        self.assertIn(respuesta.status_code, (302, 303))
        self.assertTrue(respuesta.headers['Location'].endswith('/shop/cart'))
        carrito = self.url_open('/shop/cart').text
        self.assertIn('Sofá de prueba', carrito)

    def test_agregar_producto_no_publicado_no_entra(self):
        self.authenticate(None, None)
        home = self.url_open('/').text
        token = re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', home).group(1)
        respuesta = self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token, 'product_template_id': self.oculto.id,
        }, allow_redirects=False)
        self.assertTrue(respuesta.headers['Location'].endswith('/shop'))
        self.assertNotIn('Mueble sin publicar', self.url_open('/shop/cart').text)

    def test_ficha_de_producto_con_whatsapp_y_sellos(self):
        html = self.url_open(self.sofa.website_url).text
        self.assertIn('o_dcasa_sellos', html)
        self.assertIn('me%20interesa%3A%20Sof%C3%A1%20de%20prueba', html)

    def test_ficha_sin_promesas_inventadas(self):
        html = self.url_open(self.sofa.website_url).text
        self.assertNotIn('30-day', html)
        self.assertNotIn('30 días', html)

    def test_tienda_con_descripcion_para_google(self):
        html = self.url_open('/shop').text
        self.assertRegex(html, r'<meta name="description" content="Tienda en línea de D(&#39;|\')CASA')

    def _token(self):
        self.authenticate(None, None)
        home = self.url_open('/').text
        return re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', home).group(1)

    def _agregar(self, product_template_id, token=None):
        return self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token or self._token(), 'product_template_id': product_template_id,
        }, allow_redirects=False)

    def test_agregar_sin_csrf_se_rechaza(self):
        self.authenticate(None, None)
        respuesta = self.url_open('/dcasa/carrito/agregar', data={'product_template_id': self.sofa.id},
                                  allow_redirects=False)
        self.assertEqual(respuesta.status_code, 400)

    def test_agregar_id_invalido_va_a_la_tienda(self):
        respuesta = self._agregar('abc')
        self.assertTrue(respuesta.headers['Location'].endswith('/shop'))

    def test_producto_con_variantes_va_a_la_ficha(self):
        color = self.env['product.attribute'].create({
            'name': 'Color prueba',
            'value_ids': [(0, 0, {'name': 'Gris'}), (0, 0, {'name': 'Azul'})],
        })
        self.sofa.attribute_line_ids = [(0, 0, {
            'attribute_id': color.id, 'value_ids': [(6, 0, color.value_ids.ids)],
        })]
        respuesta = self._agregar(self.sofa.id)
        self.assertIn(self.sofa.website_url, respuesta.headers['Location'])
        self.assertIn('>Elegir<', self.url_open('/').text, 'Con variantes la tarjeta lleva a la ficha')

    def test_precio_cero_bloqueado_no_se_agrega(self):
        self.website.prevent_zero_price_sale = True
        gratis = self.env['product.template'].create({
            'name': 'Mueble a consultar', 'list_price': 0.0, 'is_published': True, 'website_sequence': -102,
        })
        respuesta = self._agregar(gratis.id)
        self.assertIn(gratis.website_url, respuesta.headers['Location'])
        self.assertNotIn('Mueble a consultar', self.url_open('/shop/cart').text)

    def test_whatsapp_redirige_al_numero_configurado(self):
        self.website.dcasa_whatsapp_number = '+507 6026-1919'
        respuesta = self.url_open('/whatsapp?texto=Hola', allow_redirects=False)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.headers['Location'].startswith('https://wa.me/50760261919?text=Hola'))
        self.website.dcasa_whatsapp_number = False
        self.website.company_id.phone = False
        respuesta = self.url_open('/whatsapp', allow_redirects=False)
        self.assertTrue(respuesta.headers['Location'].endswith('/contactus'))

    def test_json_ld_no_cierra_el_script(self):
        self.website.company_id.name = 'D\'CASA </script><script>alert(1)</script>'
        texto = str(self.website._dcasa_json_ld().__html__())  # lo que QWeb imprime en <script>
        self.assertNotIn('<', texto)
        self.assertEqual(json.loads(texto)['name'], self.website.company_id.name)
        self.assertNotIn('priceRange', texto, 'Sin cifras inventadas')


@tagged('post_install', '-at_install')
class TestMarcaYMovimiento(HttpCase):
    """Sin marca de Odoo, hero sin placa, reseñas reales y animaciones."""

    def test_sin_credito_de_odoo(self):
        for ruta in ('/', '/shop', '/socios'):
            html = self.url_open(ruta).text
            self.assertNotIn('o_brand_promotion', html, ruta)
            self.assertNotIn('utm_source=db', html, ruta)
            self.assertNotIn('Con la tecnología de', html, ruta)

    def test_favicon_de_dcasa(self):
        website = self.env.ref('website.default_website')
        # Odoo lo guarda convertido a .ico: basta con que ya no sea el de Odoo.
        with file_open('web/static/img/favicon.ico', 'rb') as archivo:
            self.assertNotEqual(base64.b64decode(website.favicon), archivo.read())
        self.assertTrue(website.favicon)

    def test_hero_sin_placa_con_texto_blanco(self):
        html = self.url_open('/').text
        self.assertIn('o_dcasa_hero_texto', html)
        self.assertNotIn('o_dcasa_placa', html)
        socios = self.url_open('/socios').text
        self.assertIn('o_dcasa_hero_compacto', socios, 'Las páginas interiores usan el mismo hero')

    def test_resenas_reales_de_google(self):
        resenas = self.env.ref('website.default_website')._dcasa_resenas()
        html = self.url_open('/').text
        self.assertIn(resenas['ficha'], html)
        self.assertIn('Déjanos tu opinión en Google', html)
        self.assertIn('o_dcasa_resenas_pausa', html, 'La cinta se puede pausar (WCAG 2.2.2)')
        for opinion in resenas['opiniones']:
            self.assertIn(opinion['autor'], html)
        self.assertGreater(resenas['copias'], 1)
        self.assertEqual(resenas['copias'] % 2, 0, 'El bucle sin salto necesita un número par de copias')
        self.assertGreaterEqual(len(resenas['opiniones']) * resenas['copias'] / 2, 8)

    def test_animaciones_cargan(self):
        html = self.url_open('/').text
        self.assertIn('data-anim-entrada', html)
        self.assertIn('data-titular', html)
        scripts = re.findall(r'src="([^"]*web\.assets_frontend[^"]*\.js)"', html)
        self.assertTrue(scripts)
        js = ''.join(self.url_open(src).text for src in scripts)
        self.assertIn('website_dcasa.revelar', js, 'Las animaciones son Interactions de Odoo')

    def test_menu_corto_con_catalogo(self):
        website = self.env.ref('website.default_website')
        nombres = website.menu_id.child_id.sorted('sequence').mapped('name')
        self.assertEqual(nombres, ['Catálogo', "Socios D'CASA", 'Visítanos'])
        self.assertEqual(website.menu_id.child_id[0].url, '/shop')
        catalogo = website.menu_id.child_id.filtered(lambda m: m.url == '/shop')
        self.assertEqual(catalogo.with_context(lang='es_419').name, 'Catálogo', 'No «Tienda» en español')
        html = self.url_open('/').text
        self.assertIn('id="visitanos"', html, 'El enlace «Visítanos» tiene a dónde ir')

    def test_navbar_liquido_y_mapa(self):
        html = self.url_open('/').text
        self.assertIn('o_no_autohide_menu', html, 'Las tres opciones del menú nunca se esconden en el «+»')
        self.assertIn('id="dcasa-liquido"', html)
        self.assertIn('https://www.google.com/maps/embed?pb=', html)
        self.assertRegex(html, r'title="Mapa: D(&#39;|\')CASA en La Chorrera"')
        datos = json.loads(self.env.ref('website.default_website')._dcasa_json_ld())
        self.assertEqual(datos['geo']['latitude'], 8.8765881)

    def test_menu_ancla_no_marca_activo(self):
        website = self.env.ref('website.default_website')
        visitanos = website.menu_id.child_id.filtered(lambda m: m.url == '/#visitanos')
        html = self.url_open('/').text
        enlace = re.search(r'<a[^>]*href="/#visitanos"[^>]*>', html).group(0)
        self.assertNotIn('active', enlace, 'Un ancla de la portada no es «la página actual»')
        self.assertTrue(visitanos)

    def test_armar_menu_respeta_lo_agregado(self):
        website = self.env.ref('website.default_website')
        propio = self.env['website.menu'].create({
            'name': 'Ofertas', 'url': '/ofertas', 'parent_id': website.menu_id.id, 'website_id': website.id,
        })
        self.env['website']._dcasa_armar_menu_principal()
        self.env['website']._dcasa_armar_menu_principal()
        urls = website.menu_id.child_id.mapped('url')
        self.assertIn('/ofertas', urls, 'El menú que agregó la dueña se queda')
        self.assertEqual(urls.count('/shop'), 1, 'Sin duplicados al volver a correr')
        self.assertTrue(propio.exists())

    def test_cabecera_sobre_el_hero(self):
        self.assertIn('o_header_overlay', self.url_open('/').text)
        self.assertIn('o_header_overlay', self.url_open('/socios').text)
        self.assertIn('o_header_overlay', self.url_open('/contactus').text)
        self.assertNotIn('o_header_overlay', self.url_open('/shop').text)

    def test_contacto_con_datos_reales(self):
        html = self.url_open('/contactus').text
        self.assertNotIn('Fake Buena Vista', html)
        self.assertNotIn('555-555-5556', html)
        self.assertIn('info@dcasapty.com', html)
        self.assertIn('href="/whatsapp"', html)

    def test_cta_de_la_cabecera_es_whatsapp(self):
        html = self.url_open('/shop').text
        self.assertRegex(html, r'class="[^"]*btn_cta[^"]*"|btn_cta')
        cta = re.search(r'<a[^>]*btn_cta[^>]*>', html).group(0)
        self.assertIn('href="/whatsapp"', cta)

    def test_cache_de_pagina_separa_tarifas(self):
        pagina = self.env.ref('website.homepage_page')
        pedido = type('Pedido', (), {})()
        pedido.website = self.env.ref('website.default_website')
        pedido.lang = self.env['res.lang']._lang_get('en_US')
        pedido.httprequest = type('H', (), {'path': '/'})()
        pedido.session = type('S', (), {'debug': ''})()
        tarifas = self.env['product.pricelist'].create([{'name': 'A'}, {'name': 'B'}])
        claves = []
        for tarifa in tarifas:
            pedido.pricelist = tarifa
            pedido.fiscal_position = self.env['account.fiscal.position']
            claves.append(pagina._get_cache_key(pedido))
        self.assertNotEqual(*claves)


@tagged('post_install', '-at_install')
class TestCarritoReglas(HttpCase):
    """«Agregar» de un clic con la tienda solo para usuarios registrados."""

    def test_tienda_solo_registrados_no_agrega(self):
        website = self.env.ref('website.default_website')
        website.ecommerce_access = 'logged_in'
        producto = self.env['product.template'].create({
            'name': 'Mesa de prueba', 'list_price': 50.0, 'is_published': True,
        })
        self.authenticate(None, None)
        # Sin acceso a la tienda la portada no ofrece «Agregar»: el token sale de otro formulario.
        self.assertNotIn('action="/dcasa/carrito/agregar"', self.url_open('/').text)
        socios = self.url_open('/socios').text
        token = re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', socios).group(1)
        respuesta = self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token, 'product_template_id': producto.id,
        }, allow_redirects=False)
        self.assertNotIn('/shop/cart', respuesta.headers.get('Location', ''))


@tagged('post_install', '-at_install')
class TestResenasRobustas(TransactionCase):

    def test_json_incompleto_no_tumba_la_portada(self):
        from odoo.addons.website_dcasa.models import website as modulo
        website = self.env.ref('website.default_website')
        original = modulo._leer_resenas
        try:
            modulo._leer_resenas = lambda: {'ficha': 'https://x', 'puntuacion': None,
                                            'opiniones': [{'autor': 'A', 'texto': 'Bien', 'estrellas': 5}]}
            self.assertEqual(website._dcasa_resenas()['copias'], 1)
            modulo._leer_resenas = lambda: {'opiniones': [{'texto': 'sin autor'}]}
            self.assertEqual(website._dcasa_resenas()['opiniones'], [])
        finally:
            modulo._leer_resenas = original
