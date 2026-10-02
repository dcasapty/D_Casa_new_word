"""El acceso de punta a punta: /web/login, enrolar la app, Turnstile, avisos y robots.txt."""
import base64
import time
from unittest.mock import MagicMock, patch

from odoo import http
from odoo.addons.auth_totp.models.totp import hotp
from odoo.addons.dcasa_seguridad.controllers.enrolar import CLAVE_SESION
from odoo.addons.dcasa_seguridad.models.ir_http import INICIO
from odoo.addons.dcasa_seguridad.models.parametros import aplicar_sesiones_admin
from odoo.addons.dcasa_seguridad.models.res_users import RUTA_ENROLAR, ResUsers
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import HOST, Opener, get_db_name
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestAccesoHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.admin = new_test_user(cls.env, 'http_admin', groups='base.group_system', name='Admin HTTP')
        cls.vendedora = new_test_user(cls.env, 'http_vendedora', groups='base.group_user')
        cls.ICP.set_param('cf.turnstile_site_key', '')
        cls.ICP.set_param('cf.turnstile_secret_key', '')

    def setUp(self):
        super().setUp()
        self.session = http.root.session_store.new()
        self.session.update(http.get_default_session(), db=get_db_name())
        self.opener = Opener(self)
        self.opener.cookies.set('session_id', self.session.sid, domain=HOST, path='/')
        # El contador de fallos por IP vive en memoria del registro: cada test empieza limpio.
        self.env.registry._login_failures = None

    def _entrar(self, login, clave, **extra):
        return self.url_open('/web/login', data={
            'login': login, 'password': clave, 'csrf_token': http.Request.csrf_token(self), **extra})

    def _accesos(self, usuario, resultado):
        return self.env['dcasa.seguridad.acceso'].search_count([
            ('user_id', '=', usuario.id), ('resultado', '=', resultado)])

    def test_sin_obligatoriedad_entra_directo_y_queda_registrado(self):
        self.ICP.set_param('dcasa_seguridad.2fa_obligatorio', '0')
        respuesta = self._entrar('http_vendedora', 'http_vendedora')
        self.assertEqual(respuesta.request.path_url, '/odoo')
        self.assertEqual(self._accesos(self.vendedora, 'ok'), 1)

    def test_obligatorio_enrola_antes_de_abrir_el_panel(self):
        self.ICP.set_param('dcasa_seguridad.2fa_obligatorio', '1')
        self.ICP.set_param('dcasa_seguridad.2fa_alcance', 'admins')
        respuesta = self._entrar('http_admin', 'http_admin')
        self.assertTrue(respuesta.request.path_url.startswith(RUTA_ENROLAR), respuesta.request.path_url)
        self.assertIn('Activa tu doble factor', respuesta.text)
        # Sin código no hay sesión: el panel no abre.
        panel = self.url_open('/odoo', allow_redirects=False)
        self.assertIn(panel.status_code, (302, 303))
        self.assertIn('/web/login', panel.headers.get('Location', ''))

        secreto = http.root.session_store.get(self.session.sid)[CLAVE_SESION]
        with mute_logger('odoo.addons.dcasa_seguridad.controllers.enrolar'):
            malo = self.url_open(RUTA_ENROLAR, data={'codigo': '000000', 'csrf_token': http.Request.csrf_token(self)})
        self.assertIn('no coincide', malo.text)
        self.assertEqual(self._accesos(self.admin, 'fallo_2fa'), 1)

        codigo = str(hotp(base64.b32decode(secreto), int(time.time() / 30))).zfill(6)
        bueno = self.url_open(RUTA_ENROLAR, data={'codigo': codigo, 'csrf_token': http.Request.csrf_token(self)})
        self.assertEqual(bueno.request.path_url, '/odoo')
        self.admin.invalidate_recordset()
        self.assertTrue(self.admin.sudo().totp_enabled)
        self.assertEqual(self._accesos(self.admin, 'enrolado'), 1)

    def test_vendedora_no_cambia_con_alcance_admins(self):
        self.ICP.set_param('dcasa_seguridad.2fa_obligatorio', '1')
        self.ICP.set_param('dcasa_seguridad.2fa_alcance', 'admins')
        self.assertEqual(self._entrar('http_vendedora', 'http_vendedora').request.path_url, '/odoo')

    def test_fallos_de_admin_registran_bloquean_y_avisan(self):
        self.ICP.set_param('base.login_cooldown_after', 5)
        with patch.object(ResUsers, '_dcasa_avisar_admins', autospec=True) as avisar, \
                mute_logger('odoo.addons.base.models.res_users'):
            for _ in range(5):
                respuesta = self._entrar('http_admin', 'clave-equivocada')
                self.assertNotEqual(respuesta.request.path_url, '/odoo')
            self.assertEqual(self._accesos(self.admin, 'fallo'), 5)
            # Un solo aviso (al llegar al umbral), no uno por intento.
            self.assertEqual(avisar.call_count, 1)
            self.assertEqual(avisar.call_args.args[1], self.admin)
            self.assertIn('5 intentos fallidos', avisar.call_args.args[2])
            # El sexto, con la IP en espera, ni se prueba ni llena la base. Ni con la clave buena.
            respuesta = self._entrar('http_admin', 'http_admin')
            self.assertNotEqual(respuesta.request.path_url, '/odoo')
            self.assertEqual(self._accesos(self.admin, 'fallo'), 5)
            self.assertEqual(self._accesos(self.admin, 'ok'), 0)

    def test_turnstile_apagado_sin_claves_y_exigido_con_claves(self):
        self.ICP.set_param('dcasa_seguridad.2fa_obligatorio', '0')
        # Con claves, un token que Cloudflare rechaza no deja entrar (aunque la clave sea buena).
        self.ICP.set_param('cf.turnstile_site_key', '1x00000000000000000000AA')
        self.ICP.set_param('cf.turnstile_secret_key', 'secreto-de-prueba')
        rechazo = MagicMock()
        rechazo.json.return_value = {'success': False, 'error-codes': ['invalid-input-response']}
        with patch('odoo.addons.website_cf_turnstile.models.ir_http.requests.post', return_value=rechazo) as post, \
                mute_logger('odoo.http', 'odoo.addons.website_cf_turnstile.models.ir_http'):
            respuesta = self._entrar('http_vendedora', 'http_vendedora', turnstile_captcha='token-falso')
        post.assert_called_once()
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertEqual(self._accesos(self.vendedora, 'ok'), 0)
        # Sin claves (como hoy): Turnstile no interviene y se entra normal.
        self.ICP.set_param('cf.turnstile_secret_key', '')
        self.ICP.set_param('cf.turnstile_site_key', '')
        self.assertEqual(self._entrar('http_vendedora', 'http_vendedora').request.path_url, '/odoo')

    def test_sesion_de_admin_vence_desde_el_inicio_aunque_rote(self):
        self.ICP.set_param('dcasa_seguridad.2fa_obligatorio', '0')
        aplicar_sesiones_admin(self.env, horas=12, minutos=60)
        self.assertEqual(self._entrar('http_admin', 'http_admin').request.path_url, '/odoo')
        sid = self.opener.cookies['session_id']
        sesion = http.root.session_store.get(sid)
        self.assertTrue(sesion.get(INICIO))
        # 11 h después de entrar, recién rotada (Odoo pone create_time en cero): sigue dentro.
        sesion[INICIO] = time.time() - 11 * 3600
        sesion['create_time'] = time.time()
        http.root.session_store.save(sesion)
        self.assertEqual(self.url_open('/odoo').request.path_url, '/odoo')
        # 13 h después de entrar, aunque haya rotado hace un minuto: a iniciar sesión otra vez.
        sesion = http.root.session_store.get(self.opener.cookies['session_id'])
        sesion[INICIO] = time.time() - 13 * 3600
        sesion['create_time'] = time.time() - 60
        http.root.session_store.save(sesion)
        self.assertTrue(self.url_open('/odoo').request.path_url.startswith('/web/login'))

    def test_robots_txt_con_politica_de_ia(self):
        self.ICP.set_param('dcasa_seguridad.robots_ia', 'equilibrada')
        texto = self.url_open('/robots.txt').text
        self.assertIn('User-agent: GPTBot\nDisallow: /', texto)
        self.assertIn('Content-Signal: search=yes, ai-input=yes, ai-train=no', texto)
        self.assertNotIn('OAI-SearchBot', texto)
        self.assertIn('Sitemap:', texto)  # lo de Odoo sigue

    def test_gestor_de_bases_cerrado(self):
        """El gestor de bases está apagado en producción (list_db = False en odoo.conf) y bloqueado
        en el borde (edge/src/routing.ts). Aquí: sin la contraseña maestra no se borra nada."""
        from odoo.exceptions import AccessDenied  # noqa: PLC0415
        from odoo.service import db as servicio_db  # noqa: PLC0415
        with self.assertRaises(AccessDenied):
            servicio_db.check_super('no-es-la-maestra')
