"""La ruta del catálogo: apagada no sirve nada, el token manda, sin cookies y nunca con enlaces locales."""
from odoo.tests import HttpCase, tagged

from .common import BASE, MetaComun, leer_csv

RUTA = '/dcasa/meta/catalogo.csv'
CABECERA = b'id,item_group_id,title'


@tagged('post_install', '-at_install')
class TestFeedAcceso(MetaComun, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mesa = cls._producto('Mesa acceso prueba Meta', 150.0)
        cls.gmc = cls.env['product.feed'].create({'name': 'Google prueba', 'website_id': cls.website.id,
                                                  'product_category_ids': [(6, 0, cls.padre.ids)]})

    def _pedir(self, feed=None, token=None, **params):
        feed = feed or self.feed
        consulta = {'feed': feed.id, 'token': feed.access_token if token is None else token, **params}
        return self.url_open(RUTA + '?' + '&'.join(f'{k}={v}' for k, v in consulta.items()), allow_redirects=False)

    def test_la_url_del_feed(self):
        self.assertEqual(self.feed.url, f'{BASE}{RUTA}?feed={self.feed.id}&token={self.feed.access_token}')

    def test_apagado_no_sirve_nada(self):
        self.feed.dcasa_activo = False
        respuesta = self._pedir()
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotIn(CABECERA, respuesta.content)
        self.assertNotIn(b'Mesa acceso', respuesta.content)
        self.feed.dcasa_activo = True
        self.assertEqual(self._pedir().status_code, 200)

    def test_encendido_sirve_el_csv_con_sus_cabeceras(self):
        respuesta = self._pedir()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        self.assertEqual(respuesta.headers['X-Robots-Tag'], 'noindex, nofollow')
        self.assertNotIn('Set-Cookie', respuesta.headers, 'ni sesión ni idioma: el borde no guarda nada personal')
        self.assertNotIn('Content-Encoding', respuesta.headers, 'sin gzip')
        self.assertTrue(respuesta.content.startswith(CABECERA))
        self.assertIn(str(self.mesa.product_variant_id.id), [f['id'] for f in leer_csv(respuesta.content)])

    def test_token_malo_403_y_sin_feed_404(self):
        self.assertEqual(self._pedir(token='0' * 32).status_code, 403)
        self.assertEqual(self._pedir(token='').status_code, 403)
        self.assertEqual(self.url_open(RUTA).status_code, 404)
        self.assertEqual(self.url_open(f'{RUTA}?feed=abc&token=x').status_code, 404)
        self.assertEqual(self.url_open(f'{RUTA}?feed=999999999&token=x').status_code, 404)
        self.assertEqual(self.url_open(f'{RUTA}?feed=-1&token=x').status_code, 404)

    def test_un_feed_de_google_no_sale_por_aqui(self):
        respuesta = self._pedir(feed=self.gmc)
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotIn(CABECERA, respuesta.content)

    def test_gmc_xml_nunca_sirve_el_de_meta(self):
        self.website.enabled_gmc_src = True
        respuesta = self.url_open(f'/gmc.xml?feed_id={self.feed.id}&access_token={self.feed.access_token}')
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotIn(b'Mesa acceso', respuesta.content)
        # El de Google sí funciona por su ruta (no se rompió lo nativo).
        self.assertEqual(self.url_open(f'/gmc.xml?feed_id={self.gmc.id}&access_token={self.gmc.access_token}')
                         .status_code, 200)

    def test_sin_direccion_publica_https_503(self):
        parametros = self.env['ir.config_parameter'].sudo()
        for base in ('http://localhost:8069', 'http://127.0.0.1:8069', 'http://tienda.example'):
            with self.subTest(base):
                parametros.set_param('web.base.url', base)
                self.feed.invalidate_recordset(['url'])
                self.assertFalse(self.feed.url, 'sin dirección pública https no hay URL que pegar en Meta')
                respuesta = self._pedir()
                self.assertEqual(respuesta.status_code, 503)
                self.assertIn('Retry-After', respuesta.headers)
                self.assertNotIn(CABECERA, respuesta.content)
                self.assertNotIn(b'localhost', respuesta.content)
                self.assertNotIn(b'127.0.0.1', respuesta.content)

    def test_enlaces_y_fotos_absolutos_y_https(self):
        self.env['product.image'].create({'name': 'Extra', 'image_1920': self.mesa.image_1920,
                                          'product_tmpl_id': self.mesa.id})
        filas = leer_csv(self._pedir().content)
        self.assertTrue(filas)
        for fila in filas:
            enlaces = [fila['link'], fila['image_link']] + [e for e in fila['additional_image_link'].split(',') if e]
            for enlace in enlaces:
                with self.subTest(enlace):
                    self.assertTrue(enlace.startswith(BASE + '/'), enlace)
        # Las fotos del CSV abren (las sirve /dcasa/img, en JPEG).
        fila = next(f for f in filas if f['id'] == str(self.mesa.product_variant_id.id))
        foto = self.url_open(fila['image_link'].removeprefix(BASE))
        self.assertEqual(foto.status_code, 200)
        self.assertEqual(foto.headers['Content-Type'], 'image/jpeg')

    def test_cambiar_la_direccion_secreta(self):
        viejo = self.feed.access_token
        self.feed.action_dcasa_meta_nueva_direccion()
        self.assertNotEqual(self.feed.access_token, viejo)
        self.assertRegex(self.feed.access_token, r'^[0-9a-f]{32}$')
        self.assertEqual(self._pedir(token=viejo).status_code, 403, 'la dirección vieja ya no sirve')
        self.assertEqual(self._pedir().status_code, 200)
        self.assertIn('dirección secreta', self.feed.message_ids[:1].body)
        self.assertNotIn(self.feed.access_token, self.feed.message_ids[:1].body, 'el token no queda en el historial')

    def test_un_feed_de_meta_no_se_vuelve_de_google_ni_con_token_debil(self):
        with self.assertRaisesRegex(Exception, 'no se puede convertir'):
            self.feed.target = 'gmc'
        with self.assertRaisesRegex(Exception, 'Cambiar la dirección secreta'):
            self.feed.access_token = '1234'
