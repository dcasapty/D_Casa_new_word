import base64
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.addons.dcasa_seguridad.models.parametros import (
    IA_BUSQUEDA,
    IA_ENTRENAMIENTO,
    aplicar_sesiones_admin,
    politica_robots,
    texto_robots_ia,
)
from odoo.addons.dcasa_seguridad.models.res_users import RUTA_ENROLAR, ResUsers
from odoo.exceptions import AccessDenied, AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


def _secreto():
    return base64.b32encode(os.urandom(20)).decode()


@tagged('post_install', '-at_install')
class TestSeguridad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.admin = new_test_user(cls.env, 'seg_admin', groups='base.group_system', name='Admin Seguridad')
        cls.vendedora = new_test_user(cls.env, 'seg_vendedora', groups='base.group_user')
        cls.portal = new_test_user(cls.env, 'seg_portal', groups='base.group_portal')

    def _obligatorio(self, valor, alcance=None):
        self.ICP.set_param('dcasa_seguridad.2fa_obligatorio', valor)
        if alcance:
            self.ICP.set_param('dcasa_seguridad.2fa_alcance', alcance)

    # --- Lo que trae Odoo 19 Community, instalado y en uso -----------------------------

    def test_modulos_de_odoo_instalados(self):
        Modulo = self.env['ir.module.module']
        for nombre in ('auth_totp', 'auth_totp_mail', 'auth_passkey', 'auth_timeout', 'website_cf_turnstile'):
            self.assertEqual(Modulo.search([('name', '=', nombre)]).state, 'installed', nombre)
        self.assertIn('totp_enabled', self.env['res.users']._fields)
        self.assertIn('auth_passkey_key_ids', self.env['res.users']._fields)
        # La app de códigos se activa desde el perfil (asistente de Odoo con QR).
        self.assertTrue(hasattr(self.admin, 'action_totp_enable_wizard'))
        # Nunca el código por correo de Odoo: sin servidor de correo dejaría a todos fuera.
        self.assertFalse(self.ICP.get_param('auth_totp.policy'))

    # --- Obligatoriedad -----------------------------------------------------------------

    def test_apagado_por_defecto(self):
        self.ICP.search([('key', 'in', ('dcasa_seguridad.2fa_obligatorio', 'dcasa_seguridad.2fa_alcance'))]).unlink()
        self.assertFalse(self.admin._dcasa_debe_enrolar())
        self.assertIsNone(self.admin._mfa_url())

    def test_enforce_sigue_el_parametro(self):
        self._obligatorio('0')
        self.assertIsNone(self.admin._mfa_url())
        self._obligatorio('1', 'admins')
        self.assertEqual(self.admin._mfa_url(), RUTA_ENROLAR)
        # Alcance «admins»: la vendedora y el portal entran como siempre.
        self.assertIsNone(self.vendedora._mfa_url())
        self.assertIsNone(self.portal._mfa_url())
        # Alcance «internos»: todo el personal, nunca los clientes del portal.
        self._obligatorio('1', 'internos')
        self.assertEqual(self.vendedora._mfa_url(), RUTA_ENROLAR)
        self.assertIsNone(self.portal._mfa_url())
        # Un alcance mal escrito cae en «admins» (lo más restringido que no deja fuera a nadie más).
        self._obligatorio('1', 'todos')
        self.assertEqual(self.admin._mfa_url(), RUTA_ENROLAR)
        self.assertIsNone(self.vendedora._mfa_url())
        # Ya enrolado: el paso normal de Odoo (pedir el código), no enrolar de nuevo.
        self.admin.sudo().totp_secret = _secreto()
        self.assertEqual(self.admin._mfa_url(), '/web/login/totp')

    def test_llave_de_acceso_no_exime_al_entrar_con_clave(self):
        self._obligatorio('1', 'admins')
        self.env['auth.passkey.key'].with_user(self.admin).sudo().create({
            'name': 'Llave de prueba', 'credential_identifier': 'llave-prueba', 'public_key': 'cHJ1ZWJh'})
        self.assertTrue(self.admin.sudo().auth_passkey_key_ids)
        self.assertTrue(self.admin._dcasa_debe_enrolar())

    # --- Claves de API (Brian por MCP) con el doble factor ------------------------------

    def test_claves_de_api_siguen_funcionando_con_2fa(self):
        self.admin.sudo().totp_secret = _secreto()
        self._obligatorio('1', 'internos')
        Claves = self.env['res.users.apikeys'].with_user(self.admin)
        vence = datetime.now() + timedelta(days=30)
        clave_brian = Claves._generate('brian', 'Brian MCP', vence)
        clave_global = Claves._generate(None, 'Integración', vence)
        # Lo que hace /brian/mcp: alcance «brian» o global.
        self.assertEqual(Claves._check_credentials(scope='brian', key=clave_brian), self.admin.id)
        self.assertEqual(Claves._check_credentials(scope='brian', key=clave_global), self.admin.id)
        # RPC no interactivo: la clave de API vale; la contraseña ya no (solo claves con 2FA).
        usuario = self.admin.with_user(self.admin)
        info = usuario._check_credentials(
            {'type': 'password', 'login': 'seg_admin', 'password': clave_global}, {'interactive': False})
        self.assertEqual(info['auth_method'], 'apikey')
        with self.assertRaises(AccessDenied):
            usuario._check_credentials(
                {'type': 'password', 'login': 'seg_admin', 'password': 'seg_admin'}, {'interactive': False})
        # Interactivo (pantalla de login): la clave sigue siendo el primer factor.
        info = usuario._check_credentials(
            {'type': 'password', 'login': 'seg_admin', 'password': 'seg_admin'}, {'interactive': True})
        self.assertEqual(info['auth_method'], 'password')

    # --- Bloqueo progresivo -------------------------------------------------------------

    def test_bloqueo_progresivo(self):
        self.ICP.set_param('base.login_cooldown_after', 5)
        self.ICP.set_param('base.login_cooldown_duration', 60)
        self.ICP.set_param('dcasa_seguridad.bloqueo_tope_s', 1800)
        Usuarios = self.env['res.users']
        ahora = datetime.now()

        def espera(fallos, hace_s):
            return Usuarios._on_login_cooldown(fallos, ahora - timedelta(seconds=hace_s))

        self.assertFalse(espera(4, 1))          # menos de 5 fallos: sin espera
        self.assertTrue(espera(5, 30))          # 5 fallos: 60 s
        self.assertFalse(espera(5, 61))
        self.assertTrue(espera(6, 100))         # 6 fallos: 120 s
        self.assertFalse(espera(6, 121))
        self.assertTrue(espera(8, 400))         # 8 fallos: 480 s
        self.assertTrue(espera(40, 1700))       # tope: 30 min
        self.assertFalse(espera(40, 1801))
        self.ICP.set_param('base.login_cooldown_after', 0)
        self.assertFalse(espera(100, 1))        # 0 = desactivado (como en Odoo)

    # --- Sesiones de administrador ------------------------------------------------------

    def test_sesiones_de_admin_vencen(self):
        aplicar_sesiones_admin(self.env)
        grupo = self.env.ref('base.group_system')
        self.assertEqual(grupo.lock_timeout, 12 * 60)
        self.assertTrue(grupo.lock_timeout_mfa)
        self.assertEqual(grupo.lock_timeout_inactivity, 60)
        self.assertEqual(self.admin._get_lock_timeouts()['lock_timeout'], [(12 * 3600, True)])
        # La vendedora no hereda el vencimiento de los administradores.
        self.assertEqual(self.vendedora._get_lock_timeouts()['lock_timeout'], [])
        aplicar_sesiones_admin(self.env, horas=0, minutos=0)
        self.assertFalse(grupo.lock_timeout)
        self.assertFalse(grupo.lock_timeout_inactivity)

    # --- Registro y avisos --------------------------------------------------------------

    def test_registro_solo_lectura_y_purga(self):
        Acceso = self.env['dcasa.seguridad.acceso']
        fila = Acceso._registrar({'login': 'x', 'resultado': 'fallo', 'ip': '1.2.3.4'})
        self.assertTrue(Acceso.with_user(self.admin).search([('login', '=', 'x')]))
        for usuario in (self.vendedora, self.admin):
            with self.assertRaises(AccessError):
                Acceso.with_user(usuario).create({'login': 'y', 'resultado': 'ok'})
        with self.assertRaises(AccessError):
            fila.with_user(self.admin).unlink()
        self.env.cr.execute("UPDATE dcasa_seguridad_acceso SET create_date = now() - interval '181 days' "
                            "WHERE id = %s", [fila.id])
        self.assertGreaterEqual(Acceso._purgar(), 1)
        self.assertFalse(fila.exists())

    def test_aviso_telegram_a_admins_vinculados(self):
        if 'brian.telegram.enlace' not in self.env:
            self.skipTest('dcasa_brian no está instalado: no hay canal de Telegram')
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.admin.id, 'chat_id': '777'})
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.vendedora.id, 'chat_id': '888'})
        with patch.object(ResUsers, '_dcasa_enviar_aviso', autospec=True) as enviar:
            self.env['res.users']._dcasa_avisar_admins(self.admin, 'hola')
            enviar.assert_called_once()
            self.assertEqual(enviar.call_args.args[1], ['777'])  # la vendedora no recibe avisos de admin
            enviar.reset_mock()
            self.ICP.set_param('dcasa_seguridad.aviso_telegram', '0')
            self.env['res.users']._dcasa_avisar_admins(self.admin, 'hola')
            enviar.assert_not_called()

    def test_aviso_operacion_por_el_mismo_canal(self):
        """Disco/memoria/base (dcasa_base) avisan a los administradores vinculados por Telegram."""
        Users = self.env['res.users']
        with patch.object(ResUsers, '_dcasa_enviar_aviso', autospec=True) as enviar:
            if 'brian.telegram.enlace' not in self.env:
                # Sin dcasa_brian no hay canal: lo dice (False) y no intenta mandar nada.
                self.assertFalse(Users._dcasa_avisar_operacion('disco al 85 %'))
                enviar.assert_not_called()
                return
            self.assertFalse(Users._dcasa_avisar_operacion('nadie vinculado'))
            self.env['brian.telegram.enlace'].sudo().create({'user_id': self.admin.id, 'chat_id': '777'})
            self.env['brian.telegram.enlace'].sudo().create({'user_id': self.vendedora.id, 'chat_id': '888'})
            self.assertTrue(Users._dcasa_avisar_operacion('disco al 85 %'))
            enviar.assert_called_once()
            self.assertEqual(enviar.call_args.args[1:], (['777'], 'disco al 85 %'))
            enviar.reset_mock()
            self.ICP.set_param('dcasa_seguridad.aviso_operacion', '0')
            self.assertFalse(Users._dcasa_avisar_operacion('disco al 85 %'))
            enviar.assert_not_called()
            # El aviso de inicio de sesión tiene su propio interruptor: sigue saliendo.
            Users._dcasa_avisar_admins(self.admin, 'entró admin')
            enviar.assert_called_once()

    # --- robots.txt ---------------------------------------------------------------------

    def test_robots_ia(self):
        self.ICP.set_param('dcasa_seguridad.robots_ia', '')
        self.assertEqual(politica_robots(self.env), 'equilibrada')
        self.ICP.set_param('dcasa_seguridad.robots_ia', 'inventada')
        self.assertEqual(politica_robots(self.env), 'equilibrada')
        equilibrada = texto_robots_ia('equilibrada')
        for agente in IA_ENTRENAMIENTO:
            self.assertIn(f'User-agent: {agente}\nDisallow: /', equilibrada)
        for agente in IA_BUSQUEDA:
            self.assertNotIn(agente, equilibrada)
        self.assertIn('ai-train=no', equilibrada)
        cerrada = texto_robots_ia('cerrada')
        self.assertIn('User-agent: OAI-SearchBot\nDisallow: /', cerrada)
        abierta = texto_robots_ia('abierta')
        self.assertNotIn('Disallow', abierta)
        # Buscadores y previsualizadores de enlaces (WhatsApp, Facebook) nunca se bloquean.
        for texto in (equilibrada, cerrada, abierta):
            for agente in ('Googlebot', 'Bingbot', 'facebookexternalhit', 'meta-externalfetcher', 'WhatsApp'):
                self.assertNotIn(agente, texto)
