# ruff: noqa: E501  (JavaScript del navegador embebido en texto)
"""Portada (pedido de la dueña, 2026-11-16): el hero en carrusel con productos propios elegidos desde el panel y la
sección «de cine» (models/portada.py, views/homepage_templates.xml, static/src/js/portada.js). Lo que se fija aquí:

* El ajuste: «Sitio web › Carrusel de la portada», una lista que se ordena arrastrando; solo Gerencia y los
  administradores la ven y la cambian.
* Vacío = el hero de siempre (también si nada de la lista se puede mostrar: sin publicar o sin foto). Con productos:
  una diapositiva por producto, en el orden del panel, con su foto grande, su nombre de cliente y el enlace a su ficha;
  la primera foto es la imagen LCP (precargada, «eager», prioridad alta) y los controles nacen escondidos.
* El carrusel nace UNA vez con las camas que aprobó la dueña (por su código público); lo que no existe se salta.
* Con el editor del sitio abierto (quien tiene el grupo de diseñador recibe las plantillas con sus marcas) la portada
  abre, y un hero guardado con el editor sigue dentro de su condición.
* La sección «de cine»: dos cintas con fotos del catálogo publicado (sin repetir los carriles de arriba) y el botón al
  catálogo; sin fotos suficientes no sale.
* En Chrome: las flechas, las barras y la pausa; el avance automático (y quieto con movimiento reducido); deslizar con
  el dedo; las cintas que corren y se pausan; la foto de orilla a orilla sin que el bloque azul noche la tape, la
  píldora clara y nada ensancha la página.
"""
import base64
import contextlib
import io
from unittest.mock import patch

from lxml import html as lhtml
from PIL import Image
from psycopg2 import IntegrityError

from odoo import Command
from odoo.addons.website_dcasa.models.portada import CARRUSEL_INICIAL, MINIMO_CINE, PARAM_SEMBRADO
from odoo.addons.website_dcasa.tests.test_black_weekend import amarillo_sobre_blanco
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tests import common as comun
from odoo.tests.common import ChromeBrowser
from odoo.tools import mute_logger


def _foto(color, ancho=600, alto=800):
    salida = io.BytesIO()
    Image.new('RGB', (ancho, alto), color).save(salida, 'JPEG')
    return base64.b64encode(salida.getvalue())


def _usuario(env, login, *grupos):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login, 'password': login,
        'group_ids': [Command.set([env.ref('base.group_user').id, *(env.ref(g).id for g in grupos)])],
    })


def _clases(nodo):
    return set((nodo.get('class') or '').split())


@tagged('post_install', '-at_install')
class TestCarruselPortada(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.Diapositiva = cls.env['dcasa.portada.diapositiva']
        cls.Diapositiva.search([]).unlink()
        recamaras = cls.env.ref('website_dcasa.public_category_recamaras')
        base = {'type': 'consu', 'is_storable': False, 'sale_ok': True, 'is_published': True, 'list_price': 159.99,
                'public_categ_ids': [Command.set(recamaras.ids)]}
        Plantilla = cls.env['product.template']
        cls.camas = Plantilla.browse()
        for nombre, color in (('CAMA QUEEN NEGRA, CABECERO CON ALAS EN CHEVRON', (20, 20, 20)),
                              ('CAMA KING ROSADA, CABECERO CON ALAS Y CANALES', (230, 150, 170)),
                              ('CAMA QUEEN BEIGE, CABECERO DE PANELES', (220, 205, 180))):
            cls.camas |= Plantilla.create({**base, 'name': f'ZZCARRUSEL {nombre}', 'image_1920': _foto(color)})
        cls.sin_publicar = Plantilla.create({**base, 'name': 'ZZCARRUSEL CAMA SIN PUBLICAR', 'is_published': False,
                                             'image_1920': _foto((90, 90, 90))})
        cls.sin_foto = Plantilla.create({**base, 'name': 'ZZCARRUSEL CAMA SIN FOTO'})
        # Catálogo para la sección «de cine» (también en una base sin el catálogo real): cuatro con foto en cada una de
        # cinco categorías. Los carriles de arriba se llevan como mucho 16; quedan fotos para las cintas.
        cls.catalogo = Plantilla.browse()
        for clave in ('colchones', 'salas', 'zapateras', 'organizacion', 'oficina'):
            categoria = cls.env.ref(f'website_dcasa.public_category_{clave}')
            for i in range(4):
                cls.catalogo |= Plantilla.create({
                    **base, 'name': f'ZZCINE {clave.upper()} {i}', 'public_categ_ids': [Command.set(categoria.ids)],
                    'image_1920': _foto((60 + 30 * i, 120, 160), 300, 400)})
        cls.gerente = _usuario(cls.env, 'gerente_carrusel', 'dcasa_base.group_gerencia')
        cls.vendedora = _usuario(cls.env, 'vendedora_carrusel', 'dcasa_base.group_vendedora')
        cls.interno = _usuario(cls.env, 'interno_carrusel')

    def _elegir(self, *productos):
        self.Diapositiva.search([]).unlink()
        for orden, producto in enumerate(productos, start=1):
            self.Diapositiva.create({'website_id': self.website.id, 'product_tmpl_id': producto.id, 'sequence': orden})

    def _portada(self, ruta='/'):
        respuesta = self.url_open(ruta)
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:2000])
        return respuesta.text, lhtml.fromstring(respuesta.text)

    def _vitrina(self, arbol):
        secciones = arbol.xpath('//section[contains(@class, "o_dcasa_hero_vitrina")]')
        return secciones[0] if secciones else None

    # ------------------------------------------------------------------ el ajuste

    def test_solo_gerencia_y_administradores_eligen_el_carrusel(self):
        Diapositiva = self.Diapositiva.with_user(self.gerente)
        diapositiva = Diapositiva.create({'product_tmpl_id': self.camas[0].id})
        self.assertEqual(diapositiva.website_id, self.website, 'por defecto, el sitio de siempre')
        diapositiva.sequence = 5
        diapositiva.product_tmpl_id = self.camas[1]
        self.assertTrue(diapositiva.en_portada)
        diapositiva.unlink()
        admin = self.env.ref('base.user_admin')
        self.Diapositiva.with_user(admin).create({'product_tmpl_id': self.camas[0].id}).unlink()
        for usuario in (self.vendedora, self.interno):
            with self.subTest(usuario=usuario.login):
                with self.assertRaises(AccessError):
                    self.Diapositiva.with_user(usuario).create({'product_tmpl_id': self.camas[0].id})
                with self.assertRaises(AccessError):
                    self.Diapositiva.with_user(usuario).search([])
        menu = 'website_dcasa.menu_dcasa_portada_diapositiva'
        def menus(usuario):
            datos = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
            return {m['xmlid'] for m in datos.values() if isinstance(m, dict) and m.get('xmlid')}
        self.assertIn(menu, menus(self.gerente), 'Gerencia lo encuentra en Sitio web')
        self.assertNotIn(menu, menus(self.vendedora))

    @mute_logger('odoo.sql_db')
    def test_un_producto_va_una_sola_vez_y_la_lista_dice_cual_no_sale(self):
        self._elegir(self.camas[0], self.sin_publicar, self.sin_foto)
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Diapositiva.create({'website_id': self.website.id, 'product_tmpl_id': self.camas[0].id})
        por_producto = {d.product_tmpl_id: d.en_portada for d in self.Diapositiva.search([])}
        self.assertEqual(por_producto, {self.camas[0]: True, self.sin_publicar: False, self.sin_foto: False})

    # ------------------------------------------------------------------ la portada

    def test_vacio_queda_el_hero_de_siempre(self):
        self.Diapositiva.search([]).unlink()
        texto, arbol = self._portada()
        self.assertIsNone(self._vitrina(arbol))
        self.assertTrue(arbol.xpath('//div[@id="oe_structure_dcasa_hero"]//section[contains(@class, "o_dcasa_hero")]'))
        self.assertIn('/website_dcasa/static/src/img/hero.webp', texto)
        precarga = arbol.xpath('//head/link[@rel="preload"][@as="image"]')
        self.assertEqual([p.get('href') for p in precarga], ['/website_dcasa/static/src/img/hero.webp'])

    def test_con_productos_una_diapositiva_por_producto_en_su_orden(self):
        orden = [self.camas[2], self.camas[0], self.camas[1]]
        self._elegir(orden[0], self.sin_publicar, orden[1], self.sin_foto, orden[2])
        texto, arbol = self._portada()
        vitrina = self._vitrina(arbol)
        self.assertIsNotNone(vitrina, 'con productos elegidos, el hero es el carrusel')
        self.assertFalse(arbol.xpath('//div[@id="oe_structure_dcasa_hero"]'), 'y no el de siempre')
        self.assertNotIn('/website_dcasa/static/src/img/hero.webp', texto)
        self.assertEqual(len(arbol.xpath('//h1')), 1, 'un solo titular en la página')
        self.assertEqual(' '.join(vitrina.xpath('.//h1')[0].text_content().split()), 'Tu casa, bien amueblada.')
        self.assertEqual(vitrina.xpath('.//a[contains(@class, "o_dcasa_btn_amarillo")]/@href'), ['/shop'])

        fotos = vitrina.xpath('.//a[contains(@class, "o_dcasa_vitrina_foto")]')
        self.assertEqual([f.get('href') for f in fotos], [p.website_url for p in orden],
                         'en el orden del panel, sin el producto sin publicar ni el que no tiene foto')
        self.assertEqual([f.xpath('.//img')[0].get('alt') for f in fotos], [p._dcasa_nombre_cliente() for p in orden])
        primera, *demas = [f.xpath('.//img')[0] for f in fotos]
        self.assertEqual((primera.get('loading'), primera.get('fetchpriority')), ('eager', 'high'), 'la imagen LCP')
        self.assertTrue(all(img.get('loading') == 'lazy' for img in demas))
        self.assertIn('is-activa', _clases(fotos[0]))
        self.assertFalse(any('is-activa' in _clases(f) for f in fotos[1:]), 'sin JavaScript se ve la primera')
        # La foto grande: WebP del ancho justo (hasta 1600 px) y, de respaldo, la de Odoo a 1920.
        fuente = fotos[0].xpath('.//source[@type="image/webp"]')[0].get('srcset')
        self.assertIn(f'/dcasa/img/product.template/{orden[0].id}/image_1920/1600.webp', fuente)
        self.assertIn('image_1920', primera.get('srcset'))
        self.assertTrue(all(f.get('tabindex') == '-1' and f.get('aria-hidden') == 'true' for f in fotos))

        textos = vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_textos")]')[0]
        self.assertEqual(textos.get('aria-live'), 'off', 'mientras avanza sola, no interrumpe al lector de pantalla')
        grupos = textos.xpath('./div[@role="group"]')
        self.assertEqual([g.get('aria-label') for g in grupos], ['1 de 3', '2 de 3', '3 de 3'])
        self.assertTrue(all(g.get('aria-roledescription') == 'diapositiva' for g in grupos))
        for grupo, producto in zip(grupos, orden, strict=True):
            self.assertEqual(grupo.xpath('.//p[contains(@class, "o_dcasa_vitrina_nombre")]')[0].text_content(),
                             producto._dcasa_nombre_cliente())
            ver = grupo.xpath('.//a[contains(@class, "o_dcasa_vitrina_ver")]')[0]
            self.assertEqual(ver.get('href'), producto.website_url, 'el botón lleva a su ficha')
            self.assertIn(producto._dcasa_nombre_cliente(), ver.text_content(), 'y dice de qué producto es')

        barras = vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_barras")]')[0]
        self.assertIsNotNone(barras.get('hidden'), 'los controles nacen escondidos')
        self.assertEqual(barras.xpath('./button/@aria-label'),
                         [f'Ver {i} de 3: {p._dcasa_nombre_cliente()}' for i, p in enumerate(orden, start=1)])
        self.assertEqual(barras.xpath('./button/@aria-current'), ['true'])
        botones = vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_botones")]')[0]
        self.assertIsNotNone(botones.get('hidden'))
        self.assertEqual(botones.xpath('./button/@aria-label'),
                         ['Pausar el carrusel', 'Producto anterior', 'Producto siguiente'])
        self.assertEqual(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina")][@role="region"]/@aria-roledescription'),
                         ['carrusel'])

        precarga = arbol.xpath('//head/link[@rel="preload"][@as="image"]')
        self.assertEqual(len(precarga), 1, 'se precarga solo la primera foto del carrusel')
        self.assertEqual(precarga[0].get('imagesrcset'), fuente)
        self.assertEqual(precarga[0].get('fetchpriority'), 'high')

    def test_el_amarillo_nunca_toca_el_blanco(self):
        """El botón amarillo del carrusel va en el bloque azul noche; el de la sección de cine (blanca) es azul."""
        self._elegir(*self.camas)
        texto, arbol = self._portada()
        self.assertEqual(amarillo_sobre_blanco(texto), [])
        vitrina = self._vitrina(arbol)
        self.assertTrue(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_panel")]//h1'), 'el titular, en el bloque')
        self.assertTrue(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_panel")]//a[contains(@class, "o_dcasa_btn_amarillo")]'))
        self.assertNotIn('o_dcasa_hero ', (vitrina.get('class') or '') + ' ',
                         'sin la clase del hero de siempre: la píldora no se vuelve ahumada sobre la foto clara')
        cine = arbol.xpath('//section[contains(@class, "o_dcasa_cine")]')[0]
        self.assertFalse(cine.xpath('.//*[contains(@class, "o_dcasa_btn_amarillo")]'))
        self.assertEqual(cine.xpath('.//a[contains(@class, "btn-primary")]/@href'), ['/shop'])

    def test_si_nada_se_puede_mostrar_vuelve_el_hero_de_siempre(self):
        self._elegir(self.sin_publicar, self.sin_foto)
        _texto, arbol = self._portada()
        self.assertIsNone(self._vitrina(arbol))
        self.assertTrue(arbol.xpath('//div[@id="oe_structure_dcasa_hero"]'))

    def test_un_solo_producto_sin_controles(self):
        self._elegir(self.camas[1])
        _texto, arbol = self._portada()
        vitrina = self._vitrina(arbol)
        self.assertEqual(len(vitrina.xpath('.//a[contains(@class, "o_dcasa_vitrina_foto")]')), 1)
        self.assertFalse(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_barras")]'))
        self.assertFalse(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_botones")]'))

    def test_el_cambio_se_ve_al_momento(self):
        """Odoo guarda la portada de los visitantes hasta una hora: el carrusel va en la clave de esa memoria."""
        self.Diapositiva.search([]).unlink()
        self.assertIsNone(self._vitrina(self._portada()[1]))
        self._elegir(self.camas[0], self.camas[1])
        self.assertIsNotNone(self._vitrina(self._portada()[1]), 'elegir productos se ve sin esperar')
        self._elegir(self.camas[1], self.camas[0])
        fotos = self._vitrina(self._portada()[1]).xpath('.//a[contains(@class, "o_dcasa_vitrina_foto")]/@href')
        self.assertEqual(fotos, [self.camas[1].website_url, self.camas[0].website_url], 'reordenar, también')
        self.Diapositiva.search([]).unlink()
        self.assertIsNone(self._vitrina(self._portada()[1]), 'y vaciar la lista vuelve al hero de siempre')

    def test_con_el_editor_del_sitio_abierto_la_portada_abre(self):
        """Quien tiene el grupo de diseñador recibe las plantillas con las marcas del editor (inherit_branding): ni
        con el carrusel ni sin él la portada puede dar error. Un hero guardado con el editor (una vista que reemplaza
        el bloque por su id) sigue dentro de la condición: sale sin carrusel y no se mezcla con él."""
        # Como lo guarda Odoo: una vista del sitio que hereda la portada que ese sitio dibuja (su copia, si la tiene).
        portada = self.env['website'].with_context(website_id=self.website.id).viewref('website_dcasa.homepage_dcasa')
        self.env['ir.ui.view'].create({
            'name': 'Hero guardado con el editor (prueba)', 'type': 'qweb', 'key': 'prueba_carrusel.hero_guardado',
            'website_id': self.website.id, 'inherit_id': portada.id,
            'arch': """<data><xpath expr="//*[hasclass('oe_structure')][@id='oe_structure_dcasa_hero']" position="replace">
                <div class="oe_structure" id="oe_structure_dcasa_hero"><section class="o_dcasa_hero">
                <h1 class="o_dcasa_display">HERO GUARDADO EN EL EDITOR</h1></section></div></xpath></data>""",
        })
        disenador = _usuario(self.env, 'disenador_carrusel', 'website.group_website_designer')
        self.authenticate(disenador.login, disenador.login)
        for ruta in ('/', '/?enable_editor=1'):
            with self.subTest(ruta=ruta, carrusel=False):
                self.Diapositiva.search([]).unlink()
                texto, arbol = self._portada(ruta)
                self.assertIn('data-oe-model', texto, 'la página trae las marcas del editor')
                self.assertIn('HERO GUARDADO EN EL EDITOR', texto)
                self.assertIsNone(self._vitrina(arbol))
            with self.subTest(ruta=ruta, carrusel=True):
                self._elegir(*self.camas)
                texto, arbol = self._portada(ruta)
                self.assertIsNotNone(self._vitrina(arbol))
                self.assertNotIn('HERO GUARDADO EN EL EDITOR', texto)
                self.assertEqual(len(arbol.xpath('//a[contains(@class, "o_dcasa_vitrina_foto")]')), 3)

    # ------------------------------------------------------------------ nace con las camas aprobadas

    def _cama_con_codigo(self, codigo):
        """Una cama publicada, con foto, con el código público ``codigo`` (el código solo se da al crear)."""
        return self.env['product.template'].create({
            'name': f'ZZCARRUSEL CAMA {codigo}', 'sale_ok': True, 'is_published': True, 'list_price': 199.99,
            'image_1920': _foto((120, 110, 100)), 'dcasa_codigo_publico': codigo})

    def test_nace_una_vez_con_las_camas_aprobadas_y_se_salta_lo_que_no_existe(self):
        Param = self.env['ir.config_parameter'].sudo()
        self.assertTrue(Param.get_param(PARAM_SEMBRADO), 'al instalar ya se intentó (en esta base no hay esas camas)')
        # Tres de las ocho existen, creadas en otro orden; las demás no: se saltan sin error.
        ivory, black, beige = (self._cama_con_codigo(CARRUSEL_INICIAL[i]) for i in (5, 0, 3))
        self.Diapositiva.search([]).unlink()
        Param.set_param(PARAM_SEMBRADO, False)
        self.assertEqual(self.Diapositiva._dcasa_sembrar(), 3)
        diapositivas = self.Diapositiva.search([('website_id', '=', self.website.id)])
        self.assertEqual(list(diapositivas.mapped('product_tmpl_id')), [black, beige, ivory],
                         'en el orden que aprobó la dueña')
        self.assertTrue(Param.get_param(PARAM_SEMBRADO))
        fotos = self._vitrina(self._portada()[1]).xpath('.//a[contains(@class, "o_dcasa_vitrina_foto")]/@href')
        self.assertEqual(fotos, [black.website_url, beige.website_url, ivory.website_url])
        # Desde ahí la lista es de Gerencia: si la vacía (o la cambia), una actualización no la vuelve a llenar.
        diapositivas.unlink()
        self.assertEqual(self.Diapositiva._dcasa_sembrar(), 0)
        self.assertFalse(self.Diapositiva.search_count([]))
        self.assertIsNone(self._vitrina(self._portada()[1]), 'vacía: el hero de siempre')

    def test_no_pisa_una_lista_que_ya_tiene_productos(self):
        self._cama_con_codigo(CARRUSEL_INICIAL[0])
        self._elegir(self.camas[2])
        self.env['ir.config_parameter'].sudo().set_param(PARAM_SEMBRADO, False)
        self.assertEqual(self.Diapositiva._dcasa_sembrar(), 0)
        self.assertEqual(self.Diapositiva.search([]).product_tmpl_id, self.camas[2])

    def test_sin_ninguna_cama_aprobada_queda_el_hero_de_siempre(self):
        self.Diapositiva.search([]).unlink()
        self.env['ir.config_parameter'].sudo().set_param(PARAM_SEMBRADO, False)
        self.assertEqual(self.Diapositiva._dcasa_sembrar(), 0)
        self.assertIsNone(self._vitrina(self._portada()[1]))

    # ------------------------------------------------------------------ la sección «de cine»

    def test_la_seccion_de_cine_trae_fotos_del_catalogo_y_el_boton(self):
        texto, arbol = self._portada()
        seccion = arbol.xpath('//section[contains(@class, "o_dcasa_cine")]')
        self.assertTrue(seccion, 'la portada trae la sección de cine')
        seccion = seccion[0]
        self.assertEqual(seccion.xpath('.//a[contains(@class, "btn-primary")]/@href'), ['/shop'])
        self.assertEqual(' '.join(seccion.xpath('.//a[contains(@class, "btn-primary")]')[0].text_content().split()),
                         'Ver el catálogo')
        self.assertIsNotNone(seccion.xpath('.//button[contains(@class, "o_dcasa_cine_pausa")]')[0].get('hidden'))
        cintas = seccion.xpath('.//div[contains(concat(" ", @class, " "), " o_dcasa_cine_cinta ")]')
        self.assertEqual(len(cintas), 2)
        self.assertIn('is-reversa', _clases(cintas[1]), 'la segunda corre al revés')
        datos = self.website._dcasa_cine()
        publicados = set(self.env['product.template'].search(self.website._dcasa_dominio_publicado()).mapped('website_url'))
        carriles = {p.website_url for p in self.env['product.template'].browse(self.website._dcasa_ids_en_carriles())}
        for cinta, dato in zip(cintas, datos["cintas"], strict=True):
            visibles = cinta.xpath('.//li[not(@aria-hidden)]')
            copias = cinta.xpath('.//li[@aria-hidden="true"]')
            self.assertEqual(len(visibles), len(dato['fotos']), 'cada foto una vez para el lector de pantalla')
            self.assertEqual(len(copias), len(dato['fotos']) * (dato['copias'] - 1))
            self.assertEqual(dato['copias'] % 2, 0, 'copias pares: la vuelta es la mitad exacta')
            self.assertTrue(all(c.xpath('./a')[0].get('tabindex') == '-1' for c in copias), 'las copias no se tabulan')
            for li in visibles:
                enlace = li.xpath('./a')[0]
                self.assertIn(enlace.get('href'), publicados, 'solo productos publicados')
                self.assertNotIn(enlace.get('href'), carriles, 'sin repetir lo de los carriles de arriba')
                self.assertTrue(enlace.get('title'), 'el nombre al pasar el ratón')
                self.assertIn(li.xpath('.//span[contains(@class, "o_dcasa_cine_cat")]')[0].text_content(),
                              {'Recámaras', 'Colchones', 'Salas', 'Zapateras', 'Estantes', 'Oficina'})
        self.assertNotIn(self.sin_publicar.website_url, texto)
        # Va a media portada: después de «Para dormir mejor» y antes de Socios.
        orden = [s.get('class') for s in arbol.xpath('//div[@id="wrap"]//section')]
        cine = next(i for i, c in enumerate(orden) if 'o_dcasa_cine' in c)
        self.assertIn('o_dcasa_rail', orden[cine - 1])
        self.assertIn('o_dcasa_socios_band', orden[cine + 1])

    def test_sin_fotos_suficientes_no_sale_la_seccion_de_cine(self):
        pocas = [{'producto': p, 'nombre': p.name, 'categoria': 'Recámaras'} for p in self.camas][:MINIMO_CINE - 1]
        with patch.object(type(self.website), '_dcasa_cine_fotos', return_value=pocas):
            self.assertIsNone(self.website._dcasa_cine())
            _texto, arbol = self._portada()
        self.assertFalse(arbol.xpath('//section[contains(@class, "o_dcasa_cine")]'))

    # ------------------------------------------------------------------ en Chrome

    @contextlib.contextmanager
    def _chrome(self, ancho, alto, movil=False, reducido=False):
        if comun.websocket is None:
            self.skipTest('websocket-client module is not installed')
        self.browser_size = f'{ancho}x{alto}'
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            self.authenticate(None, None, browser=browser)
            self.cr.flush()
            self.cr.clear()
            browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                'width': ancho, 'height': alto, 'deviceScaleFactor': 2 if movil else 1, 'mobile': movil})
            if movil:
                browser._websocket_request('Emulation.setTouchEmulationEnabled', params={'enabled': True})
            browser._websocket_request('Emulation.setEmulatedMedia', params={
                'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce' if reducido else 'no-preference'}]})
            yield browser

    def _en_chrome(self, codigo, ancho=1440, alto=900, movil=False, reducido=False):
        with self._chrome(ancho, alto, movil, reducido) as browser:
            browser.navigate_to(self.base_url() + '/', wait_stop=True)
            res = browser._websocket_request('Runtime.evaluate', params={
                'expression': PRUEBA_JS % codigo, 'awaitPromise': True, 'returnByValue': True}, timeout=120)
            self.assertFalse(browser.had_failure, 'console.error en la página')
        self.assertFalse(res.get('exceptionDetails'), f'JavaScript falló: {res}')
        return res['result']['value']

    def test_en_la_computadora_las_flechas_las_barras_la_pausa_y_el_avance(self):
        self._elegir(*self.camas)
        r = self._en_chrome(PASOS_COMPUTADORA)
        self.assertTrue(r['controlesVisibles'], 'con JavaScript salen las barras y los botones')
        self.assertEqual(r['alEmpezar'], 0)
        self.assertEqual(r['trasSiguiente'], 1, 'la flecha pasa al siguiente producto')
        self.assertEqual(r['vivo'], 'polite', 'el cambio que pide quien visita se anuncia')
        self.assertEqual(r['barraActual'], 1, 'la barra del producto que se ve')
        self.assertEqual(r['trasAnterior'], 0)
        self.assertEqual(r['trasAnteriorDeNuevo'], 2, 'da la vuelta en la orilla')
        self.assertEqual(r['trasBarra'], 1, 'una barra lleva a su producto')
        self.assertEqual(r['pausa'], {'presionado': 'true', 'etiqueta': 'Reanudar el carrusel', 'clase': True})
        self.assertEqual(r['enPausaSigue'], 1, 'en pausa no avanza')
        self.assertEqual(r['sinPausaAvanza'], 2, 'sin pausa avanza sola')
        self.assertEqual(r['vivoSolo'], 'off', 'lo que avanza solo no interrumpe al lector de pantalla')
        self.assertEqual(r['visibles'], 1, 'se ve una sola diapositiva a la vez')
        self.assertTrue(r['fotoOrillaAOrilla'], 'la foto llega a la orilla derecha y arriba')
        self.assertTrue(r['bloqueNoTapaLaFoto'], 'el bloque azul noche no tapa la foto')
        self.assertTrue(r['altoPantalla'], 'el hero mide al menos el alto de la pantalla')
        self.assertTrue(r['pildoraClara'], 'sobre la foto clara, la píldora va clara')
        self.assertTrue(r['whatsappEspera'], 'el WhatsApp flotante espera fuera mientras se ve el carrusel')
        self.assertTrue(r['nadaEnsancha'], 'nada ensancha la página')
        self.assertEqual(r['cine']['animacion'], 'dcasa-correr')
        self.assertEqual(r['cine']['estado'], 'running')
        self.assertTrue(r['cine']['pausaVisible'])
        self.assertEqual(r['cine']['enPausa'], 'paused', 'el botón detiene las cintas')

    def test_con_movimiento_reducido_nada_se_mueve_solo(self):
        self._elegir(*self.camas)
        r = self._en_chrome(PASOS_REDUCIDO, reducido=True)
        self.assertTrue(r['controlesVisibles'], 'las flechas y las barras siguen ahí')
        self.assertFalse(r['pausaVisible'], 'sin nada que avance, la pausa sobra')
        self.assertEqual(r['trasEsperar'], 0, 'no avanza solo')
        self.assertEqual(r['trasSiguiente'], 1, 'pero la flecha sí cambia de producto')
        self.assertEqual(r['cine']['animacion'], 'none', 'las cintas quietas')
        self.assertFalse(r['cine']['copiasVisibles'], 'sin sus copias repetidas')
        self.assertTrue(r['nadaEnsancha'])

    def test_en_el_telefono_la_foto_arriba_y_se_desliza_con_el_dedo(self):
        self._elegir(*self.camas)
        r = self._en_chrome(PASOS_TELEFONO, ancho=390, alto=844, movil=True)
        self.assertTrue(r['fotoArriba'], 'en el celular la foto va arriba del titular')
        self.assertTrue(r['fotoOrillaAOrilla'], 'de orilla a orilla')
        self.assertTrue(r['bloqueNoTapaLaFoto'], 'y el bloque azul noche debajo, sin taparla')
        self.assertTrue(r['etiquetaDebajoDeLaFoto'],
                        'en el celular la etiqueta va debajo de la foto y antes del bloque azul (portada v2)')
        self.assertTrue(r['etiquetaSobreAzul'],
                        'la etiqueta va sobre el mismo azul noche del bloque: el amarillo nunca toca el blanco')
        self.assertTrue(r['botonVisible'], 'el botón amarillo se ve sin bajar')
        self.assertEqual(r['trasDeslizar'], 1, 'deslizar a la izquierda pasa al siguiente')
        self.assertFalse(r['abrioFicha'], 'deslizar no abre la ficha')
        self.assertEqual(r['trasDeslizarAtras'], 0)
        self.assertTrue(r['nadaEnsancha'])
        self.assertGreaterEqual(r['flechaAncho'], 44, 'botones de 44 px para el dedo')


# El esqueleto de cada prueba en Chrome: espera a que la página esté lista y corre los pasos (%s).
PRUEBA_JS = """(async () => {
    const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
    for (let i = 0; i < 300 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
    await esperar(400);
    const vitrina = document.querySelector('.o_dcasa_vitrina');
    const actual = () => [...vitrina.querySelectorAll('.o_dcasa_vitrina_foto')].findIndex((f) => f.classList.contains('is-activa'));
    const visible = (el) => !!el && !el.hidden && getComputedStyle(el).display !== 'none';
    const [pausa, atras, adelante] = vitrina.querySelectorAll('.o_dcasa_vitrina_boton');
    const foto = vitrina.querySelector('.o_dcasa_vitrina_fotos').getBoundingClientRect();
    const panel = vitrina.querySelector('.o_dcasa_vitrina_panel').getBoundingClientRect();
    const r = {
        controlesVisibles: visible(vitrina.querySelector('.o_dcasa_vitrina_barras')) && visible(adelante),
        // El ancho del DOCUMENTO, no el de la ventana: con la página desplazable, innerWidth incluye la barra de
        // desplazamiento (1440 contra 1425 de documento, medido en Chrome el 2026-11-16) y la foto nunca «llegaría».
        fotoOrillaAOrilla: Math.abs(foto.right - document.documentElement.clientWidth) < 1 && Math.abs(foto.top - vitrina.getBoundingClientRect().top) < 1,
        bloqueNoTapaLaFoto: !(panel.left < foto.right - 1 && panel.right > foto.left + 1 && panel.top < foto.bottom - 1 && panel.bottom > foto.top + 1),
        pildoraClara: !document.documentElement.classList.contains('o_dcasa_nav_sobre_foto'),
        whatsappEspera: document.documentElement.classList.contains('o_dcasa_vitrina_a_la_vista'),
        nadaEnsancha: document.documentElement.scrollWidth <= window.innerWidth,
    };
    const tren = document.querySelector('.o_dcasa_cine_tren');
    if (!tren) { throw new Error('la portada no trae la sección de cine'); }
    r.cine = { animacion: getComputedStyle(tren).animationName, estado: getComputedStyle(tren).animationPlayState,
               pausaVisible: visible(document.querySelector('.o_dcasa_cine_pausa')),
               copiasVisibles: [...document.querySelectorAll('.o_dcasa_cine_foto[aria-hidden]')].some(visible) };
    %s
    return r;
})()"""

PASOS_COMPUTADORA = """
    // Lejos del carrusel: el ratón encima lo detiene.
    r.altoPantalla = vitrina.getBoundingClientRect().height >= window.innerHeight - 1;
    r.alEmpezar = actual();
    adelante.click(); await esperar(100);
    r.trasSiguiente = actual();
    r.vivo = vitrina.querySelector('.o_dcasa_vitrina_textos').getAttribute('aria-live');
    r.barraActual = [...vitrina.querySelectorAll('.o_dcasa_vitrina_barra')].findIndex((b) => b.getAttribute('aria-current') === 'true');
    atras.click(); await esperar(100);
    r.trasAnterior = actual();
    atras.click(); await esperar(100);
    r.trasAnteriorDeNuevo = actual();
    vitrina.querySelectorAll('.o_dcasa_vitrina_barra')[1].click(); await esperar(100);
    r.trasBarra = actual();
    // El botón tiene el foco tras el clic (y el foco también pausa): se suelta para medir solo la pausa del botón.
    pausa.click(); pausa.blur(); await esperar(100);
    r.pausa = { presionado: pausa.getAttribute('aria-pressed'), etiqueta: pausa.getAttribute('aria-label'), clase: vitrina.classList.contains('is-pausada') };
    vitrina.style.setProperty('--vitrina-tiempo', '0.4s');
    await esperar(1000);
    r.enPausaSigue = actual();
    pausa.click(); pausa.blur();
    for (let i = 0; i < 40 && actual() === 1; i++) { await esperar(50); }
    r.sinPausaAvanza = actual();
    r.vivoSolo = vitrina.querySelector('.o_dcasa_vitrina_textos').getAttribute('aria-live');
    pausa.click(); pausa.blur();
    await esperar(1100);   // la anterior se desvanece en 0,9 s
    r.visibles = [...vitrina.querySelectorAll('.o_dcasa_vitrina_foto')].filter((f) => getComputedStyle(f).visibility === 'visible').length;
    const botonCine = document.querySelector('.o_dcasa_cine_pausa');
    botonCine.click(); await esperar(100);
    r.cine.enPausa = getComputedStyle(tren).animationPlayState;
"""

PASOS_REDUCIDO = """
    r.pausaVisible = visible(pausa);
    vitrina.style.setProperty('--vitrina-tiempo', '0.3s');
    await esperar(1200);
    r.trasEsperar = actual();
    adelante.click(); await esperar(100);
    r.trasSiguiente = actual();
"""

PASOS_TELEFONO = """
    const fotos = vitrina.querySelector('.o_dcasa_vitrina_fotos');
    const titular = document.querySelector('.o_dcasa_hero_vitrina h1');
    r.fotoArriba = fotos.getBoundingClientRect().bottom <= titular.getBoundingClientRect().top;
    const etiqueta = vitrina.querySelector('.o_dcasa_vitrina_texto.is-activa').getBoundingClientRect();
    const panelMovil = vitrina.querySelector('.o_dcasa_vitrina_panel').getBoundingClientRect();
    // En el celular la etiqueta va JUSTO DEBAJO de la foto, antes del bloque azul noche (encima taparía la cama).
    r.etiquetaDebajoDeLaFoto = etiqueta.top >= foto.bottom - 1 && etiqueta.bottom <= panelMovil.top + 1
        && etiqueta.right <= document.documentElement.clientWidth;
    // Mismo fondo que el bloque azul noche: el amarillo de «Ver detalles» nunca queda sobre blanco.
    r.etiquetaSobreAzul = getComputedStyle(vitrina.querySelector('.o_dcasa_vitrina_texto.is-activa')).backgroundColor
        === getComputedStyle(vitrina.querySelector('.o_dcasa_vitrina_panel')).backgroundColor;
    const amarillo = document.querySelector('.o_dcasa_hero_vitrina .o_dcasa_btn_amarillo').getBoundingClientRect();
    r.botonVisible = amarillo.top < window.innerHeight;
    r.flechaAncho = adelante.getBoundingClientRect().width;
    vitrina.style.setProperty('--vitrina-tiempo', '600s');
    const caja = fotos.getBoundingClientRect();
    const y = caja.top + caja.height / 2;
    const deslizar = (desde, hasta) => {
        const comun = { bubbles: true, cancelable: true, pointerType: 'touch', isPrimary: true, pointerId: 7 };
        const objetivo = document.elementFromPoint(desde, y);
        objetivo.dispatchEvent(new PointerEvent('pointerdown', { ...comun, clientX: desde, clientY: y }));
        objetivo.dispatchEvent(new PointerEvent('pointerup', { ...comun, clientX: hasta, clientY: y + 4 }));
        return objetivo.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, clientX: hasta, clientY: y }));
    };
    const inicio = location.href;
    const noCancelado = deslizar(caja.left + caja.width * 0.8, caja.left + caja.width * 0.2);
    await esperar(150);
    r.trasDeslizar = actual();
    r.abrioFicha = noCancelado || location.href !== inicio;
    deslizar(caja.left + caja.width * 0.2, caja.left + caja.width * 0.8);
    await esperar(150);
    r.trasDeslizarAtras = actual();
"""
