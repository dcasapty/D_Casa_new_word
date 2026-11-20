"""Lote «legibilidad» del sitio (de la comparación con Feuxui, ``docs/referencias/feuxui/``). Cada arreglo mide en
Chrome, con el teléfono emulado, lo que la persona ve:

* Arreglo 3: las marcas de relleno (placeholder) del buscador del catálogo y de Socios y los pasos del carrito que aún
  no tocan se leen con 4,5:1 o más (antes 2,86, 3,12 y 2,38:1).
* Arreglo 4: en el celular, lo que se toca con el dedo mide 44 px o más (antes de 32 a 40 px).
* Arreglo 5: el buscador del catálogo dice qué busca (aria-label), su botón dice «Buscar» y su texto de ayuda es corto y
  no se corta en el cajón del celular. (La pista visible de la cámara es de dcasa_buscar_foto y se prueba allá.)
* Arreglo 6: «Enviar mensaje» del contacto, a todo el ancho y de 48 px o más, como el formulario de /socios.
"""
import json
import re

from odoo.tests import HttpCase, tagged

from .chrome_movil import ChromeMovilCase
from .contraste import razon_del_texto, sonda

MINIMO = 4.5     # texto normal (WCAG 1.4.3)

# Espera a que el sitio esté listo (el buscador y los pasos se pintan con el JavaScript de Odoo).
LISTO = """
    (async () => {
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) {
            await new Promise((ok) => setTimeout(ok, 50));
        }
        await new Promise((ok) => setTimeout(ok, 400));
        return true;
    })()
"""


@tagged('post_install', '-at_install')
class TestLegibilidadColor(ChromeMovilCase):
    """Arreglo 3: placeholders con el gris de la marca y pasos del carrito legibles."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        recamaras = cls.env.ref('website_dcasa.public_category_recamaras')
        cls.producto = cls.env['product.template'].create({
            'name': 'Cama del test de legibilidad', 'list_price': 129.99, 'is_published': True,
            'public_categ_ids': [(6, 0, recamaras.ids)],
        })

    def _abrir(self, browser, ruta):
        browser.navigate_to(self.base_url() + ruta, wait_stop=True)
        self.assertTrue(browser._wait_ready(), f'{ruta} no terminó de cargar')
        self._evaluar(browser, LISTO)

    def _medir(self, browser, selector, pseudo=None):
        medida = self._evaluar(browser, sonda(selector, pseudo))
        self.assertTrue(medida, f'no se encontró {selector}')
        return medida

    def test_placeholder_del_buscador_y_de_socios_con_el_gris_de_la_marca(self):
        for ancho in (390, 1440):
            with self._chrome_movil(ancho) as browser:
                for ruta, selector in (('/shop', '.o_wsale_products_searchbar_form input.oe_search_box'),
                                       ('/socios', '.o_dcasa_socios_form #celular')):
                    with self.subTest(ruta=ruta, ancho=ancho):
                        self._abrir(browser, ruta)
                        medida = self._medir(browser, selector, '::placeholder')
                        self.assertEqual(medida['color'], 'rgb(74, 81, 99)', 'el gris de la marca (#4A5163)')
                        self.assertEqual(medida['opacidad'], 1, 'sin la opacidad que Odoo le baja al placeholder')
                        razon = razon_del_texto(medida)
                        self.assertGreaterEqual(razon, MINIMO, f'placeholder de {ruta}: {razon:.2f}:1 sobre '
                                                f'{medida["fondo"]}')

    def test_pasos_del_carrito_que_aun_no_tocan_se_leen(self):
        with self._chrome_movil(390) as browser:
            self._abrir(browser, '/shop')
            agregado = self._evaluar(browser, f"""
                fetch('/shop/cart/add', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{jsonrpc: '2.0', method: 'call', params: {{
                        product_template_id: {self.producto.id},
                        product_id: {self.producto.product_variant_id.id}, quantity: 1}}}})
                }}).then((r) => r.json()).then((j) => !j.error)
            """)
            self.assertTrue(agregado, 'la cama entró al carrito')
            self._abrir(browser, '/shop/cart')
            # El paso actual («Orden») y los que faltan («Dirección», «Pago»): los que faltan son .o_disabled.
            pasos = self._evaluar(browser, "document.querySelectorAll('.o_wizard .o_disabled').length")
            self.assertGreaterEqual(pasos, 1, 'el carrito muestra los pasos que aún no tocan')
            medida = self._medir(browser, '.o_wizard .o_disabled [name="step_name"]')
            self.assertEqual(medida['opacidad'], 1, 'Odoo los dejaba al 50 % de opacidad')
            razon = razon_del_texto(medida)
            self.assertGreaterEqual(razon, MINIMO, f'pasos del carrito: {razon:.2f}:1 sobre {medida["fondo"]}')
            json.dumps(medida)


# Mide cada selector (los visibles) y devuelve [selector, ancho, alto] de cada uno.
TAMANOS = """
    ((selectores) => selectores.flatMap((sel) => [...document.querySelectorAll(sel)].map((e) => {
        const r = e.getBoundingClientRect();
        return [sel, r.width, r.height];
    }).filter(([, w, h]) => w > 0 && h > 0)))
"""
ZONA_TACTIL = 44     # px (guía de Apple y WCAG 2.5.5)


@tagged('post_install', '-at_install')
class TestLegibilidadZonasTactiles(ChromeMovilCase):
    """Arreglo 4: en el celular (puntero táctil) ninguno de estos controles mide menos de 44 px por lado."""

    def _abrir(self, browser, ruta):
        browser.navigate_to(self.base_url() + ruta, wait_stop=True)
        self.assertTrue(browser._wait_ready(), f'{ruta} no terminó de cargar')
        self._evaluar(browser, LISTO)

    def _revisar(self, browser, donde, selectores):
        medidas = self._evaluar(browser, f'{TAMANOS}({json.dumps(selectores)})')
        encontrados = {m[0] for m in medidas}
        self.assertEqual(set(selectores) - encontrados, set(), f'{donde}: no se encontró alguno de los controles')
        for selector, ancho, alto in medidas:
            self.assertGreaterEqual(ancho, ZONA_TACTIL - .1, f'{donde}: {selector} mide {ancho:.1f} px de ancho')
            self.assertGreaterEqual(alto, ZONA_TACTIL - .1, f'{donde}: {selector} mide {alto:.1f} px de alto')

    def test_controles_de_la_tienda_el_cajon_los_filtros_y_el_contacto_miden_44(self):
        with self._chrome_movil(390) as browser:
            self.assertTrue(self._evaluar(browser, "matchMedia('(pointer: coarse)').matches"),
                            'el teléfono emulado tiene puntero táctil')
            self._abrir(browser, '/shop')
            self._revisar(browser, 'cabecera y barra de la tienda', [
                'header#top [data-bs-target="#top_menu_collapse_mobile"]',    # hamburguesa
                '.o_sortby_dropdown .dropdown-toggle',                         # «Ordenar por»
                '[data-bs-target="#o_wsale_offcanvas"]'])                      # «Filtros»
            # El cajón del menú: la X y «Mi cuenta».
            self._evaluar(browser, """(async () => {
                document.querySelector('header#top [data-bs-target="#top_menu_collapse_mobile"]').click();
                for (let i = 0; i < 60 && !document.querySelector('#top_menu_collapse_mobile.show'); i++) {
                    await new Promise((ok) => setTimeout(ok, 50));
                }
                await new Promise((ok) => setTimeout(ok, 500));
            })()""")
            self._revisar(browser, 'cajón del menú', [
                '#top_menu_collapse_mobile .btn-close', '#top_menu_collapse_mobile .o_nav_link_btn'])
            # El cajón de los filtros: la X y «Eliminar filtros».
            self._abrir(browser, '/shop')
            self._evaluar(browser, """(async () => {
                document.querySelector('[data-bs-target="#o_wsale_offcanvas"]').click();
                for (let i = 0; i < 60 && !document.querySelector('#o_wsale_offcanvas.show'); i++) {
                    await new Promise((ok) => setTimeout(ok, 50));
                }
                await new Promise((ok) => setTimeout(ok, 500));
            })()""")
            self._revisar(browser, 'cajón de los filtros', [
                '#o_wsale_offcanvas .btn-close', '#o_wsale_offcanvas .offcanvas-body a.btn.d-flex'])
            # El contacto: los campos (de una línea) y «Enviar».
            self._abrir(browser, '/contactus')
            self._revisar(browser, 'contacto', [
                '#contactus_form input.s_website_form_input:not([type=hidden])',
                '#contactus_form .s_website_form_send'])


PLACEHOLDER = 'Busca un mueble'


@tagged('post_install', '-at_install')
class TestLegibilidadBuscador(HttpCase):
    """Arreglo 5, por HTTP: lo que el lector de pantalla y el navegador reciben de cada caja de búsqueda."""

    def _cajas(self, ruta):
        html = self.url_open(ruta).text
        cajas = re.findall(r'<input[^>]*type="search"[^>]*>', html)
        botones = re.findall(r'<button[^>]*oe_search_button[^>]*>', html)
        self.assertGreaterEqual(len(cajas), 2, f'{ruta}: la cabecera y la tienda traen caja de búsqueda')
        return cajas, botones

    def test_el_campo_dice_que_busca_y_el_boton_dice_buscar(self):
        for ruta in ('/', '/shop'):
            with self.subTest(ruta=ruta):
                cajas, botones = self._cajas(ruta)
                for caja in cajas:
                    self.assertIn('aria-label="Buscar en el catálogo"', caja,
                                  'el campo se llamaba solo por su placeholder')
                    ayuda = re.search(r'placeholder="([^"]*)"', caja).group(1)
                    self.assertLessEqual(len(ayuda), 16, f'texto de ayuda largo: «{ayuda}»')
                propias = [c for c in cajas if f'placeholder="{PLACEHOLDER}"' in c]
                self.assertGreaterEqual(len(propias), 2, 'la cabecera y la barra de la tienda dicen «Busca un mueble»')
                for boton in botones:
                    self.assertIn('aria-label="Buscar"', boton, 'el botón era «Búsqueda», un sustantivo')
                    self.assertIn('title="Buscar"', boton)
                    self.assertNotIn('Búsqueda', boton)

    def test_el_texto_de_ayuda_es_corto(self):
        # Cabe en el campo del cajón del celular (≈ 100 px de texto): unas 16 letras como mucho.
        self.assertLessEqual(len(PLACEHOLDER), 16)


@tagged('post_install', '-at_install')
class TestLegibilidadBuscadorMovil(ChromeMovilCase):
    """Arreglo 5, en Chrome con el teléfono emulado: el texto de ayuda cabe entero en el cajón del menú."""

    MEDIR_PLACEHOLDER = """
        (async () => {
            const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
            for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) {
                await esperar(50);
            }
            document.querySelector('header#top [data-bs-target="#top_menu_collapse_mobile"]').click();
            for (let i = 0; i < 60 && !document.querySelector('#top_menu_collapse_mobile.show'); i++) {
                await esperar(50);
            }
            await esperar(500);
            const campo = document.querySelector('#top_menu_collapse_mobile input.oe_search_box');
            const cs = getComputedStyle(campo);
            const lienzo = document.createElement('canvas').getContext('2d');
            lienzo.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
            const texto = lienzo.measureText(campo.placeholder).width;
            const util = campo.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            return { placeholder: campo.placeholder, texto, util, etiqueta: campo.getAttribute('aria-label') };
        })()
    """

    def test_el_texto_de_ayuda_no_se_corta_en_el_cajon(self):
        for ancho in (360, 390):
            with self.subTest(ancho=ancho), self._chrome_movil(ancho) as browser:
                browser.navigate_to(self.base_url() + '/shop', wait_stop=True)
                self.assertTrue(browser._wait_ready())
                medida = self._evaluar(browser, self.MEDIR_PLACEHOLDER)
                self.assertEqual(medida['placeholder'], PLACEHOLDER)
                self.assertLessEqual(medida['texto'], medida['util'], f'se cortaría: {medida}')
                self.assertEqual(medida['etiqueta'], 'Buscar en el catálogo')


@tagged('post_install', '-at_install')
class TestLegibilidadContacto(ChromeMovilCase):
    """Arreglo 6: «Enviar mensaje» a todo el ancho y de 48 px o más, como «Entrar» de /socios."""

    MEDIR_ENVIAR = """
        (async () => {
            for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) {
                await new Promise((ok) => setTimeout(ok, 50));
            }
            const boton = document.querySelector('#contactus_form .s_website_form_send');
            const filas = document.querySelector('#contactus_form .s_website_form_rows');
            const campo = document.querySelector('#contactus_form input#contact5');   // «Asunto»: de ancho completo
            const b = boton.getBoundingClientRect(), f = filas.getBoundingClientRect();
            const c = campo.getBoundingClientRect();
            return { texto: boton.textContent.trim(), ancho: b.width, alto: b.height, filas: f.width, campo: c.width,
                     izquierda: b.left - c.left, derecha: c.right - b.right };
        })()
    """

    def test_enviar_mensaje_a_todo_el_ancho(self):
        for ancho in (390, 1440):
            with self.subTest(ancho=ancho), self._chrome_movil(ancho) as browser:
                browser.navigate_to(self.base_url() + '/contactus', wait_stop=True)
                self.assertTrue(browser._wait_ready())
                m = self._evaluar(browser, self.MEDIR_ENVIAR)
                self.assertEqual(m['texto'], 'Enviar mensaje', 'el botón dice qué va a pasar')
                self.assertGreaterEqual(m['alto'], 47.9, 'mínimo 48 px')
                self.assertAlmostEqual(m['izquierda'], 0, delta=1, msg='empieza donde empiezan los campos')
                self.assertAlmostEqual(m['derecha'], 0, delta=1, msg='y termina donde terminan los campos')
                self.assertAlmostEqual(m['ancho'], m['campo'], delta=1)
