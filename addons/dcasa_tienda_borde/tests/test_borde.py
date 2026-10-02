import os
import re
from unittest.mock import patch

import requests

from odoo.addons.dcasa_tienda_borde.models.ir_http import (
    CABECERA_BORDE,
    CLAVES_NEUTRAS,
    COOKIE_PERSONAL,
    MARCA_ANONIMO,
    sesion_personal,
)
from odoo.http import Session, get_default_session
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tests.common import TEST_CURSOR_COOKIE_NAME

TOKEN = 'b' * 40
CSRF = re.compile(r'[0-9a-f]{40}o\d{6,}')


def _sin_csrf(html):
    """El único dato que cambia entre dos dibujos anónimos de Odoo: el token CSRF (por sesión)."""
    return CSRF.sub('«csrf»', html)


def _sesion(**datos):
    return Session(dict(get_default_session(), db='x', **datos), 'a' * 84, new=True)


@tagged('post_install', '-at_install')
class TestSesionPersonal(TransactionCase):
    """Qué datos de sesión hacen que la página sea de alguien (y el borde no pueda servir la guardada)."""

    def test_anonimo_de_odoo_no_es_personal(self):
        self.assertFalse(sesion_personal(_sesion()))
        # Lo que website_sale y dcasa_socios guardan a cualquier anónimo que pasa por la tienda.
        self.assertFalse(sesion_personal(_sesion(
            website_sale_current_pl=1, fiscal_position_id=False, website_sale_pricelist_time=1.0,
            dcasa_padrino='DCA7K3M9Q', _trace_disable=True)))
        # Valores vacíos de claves personales (carrito vaciado tras pagar) tampoco.
        self.assertFalse(sesion_personal(_sesion(sale_order_id=None, website_sale_cart_quantity=0)))

    def test_usuario_carrito_deseos_socio_son_personales(self):
        for datos in ({'uid': 2}, {'pre_uid': 2}, {'sale_order_id': 7}, {'website_sale_cart_quantity': 1},
                      {'wishlist_ids': [3]}, {'dcasa_socio': {'id': 1}}, {'website_sale_selected_pl_id': 2},
                      {'website_sale_shop_layout_mode': 'list'}, {'clave_que_nadie_conoce': 1}):
            with self.subTest(datos=datos):
                self.assertTrue(sesion_personal(_sesion(**datos)))

    def test_neutras_no_incluyen_lo_personal(self):
        for clave in ('uid', 'login'):
            # uid y login están en la lista porque toda sesión los tiene; uid se mira aparte.
            self.assertIn(clave, CLAVES_NEUTRAS)
        for clave in ('sale_order_id', 'pre_uid', 'wishlist_ids', 'dcasa_socio', 'website_sale_cart_quantity'):
            self.assertNotIn(clave, CLAVES_NEUTRAS)


@tagged('post_install', '-at_install')
class TestCacheDelBorde(HttpCase):
    """Odoo certifica la página anónima que el borde guarda y marca a quien debe saltarse la caché."""

    def setUp(self):
        super().setUp()
        recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        self.producto = self.env['product.template'].create({
            'name': 'Mesa borde prueba', 'list_price': 77.5, 'is_published': True, 'sale_ok': True,
            'type': 'consu', 'public_categ_ids': [(6, 0, recamaras.ids)], 'dcasa_black_weekend': True,
        })
        self.env['ir.config_parameter'].sudo().set_param('dcasa_black_weekend.activo', '1')
        entorno = patch.dict(os.environ, {'TIENDA_FEED_TOKEN': TOKEN})
        entorno.start()
        self.addCleanup(entorno.stop)

    def _otro(self, metodo, ruta, navegador=None, cookies=None, **kwargs):
        """Petición de alguien que no es el navegador del test (el borde, otro visitante)."""
        navegador = navegador or requests.Session()
        self.cr.flush()
        self.cr.clear()
        with self.allow_requests():
            cookies = dict(cookies or {}, **{TEST_CURSOR_COOKIE_NAME: self.opener.cookies.get(TEST_CURSOR_COOKIE_NAME)})
            return navegador.request(metodo, self.base_url() + ruta, cookies=cookies, timeout=30,
                                     allow_redirects=False, **kwargs)

    def _relleno(self, ruta, token=TOKEN, cookies=None):
        """Lo que hace el Worker para guardar una página: sin cookies del visitante y con el secreto."""
        return self._otro('GET', ruta, headers={CABECERA_BORDE: token}, cookies=cookies)

    def test_relleno_es_el_html_de_odoo_y_anonimo(self):
        for ruta in ('/', '/shop', self.producto.website_url, '/black-weekend', '/visitanos'):
            with self.subTest(ruta=ruta):
                guardable = self._relleno(ruta)
                self.assertEqual(guardable.status_code, 200)
                self.assertEqual(guardable.headers.get(CABECERA_BORDE), MARCA_ANONIMO)
                self.assertNotIn('Set-Cookie', guardable.headers, 'Ni session_id ni frontend_lang')
                # Mismo HTML que Odoo le da a un visitante anónimo cualquiera (salvo el CSRF).
                visita = self._otro('GET', ruta)
                self.assertEqual(visita.status_code, 200)
                self.assertIn('session_id', visita.headers.get('Set-Cookie', ''))
                self.assertEqual(_sin_csrf(guardable.text), _sin_csrf(visita.text))
                self.assertIn('o_dcasa', guardable.text, 'Es el diseño del sitio (website_dcasa)')

    def test_sin_el_secreto_no_hay_certificado(self):
        for token in ('otro' * 10, ''):
            with self.subTest(token=token):
                respuesta = self._relleno('/', token=token)
                self.assertNotIn(CABECERA_BORDE, respuesta.headers)
                self.assertIn('session_id', respuesta.headers.get('Set-Cookie', ''))
        with patch.dict(os.environ, {'TIENDA_FEED_TOKEN': ''}):
            self.assertNotIn(CABECERA_BORDE, self._relleno('/').headers, 'Sin secreto configurado: nunca')

    def test_logueado_recibe_la_cookie_y_nunca_se_certifica(self):
        self.authenticate('admin', 'admin')
        respuesta = self.url_open('/')
        self.assertIn(COOKIE_PERSONAL, respuesta.headers.get('Set-Cookie', ''))
        self.assertEqual(self.opener.cookies.get(COOKIE_PERSONAL), '1')
        # Aunque al borde se le escapara la cookie de sesión, Odoo no certifica una página de alguien.
        # Se renueva en cada respuesta mientras la sesión sea propia (no vence antes que la sesión).
        self.assertIn(COOKIE_PERSONAL, self.url_open('/shop').headers.get('Set-Cookie', ''))
        relleno = self._relleno('/', cookies={'session_id': self.session.sid})
        self.assertNotIn(CABECERA_BORDE, relleno.headers)
        self.assertNotIn('Set-Cookie', relleno.headers)
        # Al cerrar sesión la cookie se va: vuelve a recibir la página guardada.
        self.url_open('/web/session/logout', allow_redirects=False)
        self.url_open('/')
        self.assertIsNone(self.opener.cookies.get(COOKIE_PERSONAL))

    def test_anonimo_navegando_no_recibe_la_cookie(self):
        for ruta in ('/', '/shop', self.producto.website_url, '/dcasa/borde/csrf'):
            self.assertNotIn(COOKIE_PERSONAL, self.url_open(ruta).headers.get('Set-Cookie', ''), ruta)
        self.assertIsNone(self.opener.cookies.get(COOKIE_PERSONAL))

    def test_csrf_fresco_sirve_para_agregar_y_el_carrito_marca(self):
        """La página guardada trae el CSRF de otra sesión; el del endpoint es el de esta."""
        guardada = self._relleno('/').text
        token_ajeno = CSRF.search(guardada).group(0)
        datos = {'product_template_id': self.producto.id}
        # Con el token de la página guardada, Odoo rechaza el formulario (otra sesión)...
        self.url_open('/')
        ajeno = self.url_open('/dcasa/carrito/agregar', data=dict(datos, csrf_token=token_ajeno),
                              allow_redirects=False)
        self.assertEqual(ajeno.status_code, 400)
        # ...con el que da /dcasa/borde/csrf, lo acepta y el carrito vuelve personal la sesión.
        fresco = self.url_open('/dcasa/borde/csrf')
        self.assertEqual(fresco.headers['Cache-Control'], 'no-store')
        respuesta = self.url_open('/dcasa/carrito/agregar', data=dict(datos, csrf_token=fresco.json()['csrf_token']),
                                  allow_redirects=False)
        self.assertEqual(respuesta.status_code, 303)
        self.assertTrue(respuesta.headers['Location'].endswith('/shop/cart'))
        self.assertEqual(self.opener.cookies.get(COOKIE_PERSONAL), '1')

    def test_csrf_sin_sesion_previa(self):
        """Un visitante que solo vio páginas guardadas no tiene sesión: el endpoint la crea y la guarda."""
        navegador = requests.Session()
        token = self._otro('GET', '/dcasa/borde/csrf', navegador).json()['csrf_token']
        self.assertTrue(navegador.cookies.get('session_id'))
        respuesta = self._otro('POST', '/dcasa/carrito/agregar', navegador,
                               data={'product_template_id': self.producto.id, 'csrf_token': token})
        self.assertEqual(respuesta.status_code, 303)

    def test_el_js_del_csrf_esta_en_el_sitio(self):
        rutas = [r[0] for r in self.env['ir.asset']._get_asset_paths('web.assets_frontend', {})]
        self.assertIn('/dcasa_tienda_borde/static/src/js/borde_csrf.js', rutas)
