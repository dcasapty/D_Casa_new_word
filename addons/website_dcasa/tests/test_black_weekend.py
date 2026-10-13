"""Black Weekend: ventana en hora de Panamá, banda de la portada, /black-weekend y etiqueta."""
import json
import re
from datetime import datetime
from html.parser import HTMLParser

from odoo.addons.website_dcasa.controllers.main import _sitemap_black_weekend
from odoo.addons.website_dcasa.models.black_weekend import (
    OG_IMAGEN,
    PARAM_ACTIVO,
    PARAM_FIN,
    PARAM_INICIO,
    VENTANA_POR_DEFECTO,
    fechas_en_texto,
    leer_combo,
)
from odoo.addons.website_dcasa.tests.test_imagen import foto
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools.misc import file_path

PALABRAS_PROHIBIDAS = ('tafi', 'tiempo limitado', 'remate', 'cuotas', 'financiamiento', 'corre!', 'cuenta regresiva')
# Clases que pintan amarillo y los fondos oscuros (negro, azul, navy, foto oscurecida) donde pueden ir.
CLASES_AMARILLAS = {'o_dcasa_btn_amarillo', 'o_dcasa_bw_titulo'}
FONDOS_OSCUROS = {'o_dcasa_bw', 'o_dcasa_hero', 'o_dcasa_socios_band', 'o_dcasa_visita', 'o_dcasa_anuncios',
                  'o_dcasa_footer'}


class _AmarilloSobreBlanco(HTMLParser):
    """Junta las etiquetas con una clase amarilla que no están dentro de un fondo oscuro."""
    VACIAS = {'img', 'input', 'meta', 'link', 'br', 'hr', 'source', 'path', 'circle', 'rect'}

    def __init__(self):
        super().__init__()
        self.pila, self.malas = [], []

    def handle_starttag(self, tag, attrs):
        clases = set((dict(attrs).get('class') or '').split())
        if clases & CLASES_AMARILLAS and not any(c & FONDOS_OSCUROS for c in self.pila):
            self.malas.append((tag, sorted(clases)))
        if tag not in self.VACIAS:
            self.pila.append(clases)

    def handle_startendtag(self, tag, attrs):
        clases = set((dict(attrs).get('class') or '').split())
        if clases & CLASES_AMARILLAS and not any(c & FONDOS_OSCUROS for c in self.pila):
            self.malas.append((tag, sorted(clases)))

    def handle_endtag(self, tag):
        if tag not in self.VACIAS and self.pila:
            self.pila.pop()


def amarillo_sobre_blanco(html):
    parser = _AmarilloSobreBlanco()
    parser.feed(html)
    return parser.malas


def _json_ld(html):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _visible(html):
    return re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S).lower()


class _Base:

    def _ventana(self, activo='0', inicio='', fin=''):
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(PARAM_ACTIVO, activo)
        param.set_param(PARAM_INICIO, inicio)
        param.set_param(PARAM_FIN, fin)


@tagged('post_install', '-at_install')
class TestVentanaBlackWeekend(_Base, TransactionCase):
    """La ventana se evalúa en hora de Panamá (UTC-5), inclusive en los dos extremos."""

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')

    def activo(self, utc):
        return self.website._dcasa_black_weekend_activo(ahora=utc)

    def test_bordes_de_la_ventana_en_hora_de_panama(self):
        self._ventana('0', '2026-10-05', '2026-10-11')
        # Domingo 4, 23:59:59 en Panamá = lunes 5, 04:59:59 UTC: todavía no.
        self.assertFalse(self.activo(datetime(2026, 10, 5, 4, 59, 59)))
        # Lunes 5, 00:00:00 en Panamá = 05:00:00 UTC: empieza.
        self.assertTrue(self.activo(datetime(2026, 10, 5, 5, 0, 0)))
        self.assertTrue(self.activo(datetime(2026, 10, 8, 18, 0, 0)))
        # Domingo 11, 23:59:59 en Panamá = lunes 12, 04:59:59 UTC: último segundo.
        self.assertTrue(self.activo(datetime(2026, 10, 12, 4, 59, 59)))
        # Lunes 12, 00:00:00 en Panamá: se apaga sola.
        self.assertFalse(self.activo(datetime(2026, 10, 12, 5, 0, 0)))
        # Medianoche UTC del lunes 5 aún es domingo en Panamá.
        self.assertFalse(self.activo(datetime(2026, 10, 5, 0, 0, 0)))

    def test_forzado_en_staging_sin_mirar_fechas(self):
        self._ventana('1', '2026-10-05', '2026-10-11')
        self.assertTrue(self.activo(datetime(2026, 10, 2, 12, 0)))
        self.assertTrue(self.activo(datetime(2026, 12, 1, 12, 0)))

    def test_sin_fechas_solo_si_esta_forzado(self):
        self._ventana('0')
        self.assertFalse(self.activo(datetime(2026, 10, 8, 12, 0)))
        self._ventana('1')
        self.assertTrue(self.activo(datetime(2026, 10, 8, 12, 0)))

    def test_un_lado_abierto(self):
        self._ventana('0', '', '2026-10-11')
        self.assertTrue(self.activo(datetime(2026, 1, 1, 12, 0)))
        self.assertFalse(self.activo(datetime(2026, 10, 12, 5, 0)))

    def test_fechas_invalidas_la_apagan(self):
        for inicio, fin in (('5/10/2026', '2026-10-11'), ('2026-10-11', '2026-10-05'), ('2026-13-01', '')):
            self._ventana('0', inicio, fin)
            self.assertFalse(self.activo(datetime(2026, 10, 8, 12, 0)), (inicio, fin))

    def test_ventana_de_la_duena_por_defecto(self):
        self.assertEqual(VENTANA_POR_DEFECTO, {
            PARAM_ACTIVO: '0', PARAM_INICIO: '2026-10-02', PARAM_FIN: '2026-10-11'})
        param = self.env['ir.config_parameter'].sudo()
        param.search([('key', 'in', list(VENTANA_POR_DEFECTO))]).unlink()
        param.set_param(PARAM_ACTIVO, '1')  # lo que ya está (p. ej. staging) no se pisa
        self.website._dcasa_bw_parametros_por_defecto()
        self.assertEqual(param.get_param(PARAM_ACTIVO), '1')
        self.assertEqual(param.get_param(PARAM_INICIO), '2026-10-02')
        self.assertEqual(param.get_param(PARAM_FIN), '2026-10-11')

    def test_textos(self):
        from datetime import date
        self.assertEqual(fechas_en_texto(date(2026, 10, 5), date(2026, 10, 11)), 'del 5 al 11 de octubre de 2026')
        self.assertEqual(fechas_en_texto(date(2026, 10, 5), None), '')
        self.assertEqual(leer_combo('Combo con colchón First Class $469.99'),
                         {'texto': 'Combo con colchón First Class', 'colchon': 'First Class', 'precio': 469.99})
        self.assertIsNone(leer_combo('El par (-10%) $28.78'))
        self.assertIsNone(leer_combo(''))

    def test_imagen_para_compartir_liviana(self):
        from PIL import Image
        ruta = file_path(OG_IMAGEN.removeprefix('/'))
        with open(ruta, 'rb') as archivo:
            datos = archivo.read()
        self.assertLessEqual(len(datos), 200_000)
        with Image.open(ruta) as imagen:
            self.assertLessEqual(imagen.width, 1200)
            self.assertLessEqual(imagen.height, 1500)


@tagged('post_install', '-at_install')
class TestPaginasBlackWeekend(_Base, HttpCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        self.cama = self.env['product.template'].create({
            'name': 'Cama Black de prueba', 'list_price': 187.99, 'is_published': True,
            'default_code': 'BW-PRUEBA-1', 'public_categ_ids': [(6, 0, self.recamaras.ids)],
            'dcasa_black_weekend': True, 'dcasa_bw_orden': -1000, 'website_sequence': -1000,
            # Con foto propia: el <source> WebP de la tarjeta no depende del catálogo cargado.
            'image_1920': foto(600, 600),
        })
        self.otra = self.env['product.template'].create({
            'name': 'Cama normal de prueba', 'list_price': 77.0, 'is_published': True,
            'public_categ_ids': [(6, 0, self.recamaras.ids)],
        })

    def _activa(self):
        self._ventana('1', '2026-10-05', '2026-10-11')

    def _inactiva(self):
        self._ventana('0', '2020-01-01', '2020-01-02')

    def test_inactiva_no_sale_nada(self):
        self._inactiva()
        portada = self.url_open('/').text
        self.assertNotIn('o_dcasa_bw', portada)
        self.assertNotIn('o_dcasa_bw_etiqueta', self.url_open('/shop').text)
        self.assertEqual(self.url_open('/black-weekend').status_code, 404)
        self.assertFalse(list(_sitemap_black_weekend(self.env, None, '')))

    def test_banda_en_la_portada_antes_de_los_carruseles(self):
        self._activa()
        html = self.url_open('/').text
        self.assertIn('class="o_dcasa_bw"', html)
        self.assertIn('Cama Black de prueba', html)
        self.assertLess(html.index('o_dcasa_bw'), html.index('Lo más buscado'))
        self.assertIn('href="/black-weekend"', html)
        self.assertRegex(html, r'187[.,]99')
        self.assertIn('Agregar al carrito', html)
        self.assertIn('c%C3%B3digo%20BW-PRUEBA-1', html, 'WhatsApp con el código del producto')
        self.assertIn('type="image/webp"', html)

    def test_pagina_black_weekend(self):
        self._activa()
        respuesta = self.url_open('/black-weekend')
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.text
        self.assertIn('Cama Black de prueba', html)
        self.assertNotIn('Cama normal de prueba', html)
        self.assertIn('del 5 al 11 de octubre de 2026', html)
        self.assertIn('<link rel="canonical"', html)
        self.assertRegex(html, r'<meta name="description" content="Black Weekend en D(&#39;|\')CASA')
        og = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        self.assertTrue(og and og.group(1).endswith(OG_IMAGEN), 'Imagen de la campaña al compartir')
        self.assertRegex(html, r'<meta name="twitter:image" content="[^"]+black_weekend/og\.jpg"')
        listas = [d for d in _json_ld(html) if d.get('@type') == 'ItemList']
        self.assertEqual(len(listas), 1)
        nombres = [e['name'] for e in listas[0]['itemListElement']]
        self.assertIn('Cama Black de prueba', nombres)
        self.assertEqual(listas[0]['numberOfItems'], len(nombres))
        self.assertTrue(list(_sitemap_black_weekend(self.env, None, '')))

    def test_el_precio_sale_del_producto(self):
        self._activa()
        self.assertRegex(self.url_open('/black-weekend').text, r'187[.,]99')
        self.cama.list_price = 171.25
        html = self.url_open('/black-weekend').text
        self.assertRegex(html, r'171[.,]25')
        self.assertNotRegex(html, r'187[.,]99')

    def test_etiqueta_en_las_tarjetas_de_la_tienda(self):
        self._activa()
        html = self.url_open('/shop').text
        self.assertIn('o_dcasa_bw_etiqueta', html)
        # Solo el producto marcado: una etiqueta por cada producto marcado de la página.
        marcados = self.env['product.template'].search_count([
            ('dcasa_black_weekend', '=', True), ('is_published', '=', True)])
        self.assertLessEqual(html.count('class="o_dcasa_bw_etiqueta"'), marcados)

    def test_sin_amarillo_sobre_blanco_ni_palabras_prohibidas(self):
        self._activa()
        for ruta in ('/', '/black-weekend', '/shop'):
            html = self.url_open(ruta).text
            self.assertEqual(amarillo_sobre_blanco(html), [], ruta)
            visible = _visible(html)
            for palabra in PALABRAS_PROHIBIDAS:
                self.assertNotIn(palabra, visible, f'{ruta}: «{palabra}»')

    def test_no_publicado_no_sale(self):
        self._activa()
        self.cama.is_published = False
        self.assertNotIn('Cama Black de prueba', self.url_open('/').text)
        html = self.url_open('/black-weekend').text
        self.assertNotIn('Cama Black de prueba', html)

    def test_variante_destacada_se_agrega_en_un_clic(self):
        self._activa()
        color = self.env['product.attribute'].create({
            'name': 'Color BW prueba', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Beige'}), (0, 0, {'name': 'Negro'})],
        })
        self.cama.attribute_line_ids = [(0, 0, {'attribute_id': color.id, 'value_ids': [(6, 0, color.value_ids.ids)]})]
        negra = self.cama.product_variant_ids.filtered(
            lambda v: v.product_template_attribute_value_ids.name == 'Negro')
        negra.default_code = 'BW-PRUEBA-1-NEGRO'
        self.cama.dcasa_bw_variante_id = negra
        self.authenticate(None, None)
        html = self.url_open('/black-weekend').text
        self.assertIn(f'name="product_id" value="{negra.id}"', html)
        self.assertIn('BW-PRUEBA-1-NEGRO', html)
        token = re.search(r'name="csrf_token" value=[\'"]([^\'"]+)', html).group(1)
        respuesta = self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token, 'product_template_id': self.cama.id, 'product_id': negra.id,
        }, allow_redirects=False)
        self.assertTrue(respuesta.headers['Location'].endswith('/shop/cart'))
        self.assertIn('Negro', self.url_open('/shop/cart').text)
        # Una variante de otro producto no entra.
        respuesta = self.url_open('/dcasa/carrito/agregar', data={
            'csrf_token': token, 'product_template_id': self.otra.id, 'product_id': negra.id,
        }, allow_redirects=False)
        self.assertNotIn('/shop/cart', respuesta.headers['Location'])
