"""La etiqueta de disponibilidad se ve al abrir la ficha en el celular, sin bajar y sin que la tape la barra fija de
«Agregar al carrito» (ajuste del lote 1 de la web, 2026-11-13): va en la misma línea del precio, a la derecha de
«+ ITBMS». Medido en Chrome como teléfono, con un nombre de tres líneas y una foto cuadrada (el peor caso del
catálogo), en los tres estados y en tres teléfonos comunes."""
import base64
import io

from PIL import Image

from odoo.addons.website_dcasa.tests.chrome_movil import ChromeMovilCase
from odoo.tests import tagged

# Ancho × alto de pantalla (CSS): Android común, iPhone 12-15 y iPhone Pro Max.
TELEFONOS = ((360, 800), (390, 844), (430, 932))

MEDIR = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(300);
        window.scrollTo(0, 0);
        const e = document.querySelector('.o_dcasa_disponibilidad').getBoundingClientRect();
        const precio = document.querySelector('.product_price').getBoundingClientRect();
        const cta = document.querySelector('#o_wsale_cta_wrapper');
        const fija = getComputedStyle(cta).position === 'fixed';
        return {
            pantalla: [innerWidth, innerHeight], pagina: document.documentElement.scrollWidth,
            etiqueta: [e.top, e.bottom, e.left, e.right], precio: [precio.top, precio.bottom, precio.right],
            barra: fija ? cta.getBoundingClientRect().top : innerHeight, barraAlto: cta.getBoundingClientRect().height,
        };
    })()
"""


def _foto():
    salida = io.BytesIO()
    Image.new('RGB', (1200, 1200), (205, 205, 210)).save(salida, 'JPEG')
    return base64.b64encode(salida.getvalue())


@tagged('post_install', '-at_install')
class TestDisponibilidadALaVistaEnElCelular(ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'is_published': True,
                'allow_out_of_stock_order': True, 'list_price': 238.99, 'image_1920': _foto(),
                'public_categ_ids': [(6, 0, cls.env.ref('website_dcasa.public_category_colchones').ids)]}
        nombre = 'COLCHÓN DR. PRUEBA ORTOPÉDICO A CUADROS AZUL Y BLANCO, LATERAL GRIS'
        ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.productos = {}
        for estado, cantidad in (('disponible', 12), ('pocas', 3), ('agotado', 0)):
            producto = cls.env['product.template'].create({**base, 'name': f'{nombre} {estado.upper()}'})
            if cantidad:
                cls.env['stock.quant']._update_available_quantity(producto.product_variant_id, ubicacion, cantidad)
            cls.productos[estado] = producto

    def test_se_ve_al_abrir_la_ficha_en_la_linea_del_precio(self):
        for ancho, alto in TELEFONOS:
            for estado, producto in self.productos.items():
                with self.subTest(telefono=f'{ancho}x{alto}', estado=estado), self._chrome_movil(ancho) as browser:
                    browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                        'width': ancho, 'height': alto, 'deviceScaleFactor': 2, 'mobile': True})
                    browser.navigate_to(self.base_url() + producto.website_url, wait_stop=True)
                    self.assertTrue(browser._wait_ready())
                    m = self._evaluar(browser, MEDIR)
                    arriba, abajo, izquierda, derecha = m['etiqueta']
                    self.assertLessEqual(m['pagina'], ancho)
                    self.assertGreaterEqual(arriba, 0)
                    self.assertLessEqual(derecha, ancho, 'entera de ancho')
                    self.assertLessEqual(abajo, m['barra'], 'no la tapa la barra fija de «Agregar al carrito»')
                    self.assertLess(m['barraAlto'], 90, 'la barra fija en una sola fila')
                    centro_etiqueta, centro_precio = (arriba + abajo) / 2, (m['precio'][0] + m['precio'][1]) / 2
                    self.assertAlmostEqual(centro_etiqueta, centro_precio, delta=12, msg='en la línea del precio')
                    self.assertGreater(izquierda, m['precio'][2], 'a la derecha del precio y de «+ ITBMS»')
