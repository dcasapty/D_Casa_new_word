"""Lote 1 de la web, medido en Chrome con el teléfono emulado (360, 390 y 430 px).

* La lupa está a la vista junto al carrito, con 44 px de área táctil, sin romper la cabecera (todo en una fila y
  dentro de la pantalla), y abre la misma búsqueda que la computadora.
* La foto de la ficha: la lupa de la foto abre el visor de Odoo; dos dedos acercan y, ya acercada, un dedo la mueve.
"""
import base64
import io

from PIL import Image

from odoo.tests import tagged

from .chrome_movil import ChromeMovilCase

ANCHOS = (360, 390, 430)

CABECERA = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(300);
        const caja = (el) => { if (!el) { return null; } const r = el.getBoundingClientRect();
                               return { x: r.left, y: r.top, ancho: r.width, alto: r.height, derecha: r.right }; };
        const nav = document.querySelector('header#top .o_header_mobile');
        const lupa = nav.querySelector('.o_dcasa_lupa_movil');
        const res = {
            pantalla: innerWidth,
            pagina: document.documentElement.scrollWidth,
            lupa: caja(lupa),
            carrito: caja(nav.querySelector('.o_wsale_my_cart > a')),
            menu: caja(nav.querySelector('button[data-bs-target="#top_menu_collapse_mobile"]')),
            logo: caja(nav.querySelector('.navbar-brand')),
        };
        lupa.click();
        let modal = null;
        for (let i = 0; i < 100 && !(modal = document.querySelector('#o_search_modal.show')); i++) {
            await esperar(50);
        }
        await esperar(400);
        const campo = modal && modal.querySelector('input[name="search"]');
        res.modal = !!modal;
        res.campo = caja(campo);
        res.foco = !!campo && document.activeElement === campo;
        res.destino = modal && modal.querySelector('form').getAttribute('action');
        return res;
    })()
"""

BARRA_TIENDA = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(300);
        const caja = (el) => { if (!el) { return null; } const r = el.getBoundingClientRect();
                               return { x: r.left, y: r.top, ancho: r.width, alto: r.height, derecha: r.right }; };
        const barra = document.querySelector('#o_wsale_products_header .products_header');
        const campo = barra.querySelector('.o_wsale_products_searchbar_form input[name="search"]');
        return {
            pantalla: innerWidth,
            pagina: document.documentElement.scrollWidth,
            barra: caja(barra),
            formulario: caja(barra.querySelector('.o_wsale_products_searchbar_form')),
            campo: caja(campo),
            ayuda: campo.getAttribute('placeholder'),
            orden: caja(barra.querySelector('.o_sortby_dropdown')),
            filtros: caja(barra.querySelector('button[data-bs-target="#o_wsale_offcanvas"]')),
        };
    })()
"""

GESTOS = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(400);
        const boton = document.querySelector('.o_dcasa_ver_grande');
        if (!boton) { return { boton: null }; }
        const r = boton.getBoundingClientRect();
        boton.click();
        let visor = null;
        for (let i = 0; i < 100 && !(visor = document.querySelector('.o_wsale_image_viewer')); i++) {
            await esperar(50);
        }
        if (!visor) { return { boton: [r.width, r.height], visor: false }; }
        await esperar(400);
        const img = visor.querySelector('.o_wsale_image_viewer_image img');
        const dedo = (id, x, y) => new Touch({ identifier: id, target: img, clientX: x, clientY: y });
        const tocar = (tipo, dedos) => img.dispatchEvent(new TouchEvent(tipo, {
            touches: tipo === 'touchend' ? [] : dedos, changedTouches: dedos, bubbles: true, cancelable: true }));
        const escala = () => { const m = /scale3d\\(([\\d.]+)/.exec(img.getAttribute('style') || '');
                               return m ? parseFloat(m[1]) : 1; };
        const antes = escala();
        // Pellizco: los dedos pasan de 100 a 200 px de distancia → el doble.
        tocar('touchstart', [dedo(1, 145, 400), dedo(2, 245, 400)]);
        tocar('touchmove', [dedo(1, 95, 400), dedo(2, 295, 400)]);
        tocar('touchend', [dedo(1, 95, 400), dedo(2, 295, 400)]);
        await esperar(150);
        const pellizco = escala();
        // Ya acercada, un dedo la mueve 40 px a la derecha y 50 px abajo.
        tocar('touchstart', [dedo(1, 200, 400)]);
        tocar('touchmove', [dedo(1, 240, 450)]);
        tocar('touchend', [dedo(1, 240, 450)]);
        await esperar(150);
        const movida = visor.querySelector('.o_wsale_image_viewer_void').getAttribute('style') || '';
        const x = visor.querySelector('.o_wsale_image_viewer_header .fa-times');
        const cerrar = x.getBoundingClientRect();
        const encima = document.elementFromPoint(cerrar.left + cerrar.width / 2, cerrar.top + cerrar.height / 2);
        return { boton: [r.width, r.height], visor: true, antes, pellizco, movida,
                 cerrar: [cerrar.width, cerrar.height], cerrarArriba: encima === x,
                 tactil: getComputedStyle(visor.querySelector('.o_wsale_image_viewer_image')).touchAction };
    })()
"""


def _foto():
    salida = io.BytesIO()
    Image.new('RGB', (1200, 900), (210, 190, 170)).save(salida, 'JPEG')
    return base64.b64encode(salida.getvalue())


@tagged('post_install', '-at_install')
class TestBuscarYFotoEnElCelular(ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mesa = cls.env['product.template'].create({
            'name': 'Mesa de prueba de la foto', 'list_price': 59.99, 'is_published': True, 'image_1920': _foto()})

    def test_lupa_junto_al_carrito_sin_romper_la_cabecera(self):
        for ancho in ANCHOS:
            for ruta in ('/', '/shop'):
                with self.subTest(ancho=ancho, ruta=ruta), self._chrome_movil(ancho) as browser:
                    browser.navigate_to(self.base_url() + ruta, wait_stop=True)
                    self.assertTrue(browser._wait_ready())
                    m = self._evaluar(browser, CABECERA)
                    self.assertLessEqual(m['pagina'], m['pantalla'], 'la cabecera no ensancha la página')
                    for nombre in ('lupa', 'carrito', 'menu', 'logo'):
                        caja = m[nombre]
                        self.assertTrue(caja and caja['ancho'] > 0, f'{nombre} visible')
                        self.assertLessEqual(caja['derecha'], m['pantalla'], f'{nombre} dentro de la pantalla')
                    self.assertGreaterEqual(m['lupa']['ancho'], 44, 'área táctil de 44 px')
                    self.assertGreaterEqual(m['lupa']['alto'], 44, 'área táctil de 44 px')
                    self.assertLess(m['lupa']['x'], m['carrito']['x'], 'la lupa, junto al carrito')
                    self.assertAlmostEqual(m['lupa']['y'] + m['lupa']['alto'] / 2,
                                           m['carrito']['y'] + m['carrito']['alto'] / 2, delta=2,
                                           msg='en la misma fila que el carrito')
                    self.assertLessEqual(m['logo']['derecha'], m['lupa']['x'], 'no pisa el logo')
                    self.assertTrue(m['modal'], 'abre la caja de búsqueda')
                    self.assertGreater(m['campo']['ancho'], ancho * .6, 'el campo se ve entero')
                    self.assertTrue(m['foco'], 'listo para escribir')
                    self.assertEqual(m['destino'], '/shop')

    def test_barra_de_busqueda_de_la_tienda_a_lo_ancho(self):
        """En /shop la caja va sola en su fila (cabe un botón extra, como la cámara) y «Ordenar por» y «Filtros»
        quedan debajo, a la vista."""
        for ancho in ANCHOS:
            with self.subTest(ancho=ancho), self._chrome_movil(ancho) as browser:
                browser.navigate_to(self.base_url() + '/shop?search=mesa', wait_stop=True)
                self.assertTrue(browser._wait_ready())
                m = self._evaluar(browser, BARRA_TIENDA)
                self.assertLessEqual(m['pagina'], m['pantalla'])
                self.assertGreaterEqual(m['formulario']['ancho'], m['barra']['ancho'] - 2, 'la caja, a lo ancho')
                self.assertGreater(m['campo']['ancho'], ancho * .6, 'el campo se lee entero')
                self.assertEqual(m['ayuda'], 'Escribe lo que buscas')
                for nombre in ('orden', 'filtros'):
                    self.assertTrue(m[nombre] and m[nombre]['ancho'] > 0, f'{nombre} visible')
                    self.assertGreaterEqual(m[nombre]['y'], m['formulario']['y'] + m['formulario']['alto'] - 1,
                                            f'{nombre} debajo de la caja')
                    self.assertLessEqual(m[nombre]['derecha'], m['pantalla'])

    def test_foto_en_grande_con_el_dedo(self):
        with self._chrome_movil(390) as browser:
            browser.navigate_to(self.base_url() + self.mesa.website_url, wait_stop=True)
            self.assertTrue(browser._wait_ready())
            m = self._evaluar(browser, GESTOS)
        self.assertTrue(m['boton'], 'la lupa sobre la foto')
        self.assertGreaterEqual(min(m['boton']), 44)
        self.assertTrue(m['visor'], 'la lupa abre el visor')
        self.assertEqual(m['antes'], 1)
        self.assertAlmostEqual(m['pellizco'], 2, delta=.05, msg='dos dedos acercan')
        self.assertIn('translate(40px, 50px)', m['movida'], 'un dedo mueve la foto acercada')
        self.assertGreaterEqual(min(m['cerrar']), 44, 'la X se toca con el dedo')
        self.assertTrue(m['cerrarArriba'], 'la X queda encima de la foto acercada')
        self.assertEqual(m['tactil'], 'none', 'el navegador no se roba el gesto')
