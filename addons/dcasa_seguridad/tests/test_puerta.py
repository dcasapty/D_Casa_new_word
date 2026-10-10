"""La puerta del equipo (models/puerta.py, edge/src/puerta.ts): el personal solo entra con la puerta abierta."""
import hmac
import os
import re
import time
from hashlib import sha256
from unittest.mock import patch

from odoo import http
from odoo.addons.dcasa_seguridad.models import puerta
from odoo.addons.dcasa_seguridad.models.res_users import ResUsers
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import HOST, Opener, get_db_name
from odoo.tools import mute_logger

SECRETO = 's' * 40


def cabecera(correo, vence=None, secreto=SECRETO, firmar_correo=None):
    """Lo mismo que arma el borde (edge/src/puerta.ts › cabeceraParaOdoo)."""
    vence = int(vence if vence is not None else time.time() + 3600)
    firma = hmac.new(secreto.encode(), f'cabecera|{firmar_correo or correo}|{vence}'.encode(), sha256).hexdigest()
    return f'{correo}|{vence}|{firma}'


def entorno(modo='1', secreto=SECRETO, correo='0'):
    return patch.dict(os.environ, {
        'DCASA_PUERTA_OBLIGATORIA': modo, 'DCASA_PUERTA_SECRETO': secreto, 'DCASA_PUERTA_EXIGIR_CORREO': correo})


@tagged('post_install', '-at_install')
class TestPuertaFunciones(TransactionCase):

    def test_modo_apagado_por_defecto(self):
        with patch.dict(os.environ, {}, clear=False):
            for nombre in ('DCASA_PUERTA_OBLIGATORIA', 'DCASA_PUERTA_SECRETO', 'DCASA_PUERTA_EXIGIR_CORREO'):
                os.environ.pop(nombre, None)
            self.assertEqual(puerta.modo(), puerta.APAGADA)
            self.assertFalse(puerta.exigir_correo())

    def test_el_modo_respeta_los_tres_valores(self):
        for valor in ('0', 'avisar', '1'):
            with entorno(valor):
                self.assertEqual(puerta.modo(), valor)
        with entorno('AVISAR'):
            self.assertEqual(puerta.modo(), 'avisar')

    def test_un_valor_raro_o_sin_secreto_no_deja_a_nadie_fuera(self):
        for valor in ('2', 'si', 'true'):
            with entorno(valor):
                self.assertEqual(puerta.modo(), puerta.APAGADA)
        for secreto in ('', 'corto', 'x' * 31):
            with entorno('1', secreto=secreto):
                self.assertEqual(puerta.modo(), puerta.APAGADA, 'Sin secreto no se puede verificar: no se exige')

    def test_cabecera_valida_devuelve_el_correo_en_minusculas(self):
        with entorno():
            self.assertEqual(puerta.correo_de_la_puerta(cabecera('Dueña@Example.com')), 'dueña@example.com')

    def test_cabecera_mala_no_abre(self):
        with entorno():
            ahora = int(time.time())
            casos = {
                'vacía': '',
                'ninguna': None,
                'vencida': cabecera('a@example.com', vence=ahora - 5),
                'justo ahora': cabecera('a@example.com', vence=ahora),
                'otro secreto': cabecera('a@example.com', secreto='z' * 40),
                'otro correo firmado': cabecera('jefa@example.com', firmar_correo='peon@example.com'),
                'sin firma': f'a@example.com|{ahora + 60}|',
                'firma en mayúsculas': cabecera('a@example.com').upper(),
                'dos partes': f'a@example.com|{ahora + 60}',
                'cuatro partes': cabecera('a@example.com') + '|x',
                'vence con letras': f'a@example.com|abc|{"0" * 64}',
                'correo sin arroba': cabecera('aexample.com'),
                'correo con espacio': cabecera('a b@example.com'),
            }
            for nombre, valor in casos.items():
                self.assertIsNone(puerta.correo_de_la_puerta(valor), nombre)

    def test_sin_secreto_nada_se_verifica(self):
        valor = cabecera('a@example.com')
        with entorno('1', secreto=''):
            self.assertIsNone(puerta.correo_de_la_puerta(valor))

    def test_problema_sin_puerta_y_con_correo_distinto(self):
        usuario = new_test_user(self.env, 'puerta_func', groups='base.group_user', email='Equipo@Example.com')
        with entorno(correo='0'):
            self.assertEqual(puerta.problema(None, usuario), puerta.SIN_PUERTA)
            self.assertIsNone(puerta.problema(cabecera('cualquiera@example.com'), usuario))
        with entorno(correo='1'):
            self.assertEqual(puerta.problema(cabecera('cualquiera@example.com'), usuario), puerta.CORREO_DISTINTO)
            self.assertIsNone(puerta.problema(cabecera('equipo@example.com'), usuario))

    def test_el_correo_exigido_tambien_puede_ser_el_usuario(self):
        usuario = new_test_user(self.env, 'jefa@example.com', groups='base.group_user')
        with entorno(correo='1'):
            self.assertIsNone(puerta.problema(cabecera('jefa@example.com'), usuario))
            self.assertEqual(puerta.problema(cabecera('otra@example.com'), usuario), puerta.CORREO_DISTINTO)


@tagged('post_install', '-at_install')
class TestPuertaHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.ICP.set_param('cf.turnstile_site_key', '')
        cls.ICP.set_param('cf.turnstile_secret_key', '')
        cls.ICP.set_param('dcasa_seguridad.2fa_obligatorio', '0')
        cls.vendedora = new_test_user(cls.env, 'puerta_vendedora', groups='base.group_user',
                                      email='vendedora@example.com')
        cls.admin = new_test_user(cls.env, 'puerta_admin', groups='base.group_system', email='admin@example.com')
        cls.cliente = new_test_user(cls.env, 'puerta_cliente', groups='base.group_portal',
                                    email='cliente@example.com')

    def setUp(self):
        super().setUp()
        self.session = http.root.session_store.new()
        self.session.update(http.get_default_session(), db=get_db_name())
        self.opener = Opener(self)
        self.opener.cookies.set('session_id', self.session.sid, domain=HOST, path='/')
        self.env.registry._login_failures = None

    def _entrar(self, login, header=None):
        headers = {puerta.CABECERA: header} if header else None
        return self.url_open('/web/login', data={
            'login': login, 'password': login, 'csrf_token': http.Request.csrf_token(self)}, headers=headers)

    @staticmethod
    def _error_de_login(respuesta):
        encontrado = re.search(r'<p class="alert alert-danger"[^>]*>\s*(.*?)\s*</p>', respuesta.text, re.S)
        return encontrado.group(1) if encontrado else ''

    def _registros(self, usuario, resultado):
        return self.env['dcasa.seguridad.acceso'].search([
            ('user_id', '=', usuario.id), ('resultado', '=', resultado)])

    def _panel(self, header=None):
        headers = {puerta.CABECERA: header} if header else None
        return self.url_open('/odoo', headers=headers, allow_redirects=False)

    # --- apagada ---------------------------------------------------------------------------------------------

    def test_apagada_no_cambia_nada(self):
        with entorno('0'):
            self.assertEqual(self._entrar('puerta_vendedora').request.path_url, '/odoo')
        self.assertFalse(self._registros(self.vendedora, puerta.SIN_PUERTA))

    # --- obligatoria: el inicio de sesión --------------------------------------------------------------------

    def test_el_personal_con_clave_correcta_pero_sin_puerta_no_entra(self):
        with entorno('1'), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_vendedora')
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertTrue(respuesta.request.path_url.startswith('/web/login'))
        # El mismo mensaje que una clave equivocada: no le dice a quien prueba que la clave estaba bien.
        with mute_logger('odoo.addons.base.models.res_users', 'odoo.http'):
            equivocada = self.url_open('/web/login', data={
                'login': 'puerta_vendedora', 'password': 'otra-clave', 'csrf_token': http.Request.csrf_token(self)})
        self.assertEqual(self._error_de_login(respuesta), self._error_de_login(equivocada))
        self.assertTrue(self._error_de_login(respuesta))
        with entorno('1'):
            panel = self._panel()
        self.assertIn(panel.status_code, (302, 303), 'No quedó ninguna sesión')
        registro = self._registros(self.vendedora, puerta.SIN_PUERTA)
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.metodo, 'bloqueado')
        self.assertFalse(self._registros(self.vendedora, 'ok'))

    def test_con_la_puerta_abierta_entra_y_queda_el_correo_en_el_registro(self):
        with entorno('1'):
            respuesta = self._entrar('puerta_vendedora', cabecera('vendedora@example.com'))
        self.assertEqual(respuesta.request.path_url, '/odoo')
        registro = self._registros(self.vendedora, 'ok')
        self.assertEqual(registro.puerta, 'vendedora@example.com')

    def test_una_cabecera_falsificada_no_abre(self):
        falsa = cabecera('vendedora@example.com', secreto='z' * 40)
        with entorno('1'), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_vendedora', falsa)
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertEqual(len(self._registros(self.vendedora, puerta.SIN_PUERTA)), 1)

    def test_un_cliente_del_portal_nunca_pasa_por_la_puerta(self):
        with entorno('1'):
            respuesta = self._entrar('puerta_cliente')
        self.assertFalse(self._registros(self.cliente, puerta.SIN_PUERTA))
        self.assertTrue(self._registros(self.cliente, 'ok'))
        self.assertNotIn('Wrong login/password', respuesta.text)

    def test_el_administrador_sin_puerta_tampoco_entra_y_se_avisa(self):
        with entorno('1'), patch.object(ResUsers, '_dcasa_avisar_admins', autospec=True) as avisar, \
                mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_admin')
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertTrue(self._registros(self.admin, puerta.SIN_PUERTA).es_admin)
        avisar.assert_called_once()
        self.assertIn('no pasó por la puerta', avisar.call_args.args[2])
        self.assertIn('no entró', avisar.call_args.args[2])

    # --- avisar ----------------------------------------------------------------------------------------------

    def test_en_modo_avisar_entra_pero_queda_anotado(self):
        with entorno('avisar'), mute_logger('odoo.addons.dcasa_seguridad.models.res_users'):
            respuesta = self._entrar('puerta_vendedora')
        self.assertEqual(respuesta.request.path_url, '/odoo')
        registro = self._registros(self.vendedora, puerta.SIN_PUERTA)
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.metodo, 'solo aviso')
        with entorno('avisar'):
            self.assertEqual(self._panel().status_code, 200, 'En modo aviso la sesión sigue')

    # --- obligatoria: la sesión ------------------------------------------------------------------------------

    def test_la_sesion_del_personal_solo_vale_con_la_puerta(self):
        abierta = cabecera('vendedora@example.com')
        with entorno('1'):
            self.assertEqual(self._entrar('puerta_vendedora', abierta).request.path_url, '/odoo')
            self.assertEqual(self._panel(abierta).status_code, 200)
            # La misma sesión, sin la cabecera del borde (cookie robada, puerta vencida): se cierra.
            sin = self._panel()
            self.assertIn(sin.status_code, (302, 303))
            self.assertIn('/web/login', sin.headers.get('Location', ''))
            # Y ya no vuelve sola: aun con la cabecera, hay que iniciar sesión otra vez.
            otra = self._panel(abierta)
            self.assertIn(otra.status_code, (302, 303))

    def test_la_sesion_de_un_cliente_no_se_toca(self):
        with entorno('1'):
            self._entrar('puerta_cliente')
            mi_cuenta = self.url_open('/my', allow_redirects=False)
        self.assertEqual(mi_cuenta.status_code, 200)

    # --- amarre del correo -----------------------------------------------------------------------------------

    def test_exigir_correo_amarra_la_puerta_a_la_cuenta(self):
        with entorno('1', correo='1'), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            ajeno = self._entrar('puerta_vendedora', cabecera('admin@example.com'))
        self.assertNotEqual(ajeno.request.path_url, '/odoo')
        registro = self._registros(self.vendedora, puerta.CORREO_DISTINTO)
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.puerta, 'admin@example.com')
        with entorno('1', correo='1'):
            propio = self._entrar('puerta_vendedora', cabecera('Vendedora@Example.com'))
        self.assertEqual(propio.request.path_url, '/odoo')

    def test_sin_exigir_correo_cualquier_correo_del_equipo_basta(self):
        with entorno('1', correo='0'):
            respuesta = self._entrar('puerta_vendedora', cabecera('admin@example.com'))
        self.assertEqual(respuesta.request.path_url, '/odoo')
