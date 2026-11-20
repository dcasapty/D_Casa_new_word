"""Lote «legibilidad», arreglo 5: la cámara de «Busca con una foto» va sola, sin palabra, y era la función menos
conocida del buscador. Una pista corta y visible («Busca con una foto») debajo de cada caja de búsqueda que lleva la
cámara."""
import re

from odoo.addons.website_dcasa.tests.chrome_movil import ChromeMovilCase
from odoo.addons.website_dcasa.tests.contraste import razon_del_texto, sonda
from odoo.tests import HttpCase, tagged

from ..models.buscar_foto import PARAM_ACTIVO

PISTA = 'Busca con una foto'


@tagged('post_install', '-at_install')
class TestPistaDeLaCamara(HttpCase):

    def test_cada_caja_con_camara_lleva_su_pista(self):
        for ruta in ('/', '/shop'):
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                camaras = len(re.findall(r'<label[^>]*o_dcasa_foto_boton_icono', html))
                pistas = re.findall(r'<p[^>]*o_dcasa_foto_pista[^>]*>.*?</p>', html, re.S)
                self.assertGreaterEqual(camaras, 2, 'la cabecera y la tienda llevan cámara')
                self.assertEqual(len(pistas), camaras, 'cada cámara tiene su pista')
                for pista in pistas:
                    self.assertIn(PISTA, pista)
                    self.assertIn('aria-hidden="true"', pista, 'el lector de pantalla ya oye la cámara: no se repite')

    def test_apagada_la_camara_no_sale_la_pista(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAM_ACTIVO, 'False')
        html = self.url_open('/shop').text
        self.assertNotIn('o_dcasa_foto_pista', html)
        self.assertNotIn('o_dcasa_foto_boton', html)


@tagged('post_install', '-at_install')
class TestPistaDeLaCamaraEnElCelular(ChromeMovilCase):

    def test_la_pista_se_ve_y_se_lee(self):
        with self._chrome_movil(390) as browser:
            browser.navigate_to(self.base_url() + '/shop', wait_stop=True)
            self.assertTrue(browser._wait_ready())
            visible = self._evaluar(browser, """(async () => {
                for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) {
                    await new Promise((ok) => setTimeout(ok, 50));
                }
                const p = document.querySelector('.o_wsale_products_searchbar_form .o_dcasa_foto_pista');
                const r = p.getBoundingClientRect();
                return { ancho: r.width, alto: r.height, texto: p.textContent.trim(), sale: r.right <= innerWidth };
            })()""")
            self.assertEqual(visible['texto'], PISTA)
            self.assertGreater(visible['ancho'], 60)
            self.assertTrue(visible['sale'], 'cabe en la pantalla')
            medida = self._evaluar(browser, sonda('.o_wsale_products_searchbar_form .o_dcasa_foto_pista'))
            self.assertGreaterEqual(razon_del_texto(medida), 4.5, f'pista bajo 4,5:1 sobre {medida["fondo"]}')
