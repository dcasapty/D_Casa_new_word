# ruff: noqa: E501  (JavaScript del navegador embebido en texto)
"""Portada: el hero es UN FONDO EN MOVIMIENTO (la dueña, 2026-11-17: «simplemente quiero la foto detrás, el
texto») y la sección «de cine» (models/portada.py, views/homepage_templates.xml, static/src/js/portada.js).
Lo que se fija aquí:

* El ajuste: «Sitio web › Carrusel de la portada», una lista que se ordena arrastrando; solo Gerencia y los
  administradores la ven y la cambian.
* Vacío = el hero de siempre (también si nada de la lista se puede mostrar: sin publicar o sin foto). Con productos:
  las fotos ocupan la pantalla entera y se funden unas en otras, en orden al azar, con un zoom lento que no para.
  Encima, SOLO el texto de siempre: ni nombres de producto, ni enlaces, ni flechas, ni barras, ni pausa. El visitante
  no maneja nada, así que el bloque es decorativo (aria-hidden, alt vacío). La primera foto es la imagen LCP
  (precargada, «eager», prioridad alta).
* El contraste se resuelve en AZUL DE MARCA, no oscureciendo la foto: un degradado diagonal (navy → azul →
  transparente) que deja el amarillo siempre sobre azul y nunca sobre blanco.
* El carrusel nace UNA vez con las camas que aprobó la dueña (por su código público); lo que no existe se salta.
* Con el editor del sitio abierto (quien tiene el grupo de diseñador recibe las plantillas con sus marcas) la portada
  abre, y un hero guardado con el editor sigue dentro de su condición.
* La sección «de cine»: dos cintas con fotos del catálogo publicado (sin repetir los carriles de arriba) y el botón al
  catálogo; sin fotos suficientes no sale.
* En Chrome: la foto de orilla a orilla y del alto de la pantalla, el zoom corriendo, el cambio solo de foto (y quieto
  con movimiento reducido), que no haya NADA que tocar, la píldora clara y que nada ensanche la página.
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


def _id_del_src(src):
    """El id del producto dentro de la URL de su foto (/web/image/product.template/<id>/image_1024/...)."""
    return int(src.split('/image_')[0].rsplit('/', 1)[-1])


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

    def test_con_productos_el_fondo_son_las_fotos_y_encima_solo_el_texto(self):
        """El hero es un fondo: una foto por producto, en el orden del panel, y encima el texto de siempre.

        Nada que el visitante pueda tocar (la dueña, 2026-11-17: «no quiero ni siquiera que el usuario tenga control
        de este carrusel», «ni siquiera tiene que tener el nombre del producto»): ni enlaces, ni nombres, ni flechas,
        ni barras, ni pausa. Por eso la pila de fotos es decorativa y el lector de pantalla no la lee.
        """
        orden = [self.camas[2], self.camas[0], self.camas[1]]
        self._elegir(orden[0], self.sin_publicar, orden[1], self.sin_foto, orden[2])
        texto, arbol = self._portada()
        vitrina = self._vitrina(arbol)
        self.assertIsNotNone(vitrina, 'con productos elegidos, el hero es el fondo en movimiento')
        self.assertFalse(arbol.xpath('//div[@id="oe_structure_dcasa_hero"]'), 'y no el de siempre')
        self.assertNotIn('/website_dcasa/static/src/img/hero.webp', texto)
        self.assertEqual(len(arbol.xpath('//h1')), 1, 'un solo titular en la página')
        self.assertEqual(' '.join(vitrina.xpath('.//h1')[0].text_content().split()), 'Tu casa, bien amueblada.')
        self.assertEqual(vitrina.xpath('.//a[contains(@class, "o_dcasa_btn_amarillo")]/@href'), ['/shop'])

        pila = vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_fotos")]')[0]
        self.assertEqual(pila.get('aria-hidden'), 'true', 'el fondo es decorativo: no se lee')
        fotos = pila.xpath('./div[contains(@class, "o_dcasa_vitrina_foto")]')
        self.assertEqual(len(fotos), len(orden),
                         'una foto por producto que se puede mostrar, sin el sin publicar ni el que no tiene foto')
        self.assertEqual([f.get('style') for f in fotos], ['--i: 0;', '--i: 1;', '--i: 2;'],
                         'cada foto arranca en un punto distinto del zoom')
        imagenes = [f.xpath('.//img')[0] for f in fotos]
        self.assertEqual([img.get('alt') for img in imagenes], [''] * len(orden),
                         'alt vacío: el nombre del producto no sale ni para el lector de pantalla')
        primera, *demas = imagenes
        self.assertEqual((primera.get('loading'), primera.get('fetchpriority')), ('eager', 'high'), 'la imagen LCP')
        self.assertTrue(all(img.get('loading') == 'lazy' for img in demas))
        self.assertIn('is-activa', _clases(fotos[0]))
        self.assertFalse(any('is-activa' in _clases(f) for f in fotos[1:]), 'sin JavaScript se ve la primera')
        # La foto grande: WebP del ancho justo (hasta 1600 px) y, de respaldo, la de Odoo a 1920.
        fuente = fotos[0].xpath('.//source[@type="image/webp"]')[0].get('srcset')
        self.assertIn(f'/dcasa/img/product.template/{orden[0].id}/image_1920/1600.webp', fuente)
        self.assertIn('image_1920', primera.get('srcset'))

        # Nada que manejar: ni mandos, ni enlaces, ni nombres, ni el papel de «carrusel».
        self.assertFalse(vitrina.xpath('.//*[contains(@class, "o_dcasa_vitrina_barra")]'), 'sin barras')
        self.assertFalse(vitrina.xpath('.//*[contains(@class, "o_dcasa_vitrina_boton")]'), 'sin flechas ni pausa')
        self.assertFalse(vitrina.xpath('.//*[contains(@class, "o_dcasa_vitrina_nombre")]'), 'sin nombres')
        self.assertFalse(vitrina.xpath('.//*[contains(@class, "o_dcasa_vitrina_ver")]'), 'sin «Ver detalles»')
        self.assertFalse(pila.xpath('.//a'), 'el fondo no lleva a ninguna ficha')
        self.assertFalse(pila.xpath('.//button'))
        self.assertFalse(vitrina.xpath('.//*[@role="group"] | .//*[@aria-roledescription] | .//*[@aria-live]'),
                         'no es un carrusel que se recorra: no se anuncia como tal')
        en_el_hero = lhtml.tostring(vitrina, encoding='unicode')
        for producto in orden:
            self.assertNotIn(producto._dcasa_nombre_cliente(), en_el_hero,
                             'el nombre del producto no sale en el hero (en los carriles de abajo sí: son tarjetas)')

        # El texto va aparte de la pila de fotos, en su propio bloque encima.
        panel = vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_panel")]')[0]
        self.assertTrue(panel.xpath('.//h1'), 'el titular va en el bloque de encima')
        self.assertFalse(panel.xpath('.//img'), 'y ninguna foto dentro del bloque del texto')

        precarga = arbol.xpath('//head/link[@rel="preload"][@as="image"]')
        self.assertEqual(len(precarga), 1, 'se precarga solo la primera foto del fondo')
        self.assertEqual(precarga[0].get('imagesrcset'), fuente)
        self.assertEqual(precarga[0].get('fetchpriority'), 'high')

    def test_el_amarillo_nunca_toca_el_blanco(self):
        """El amarillo del hero cae sobre el degradado azul de marca; el de la sección de cine (blanca) es azul."""
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

    def test_un_solo_producto_una_foto_quieta(self):
        """Con un solo producto el fondo es esa foto, con su zoom lento; no hay nada más que enseñar."""
        self._elegir(self.camas[1])
        _texto, arbol = self._portada()
        vitrina = self._vitrina(arbol)
        self.assertEqual(len(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_fotos")]/div')), 1)
        self.assertFalse(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_barras")]'))
        self.assertFalse(vitrina.xpath('.//div[contains(@class, "o_dcasa_vitrina_botones")]'))

    def test_el_cambio_se_ve_al_momento(self):
        """Odoo guarda la portada de los visitantes hasta una hora: el carrusel va en la clave de esa memoria."""
        self.Diapositiva.search([]).unlink()
        self.assertIsNone(self._vitrina(self._portada()[1]))
        self._elegir(self.camas[0], self.camas[1])
        self.assertIsNotNone(self._vitrina(self._portada()[1]), 'elegir productos se ve sin esperar')
        self._elegir(self.camas[1], self.camas[0])
        fotos = self._vitrina(self._portada()[1]).xpath(
            './/div[contains(@class, "o_dcasa_vitrina_fotos")]/div//img/@src')
        self.assertEqual([_id_del_src(f) for f in fotos], [self.camas[1].id, self.camas[0].id], 'reordenar, también')
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
                self.assertEqual(len(arbol.xpath('//div[contains(@class, "o_dcasa_vitrina_fotos")]/div')), 3)

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
        fotos = self._vitrina(self._portada()[1]).xpath(
            './/div[contains(@class, "o_dcasa_vitrina_fotos")]/div//img/@src')
        self.assertEqual([_id_del_src(f) for f in fotos], [black.id, beige.id, ivory.id])
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

    def test_en_la_computadora_el_fondo_cubre_la_pantalla_y_cambia_solo(self):
        self._elegir(*self.camas)
        r = self._en_chrome(PASOS_COMPUTADORA)
        self.assertTrue(r['fotoOrillaAOrilla'], 'la foto llega a las dos orillas y a arriba')
        self.assertTrue(r['altoPantalla'], 'el hero mide al menos el alto de la pantalla')
        self.assertTrue(r['textoEncimaDeLaFoto'], 'el texto va ENCIMA de la foto, no a su lado')
        self.assertEqual(r['zoom'], 'dcasa-vitrina-zoom', 'el zoom lento corre')
        self.assertEqual(r['zoomEstado'], 'running', 'y no para nunca')
        self.assertEqual(r['alEmpezar'], 0, 'se ve la primera, la que el navegador precargó')
        self.assertNotEqual(r['trasEsperar'], 0, 'la foto cambia sola')
        self.assertEqual(r['visibles'], 1, 'se ve una sola foto a la vez')
        self.assertTrue(r['capaAzul'], 'el contraste se resuelve en azul de marca, no oscureciendo la foto')
        self.assertEqual(r['nadaQueTocar'], 0, 'no hay flechas, barras, pausa ni enlaces: es un fondo')
        self.assertTrue(r['pildoraClara'], 'sobre la foto clara, la píldora va clara')
        self.assertTrue(r['whatsappEspera'], 'el WhatsApp flotante espera fuera mientras se ve el hero')
        self.assertTrue(r['nadaEnsancha'], 'nada ensancha la página')
        self.assertEqual(r['cine']['animacion'], 'dcasa-correr')
        self.assertEqual(r['cine']['estado'], 'running')
        self.assertTrue(r['cine']['pausaVisible'])
        self.assertEqual(r['cine']['enPausa'], 'paused', 'el botón detiene las cintas')

    def test_con_movimiento_reducido_nada_se_mueve_solo(self):
        self._elegir(*self.camas)
        r = self._en_chrome(PASOS_REDUCIDO, reducido=True)
        self.assertEqual(r['trasEsperar'], 0, 'la foto no cambia sola')
        self.assertEqual(r['zoom'], 'none', 'y el zoom tampoco se mueve')
        self.assertTrue(r['fotoOrillaAOrilla'], 'pero la foto sigue cubriendo la pantalla')
        self.assertEqual(r['nadaQueTocar'], 0, 'sigue sin nada que manejar')
        self.assertEqual(r['cine']['animacion'], 'none', 'las cintas quietas')
        self.assertFalse(r['cine']['copiasVisibles'], 'sin sus copias repetidas')
        self.assertTrue(r['nadaEnsancha'])

    def test_en_el_telefono_la_foto_cubre_la_pantalla_y_el_texto_va_encima(self):
        self._elegir(*self.camas)
        r = self._en_chrome(PASOS_TELEFONO, ancho=390, alto=844, movil=True)
        self.assertTrue(r['fotoOrillaAOrilla'], 'de orilla a orilla')
        self.assertTrue(r['altoPantalla'], 'y del alto de la pantalla')
        self.assertTrue(r['textoEncimaDeLaFoto'], 'el texto va encima de la foto')
        self.assertTrue(r['capaAzul'], 'el azul sube desde el pie para que el texto se lea')
        self.assertTrue(r['botonVisible'], 'el botón amarillo se ve sin bajar')
        self.assertEqual(r['nadaQueTocar'], 0, 'tampoco en el celular hay nada que manejar')
        self.assertFalse(r['deslizarCambia'], 'deslizar no cambia la foto: no es un carrusel')
        self.assertFalse(r['abrioFicha'], 'ni abre ninguna ficha')
        self.assertTrue(r['nadaEnsancha'])


# El esqueleto de cada prueba en Chrome: espera a que la página esté lista y corre los pasos (%s).
PRUEBA_JS = r"""(async () => {
    const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
    for (let i = 0; i < 300 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
    await esperar(400);
    const vitrina = document.querySelector('.o_dcasa_vitrina');
    const fotos = () => [...vitrina.querySelectorAll('.o_dcasa_vitrina_foto')];
    const actual = () => fotos().findIndex((f) => f.classList.contains('is-activa'));
    const visible = (el) => !!el && !el.hidden && getComputedStyle(el).display !== 'none';
    const pila = vitrina.querySelector('.o_dcasa_vitrina_fotos');
    const foto = pila.getBoundingClientRect();
    const panel = vitrina.querySelector('.o_dcasa_vitrina_panel').getBoundingClientRect();
    const primera = fotos()[0].querySelector('img');
    const capa = getComputedStyle(vitrina, '::after');
    const r = {
        // El ancho del DOCUMENTO, no el de la ventana: con la página desplazable, innerWidth incluye la barra de
        // desplazamiento (1440 contra 1425 de documento, medido en Chrome el 2026-11-16) y la foto nunca «llegaría».
        fotoOrillaAOrilla: Math.abs(foto.left) < 1
            && Math.abs(foto.right - document.documentElement.clientWidth) < 1
            && Math.abs(foto.top - vitrina.getBoundingClientRect().top) < 1,
        altoPantalla: vitrina.getBoundingClientRect().height >= window.innerHeight - 1,
        // Lo contrario de antes: el texto YA NO va al lado de la foto, va encima (el hero es un fondo).
        textoEncimaDeLaFoto: panel.left < foto.right - 1 && panel.right > foto.left + 1
            && panel.top < foto.bottom - 1 && panel.bottom > foto.top + 1,
        zoom: getComputedStyle(primera).animationName,
        zoomEstado: getComputedStyle(primera).animationPlayState,
        // El contraste es azul de marca (#1340B1 / #0E2A6B), nunca negro: un degradado, no un velo oscuro.
        capaAzul: capa.backgroundImage.includes('gradient')
            && /rgba?\((?:14, 42, 107|19, 64, 177)/.test(capa.backgroundImage)
            && !/rgba?\(0, 0, 0/.test(capa.backgroundImage),
        // Ni un solo mando ni enlace dentro del hero: no se maneja.
        nadaQueTocar: vitrina.querySelectorAll('a, button, [role="group"], [aria-live], .o_dcasa_vitrina_barra,'
            + ' .o_dcasa_vitrina_boton, .o_dcasa_vitrina_nombre').length
            - vitrina.querySelectorAll('.o_dcasa_vitrina_panel a, .o_dcasa_vitrina_panel button').length,
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

# El primer cambio ya está programado desde que carga la página, con el tiempo de verdad ($dcasa-vitrina-tiempo,
# 6,5 s): acortar --vitrina-tiempo aquí solo vale de la segunda vez en adelante. Por eso se espera hasta ESPERA_FONDO.
PASOS_COMPUTADORA = """
    r.alEmpezar = actual();
    vitrina.style.setProperty('--vitrina-tiempo', '0.4s');
    for (let i = 0; i < 240 && actual() === r.alEmpezar; i++) { await esperar(50); }
    r.trasEsperar = actual();
    // Para contar cuántas se ven hay que dejar de cambiar: con 0,4 s entre fotos y 1,8 s de fundido siempre
    // habría dos a medio camino. Se alarga el tiempo, se deja terminar el fundido y recién ahí se cuenta.
    vitrina.style.setProperty('--vitrina-tiempo', '600s');
    await esperar(2500);
    r.visibles = fotos().filter((f) => parseFloat(getComputedStyle(f).opacity) > 0.01).length;
    const botonCine = document.querySelector('.o_dcasa_cine_pausa');
    botonCine.click(); await esperar(100);
    r.cine.enPausa = getComputedStyle(tren).animationPlayState;
"""

# Se espera MÁS que el tiempo de verdad de una diapositiva (6,5 s): si con movimiento reducido se hubiera
# programado el cambio, aquí ya habría pasado.
PASOS_REDUCIDO = """
    await esperar(9000);
    r.trasEsperar = actual();
"""

PASOS_TELEFONO = """
    const amarillo = document.querySelector('.o_dcasa_hero_vitrina .o_dcasa_btn_amarillo').getBoundingClientRect();
    r.botonVisible = amarillo.top < window.innerHeight;
    // Que nadie se quede «arrastrando» el fondo esperando que pase algo: deslizar no cambia la foto ni abre nada.
    vitrina.style.setProperty('--vitrina-tiempo', '600s');
    const antes = actual();
    const caja = pila.getBoundingClientRect();
    const y = caja.top + caja.height / 2;
    const deslizar = (desde, hasta) => {
        const comun = { bubbles: true, cancelable: true, pointerType: 'touch', isPrimary: true, pointerId: 7 };
        const objetivo = document.elementFromPoint(desde, y);
        objetivo.dispatchEvent(new PointerEvent('pointerdown', { ...comun, clientX: desde, clientY: y }));
        objetivo.dispatchEvent(new PointerEvent('pointerup', { ...comun, clientX: hasta, clientY: y + 4 }));
        return objetivo.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, clientX: hasta, clientY: y }));
    };
    const inicio = location.href;
    deslizar(caja.left + caja.width * 0.8, caja.left + caja.width * 0.2);
    await esperar(300);
    r.deslizarCambia = actual() !== antes;
    r.abrioFicha = location.href !== inicio;
"""
