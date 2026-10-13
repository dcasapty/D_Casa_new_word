"""Celular: la página nunca se sale del ancho de la pantalla (pedido de la dueña: «en el teléfono solo se
desliza hacia abajo; de lado, nada más los carriles; y que no se haga zoom»).

Se mide en Chrome con el teléfono emulado (viewport «móvil»: ahí el navegador ensancha el viewport de
diseño si algo se sale, que es lo que se vive en el iPhone como «zoom» y arrastre lateral), mientras se
baja, se sube y se vuelve al inicio como lo haría una persona:

* ``scrollWidth`` nunca pasa del ancho de la pantalla (lo atrapa, por ejemplo, un texto de lector de
  pantalla de un botón de un carril que escapaba del carril).
* ``innerWidth`` nunca cambia (lo atrapa el menú del celular, que al volver arriba ensanchaba la página
  ~0,4 s). El menú cerrado no se dibuja (display: none).
* Los campos de formulario tienen 16 px o más (menos y el iPhone acerca la pantalla al tocarlos) y el
  doble toque no hace zoom (touch-action: manipulation).
"""
from odoo.addons.website_dcasa.models.black_weekend import PARAM_ACTIVO, PARAM_FIN, PARAM_INICIO
from odoo.tests import tagged

from .chrome_movil import ChromeMovilCase

ANCHOS = (360, 390)

# Baja de a 400 px, sube de a 700 px y vuelve al inicio muestreando cada 100 ms durante 1,5 s (el menú
# ensanchaba la página justo ahí). Devuelve las muestras ``[etiqueta, innerWidth, clientWidth, scrollWidth]``.
RECORRER = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        const muestras = [];
        const mira = (etiqueta) => muestras.push([etiqueta, innerWidth, document.documentElement.clientWidth,
                                                  document.documentElement.scrollWidth]);
        for (let i = 0; i < 100 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(300);
        mira('carga');
        const alto = document.body.scrollHeight;
        for (let y = 0; y < alto; y += 400) { window.scrollTo(0, y); await esperar(40); mira('y=' + y); }
        for (let y = alto; y > 0; y -= 700) { window.scrollTo(0, y); await esperar(40); mira('sube y=' + y); }
        window.scrollTo(0, 0);
        for (let t = 1; t <= 15; t++) { await esperar(100); mira('arriba+' + t * 100 + 'ms'); }
        return muestras;
    })()
"""

# Estado del menú del celular, de los campos de formulario y del doble toque.
ESTADO = """
    (() => {
        const menu = document.querySelector('#top_menu_collapse_mobile');
        const campos = [...document.querySelectorAll(
            'input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=range]), select, textarea')]
            .filter((el) => el.getBoundingClientRect().width > 0)
            .map((el) => [el.tagName.toLowerCase() + '[' + (el.type || '') + ']' + (el.name || el.id || ''),
                          parseFloat(getComputedStyle(el).fontSize)]);
        return {
            menu: menu ? { display: getComputedStyle(menu).display, clases: menu.className } : null,
            camposChicos: campos.filter(([, px]) => px < 16),
            camposTotal: campos.length,
            toque: getComputedStyle(document.documentElement).touchAction,
        };
    })()
"""


@tagged('post_install', '-at_install')
class TestMovilSinDesborde(ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        param = cls.env['ir.config_parameter'].sudo()
        param.set_param(PARAM_ACTIVO, '1')       # la banda Black Weekend de la portada es la que desbordaba
        param.set_param(PARAM_INICIO, '')
        param.set_param(PARAM_FIN, '')
        recamaras = cls.env.ref('website_dcasa.public_category_recamaras')
        cls.productos = cls.env['product.template']
        for n in range(1, 5):
            cls.productos |= cls.env['product.template'].create({
                'name': f'Cama del test móvil {n}', 'list_price': 99.99 + n, 'is_published': True,
                'public_categ_ids': [(6, 0, recamaras.ids)], 'dcasa_black_weekend': True})
        cls.paginas = {'portada': '/', 'tienda': '/shop', 'black-weekend': '/black-weekend',
                       'ficha': cls.productos[0].website_url}

    def _recorrer(self, ancho, ruta):
        with self._chrome_movil(ancho) as browser:
            browser.navigate_to(self.base_url() + ruta, wait_stop=True)
            self.assertTrue(browser._wait_ready(), f'{ruta} no terminó de cargar')
            return self._evaluar(browser, RECORRER), self._evaluar(browser, ESTADO)

    def test_ninguna_pagina_se_sale_del_ancho_ni_se_ensancha_al_subir(self):
        for ancho in ANCHOS:
            for nombre, ruta in self.paginas.items():
                with self.subTest(pagina=nombre, ancho=ancho):
                    muestras, estado = self._recorrer(ancho, ruta)
                    self.assertGreater(len(muestras), 15, 'la página se recorrió entera')
                    for etiqueta, interno, cliente, desplazable in muestras:
                        self.assertEqual(cliente, ancho, f'{etiqueta}: el ancho de la pantalla cambió')
                        self.assertEqual(
                            interno, cliente,
                            f'{etiqueta}: el navegador ensanchó la página a {interno}px (se vería como zoom)')
                        self.assertLessEqual(
                            desplazable, cliente + 1,
                            f'{etiqueta}: la página mide {desplazable}px y la pantalla {cliente}px '
                            '(se arrastraría de lado)')
                    self.assertEqual(
                        estado['menu']['display'], 'none',
                        f'el menú del celular cerrado no puede estar dibujado ({estado["menu"]["clases"]})')

    def test_campos_de_formulario_sin_zoom_del_iphone_y_doble_toque_desactivado(self):
        for ruta in ('/shop', '/socios', '/contactus'):
            with self.subTest(pagina=ruta):
                _muestras, estado = self._recorrer(390, ruta)
                self.assertEqual(estado['camposChicos'], [], 'campos de menos de 16 px: el iPhone acerca la pantalla')
                self.assertEqual(estado['toque'], 'manipulation', 'el doble toque no debe hacer zoom')
