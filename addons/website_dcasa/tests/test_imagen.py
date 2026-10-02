import base64
import io
import re

from PIL import Image

from odoo.tests import HttpCase, tagged


def foto(ancho, alto, color='blue', formato='JPEG', modo='RGB'):
    salida = io.BytesIO()
    Image.new(modo, (ancho, alto), color).save(salida, format=formato)
    return base64.b64encode(salida.getvalue())


@tagged('post_install', '-at_install')
class TestImagenWebp(HttpCase):
    """/dcasa/img: WebP/JPEG al ancho justo, inmutable por versión, solo lo publicado."""

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.mesa = self.env['product.template'].create({
            'name': 'Mesa foto prueba', 'list_price': 10, 'is_published': True,
            'image_1920': foto(1200, 900),
        })

    def _url(self, registro, ancho, formato='webp'):
        return self.website._dcasa_img_url(registro, ancho, formato)

    def _abrir(self, url, **kw):
        return self.url_open(url, allow_redirects=False, **kw)

    def test_webp_al_ancho_pedido_y_cabeceras(self):
        url = self._url(self.mesa, 512)
        self.assertRegex(url, rf'^/dcasa/img/product\.template/{self.mesa.id}/image_1920/512\.webp\?v=[0-9a-f]{{12}}$')
        respuesta = self._abrir(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Content-Type'], 'image/webp')
        self.assertEqual(respuesta.headers['Cache-Control'], 'public, max-age=31536000, immutable')
        self.assertNotIn('Set-Cookie', respuesta.headers, 'el borde no cachea respuestas con cookie')
        imagen = Image.open(io.BytesIO(respuesta.content))
        self.assertEqual(imagen.format, 'WEBP')
        self.assertEqual(imagen.size, (512, 384))
        # Revalidación del navegador: 304 sin cuerpo.
        otra = self._abrir(url, headers={'If-None-Match': respuesta.headers['ETag']})
        self.assertEqual(otra.status_code, 304)

    def test_jpeg_progresivo_y_nunca_agranda(self):
        respuesta = self._abrir(self._url(self.mesa, 1600, 'jpg'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Content-Type'], 'image/jpeg')
        imagen = Image.open(io.BytesIO(respuesta.content))
        self.assertEqual(imagen.size, (1200, 900), 'el original mide 1200: no se agranda a 1600')
        self.assertTrue(imagen.info.get('progressive') or imagen.info.get('progression'))
        self.assertNotIn('exif', imagen.info)

    def test_png_transparente(self):
        self.mesa.image_1920 = foto(800, 800, (0, 0, 255, 0), 'PNG', 'RGBA')
        webp = Image.open(io.BytesIO(self._abrir(self._url(self.mesa, 256)).content))
        self.assertEqual(webp.mode, 'RGBA')
        jpg = Image.open(io.BytesIO(self._abrir(self._url(self.mesa, 256, 'jpg')).content))
        self.assertEqual(jpg.getpixel((5, 5)), (255, 255, 255), 'sin alfa en JPEG: fondo blanco')

    def test_se_genera_una_sola_vez_y_cambia_con_la_foto(self):
        Variante = self.env['dcasa.imagen.variante']
        url = self._url(self.mesa, 256)
        primera = self._abrir(url).content
        self.assertEqual(self._abrir(url).content, primera)
        self.assertEqual(Variante.search_count([('res_id', '=', self.mesa.id),
                                                ('res_model', '=', 'product.template')]), 1)
        self.mesa.image_1920 = foto(1000, 1000, 'red')
        nueva = self._url(self.mesa, 256)
        self.assertNotEqual(nueva, url, 'otra foto, otra versión (otra URL inmutable)')
        self.assertEqual(self._abrir(nueva).status_code, 200)
        variantes = Variante.search([('res_id', '=', self.mesa.id), ('res_model', '=', 'product.template')])
        self.assertEqual(variantes.mapped('version'), [nueva.rsplit('=', 1)[1]], 'las de la foto vieja se borran')
        # La URL vieja (página estática aún sin regenerar) lleva a la vigente, sin caché larga.
        vieja = self._abrir(url)
        self.assertEqual(vieja.status_code, 302)
        self.assertTrue(vieja.headers['Location'].endswith(nueva))
        self.assertNotIn('immutable', vieja.headers.get('Cache-Control', ''))

    def test_sin_version_redirige(self):
        url = self._url(self.mesa, 512)
        respuesta = self._abrir(url.split('?')[0])
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.headers['Location'].endswith(url))

    def test_no_publicado_o_fuera_de_lista_no_existe(self):
        url = self._url(self.mesa, 512)
        self.mesa.is_published = False
        self.assertEqual(self._abrir(url).status_code, 404)
        self.mesa.is_published = True
        base = url.split('/512.webp')[0]
        version = url.rsplit('=', 1)[1]
        for mala in (f'{base}/513.webp?v={version}', f'{base}/512.png?v={version}',
                     f'/dcasa/img/res.partner/{self.env.user.partner_id.id}/image_1920/512.webp',
                     f'/dcasa/img/product.template/{self.mesa.id}/image_128/512.webp'):
            self.assertEqual(self._abrir(mala).status_code, 404, mala)
        sin_foto = self.env['product.template'].create({'name': 'Sin foto', 'is_published': True})
        self.assertIsNone(self._url(sin_foto, 512))
        self.assertEqual(self._abrir(f'/dcasa/img/product.template/{sin_foto.id}/image_1920/512.webp').status_code,
                         404)

    def test_variante_y_galeria(self):
        talla = self.env['product.attribute'].create({
            'name': 'Tamaño foto', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Twin'}), (0, 0, {'name': 'Full'})],
        })
        cama = self.env['product.template'].create({
            'name': 'Cama foto', 'is_published': True, 'image_1920': foto(900, 900),
            'attribute_line_ids': [(0, 0, {'attribute_id': talla.id, 'value_ids': [(6, 0, talla.value_ids.ids)]})],
        })
        twin, full = cama.product_variant_ids
        full.image_variant_1920 = foto(700, 700, 'green')
        self.assertTrue(self._url(twin, 512).startswith(f'/dcasa/img/product.template/{cama.id}/'),
                        'sin foto propia, la de la plantilla (misma URL, misma caché)')
        self.assertTrue(self._url(full, 512).startswith(f'/dcasa/img/product.product/{full.id}/image_variant_1920/'))
        self.assertEqual(self._abrir(self._url(full, 512)).status_code, 200)
        extra = self.env['product.image'].create({'name': 'Detalle', 'product_tmpl_id': cama.id,
                                                  'image_1920': foto(600, 600, 'yellow')})
        respuesta = self._abrir(self._url(extra, 1024))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(respuesta.content)).size, (600, 600))
        cama.is_published = False
        self.assertEqual(self._abrir(self._url(extra, 512)).status_code, 404)
        self.assertEqual(self._abrir(self._url(full, 512)).status_code, 404)

    def test_tarjetas_de_la_tienda_con_webp(self):
        html = self.url_open('/shop').text
        tarjeta = re.search(
            r'<picture><source type="image/webp" srcset="([^"]*)" sizes="[^"]+"/><img[^>]*oe_product_image_img\b',
            html)
        self.assertTrue(tarjeta, 'la foto de la tarjeta va en <picture> con WebP')
        self.assertRegex(tarjeta.group(1), r'^/dcasa/img/product\.\w+/\d+/\w+/256\.webp\?v=\w{12} 256w, '
                                           r'\S+/512\.webp\?v=\w{12} 512w, \S+/1024\.webp\?v=\w{12} 1024w$')
