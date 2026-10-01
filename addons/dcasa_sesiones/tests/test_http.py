import os
import re
from types import SimpleNamespace
from unittest.mock import patch

from odoo import http
from odoo.http import STORED_SESSION_BYTES
from odoo.tests import HttpCase, tagged

from ..almacen import PostgresSessionStore
from ..controllers import salud


@tagged('post_install', '-at_install')
class TestSesionesHttp(HttpCase):
    """Odoo de punta a punta con las sesiones en la base: login, «reinicio» y la ruta de salud."""

    def reiniciar(self):
        """Como un reinicio del contenedor: Odoo con un almacén nuevo, sin nada en memoria."""
        nuevo = PostgresSessionStore(self.env.cr.dbname)
        patcher = patch.object(http.root, 'session_store', nuevo)
        patcher.start()
        self.addCleanup(patcher.stop)
        return nuevo

    def cerrar_al_final(self, sid):
        self.addCleanup(http.root.session_store.delete_from_identifiers, [sid[:STORED_SESSION_BYTES]])

    def info_sesion(self):
        respuesta = self.url_open('/web/session/get_session_info',
                                  json={'jsonrpc': '2.0', 'method': 'call', 'params': {}})
        return respuesta.json()['result']

    # ------------------------------------------------------------------
    # Login de /web
    # ------------------------------------------------------------------

    def test_login_web_sobrevive_al_reinicio(self):
        self.assertIsInstance(http.root.session_store, PostgresSessionStore)
        pagina = self.url_open('/web/login').text
        token = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
        respuesta = self.url_open('/web/login', data={
            'login': 'admin', 'password': 'admin', 'csrf_token': token, 'redirect': '/web/health',
        })
        self.assertEqual(respuesta.status_code, 200)
        sid = self.opener.cookies.get('session_id')
        self.assertTrue(sid, 'El login pone la cookie de sesión')
        self.cerrar_al_final(sid)
        admin = self.env.ref('base.user_admin')
        self.assertEqual(http.root.session_store.get(sid).uid, admin.id, 'La sesión está en la base')
        self.reiniciar()
        self.assertEqual(self.info_sesion()['uid'], admin.id, 'Tras el reinicio sigue dentro')

    def test_cerrar_sesion_la_borra(self):
        self.authenticate('admin', 'admin')
        sid = self.session.sid
        self.cerrar_al_final(sid)
        self.assertFalse(http.root.session_store.get(sid).is_new)
        self.url_open('/web/session/logout?redirect=/web/health')
        self.assertTrue(self.reiniciar().get(sid).is_new, 'El logout rota: la sesión vieja ya no abre')

    # ------------------------------------------------------------------
    # Login de /socios (sesión propia: celular + PIN)
    # ------------------------------------------------------------------

    def test_login_socios_sobrevive_al_reinicio(self):
        if 'res.partner' not in self.env or 'dcasa_socio_codigo' not in self.env['res.partner']._fields:
            self.skipTest('dcasa_socios no está instalado')
        self.startPatcher(patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'}))
        self.authenticate(None, None)  # visitante, como el QR de la tienda

        def post(url, **datos):
            pagina = self.url_open('/socios/terminos').text
            datos['csrf_token'] = re.search(r'csrf_token: "([^"]+)"', pagina).group(1)
            return self.url_open(url, data=datos)

        post('/socios/registro', nombre='Luis', apellido='Mora', celular='6123-4567', pin='482915',
             pin2='482915', cumple_dia='14', cumple_mes='2', acepta='on')
        socio = self.env['res.partner'].search([('dcasa_celular', '=', '61234567')])
        self.assertTrue(socio)
        post('/socios/salir')
        cuenta = post('/socios/entrar', celular='6123-4567', pin='482915')
        self.assertIn(socio.dcasa_socio_codigo, cuenta.text)
        sid = self.opener.cookies.get('session_id')
        self.cerrar_al_final(sid)
        self.assertEqual(http.root.session_store.get(sid)['dcasa_socio']['id'], socio.id)
        self.reiniciar()
        self.assertIn(socio.dcasa_socio_codigo, self.url_open('/socios/cuenta').text,
                      'Tras el reinicio el socio sigue dentro')

    # ------------------------------------------------------------------
    # /dcasa/salud
    # ------------------------------------------------------------------

    def test_salud_ok_sin_cookie_ni_sesion(self):
        respuesta = self.url_open('/dcasa/salud')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {'ok': True})
        self.assertNotIn('Set-Cookie', respuesta.headers)
        self.assertNotIn('session_id', self.opener.cookies)
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        self.assertNotRegex(respuesta.text, r'(?i)19\.0|odoo|dcasa', 'No dice versión ni base')

    def test_salud_con_sesion_no_la_toca(self):
        self.authenticate('admin', 'admin')
        respuesta = self.url_open('/dcasa/salud')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('Set-Cookie', respuesta.headers)

    def test_salud_503_si_la_base_no_responde(self):
        with patch.object(salud, 'base_responde', return_value=False):
            respuesta = self.url_open('/dcasa/salud')
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json(), {'ok': False})
        self.assertNotIn('Set-Cookie', respuesta.headers)

    def test_salud_solo_get(self):
        self.assertEqual(self.url_open('/dcasa/salud', data={'x': '1'}).status_code, 405)

    def test_base_responde_sin_registro(self):
        """Modo sin base (la base no carga): conexión directa con SELECT 1."""
        with patch.object(salud, 'request', SimpleNamespace(env=None, db=self.env.cr.dbname)):
            self.assertTrue(salud.base_responde())
        with patch.object(salud, 'request', SimpleNamespace(env=None, db='dcasa_base_que_no_existe')), \
                self.assertLogs('odoo.addons.dcasa_sesiones.controllers.salud', 'WARNING'):
            self.assertFalse(salud.base_responde())
