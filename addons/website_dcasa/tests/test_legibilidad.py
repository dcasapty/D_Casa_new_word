"""Lote «legibilidad» del sitio (de la comparación con Feuxui, ``docs/referencias/feuxui/``). Cada arreglo mide en
Chrome, con el teléfono emulado, lo que la persona ve:

* Arreglo 3: las marcas de relleno (placeholder) del buscador del catálogo y de Socios y los pasos del carrito que aún
  no tocan se leen con 4,5:1 o más (antes 2,86, 3,12 y 2,38:1).
"""
import json

from odoo.tests import tagged

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
