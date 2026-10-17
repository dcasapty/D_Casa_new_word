"""La puerta del equipo (models/puerta.py, edge/src/puerta.ts): el personal solo entra con la puerta abierta."""
import base64
import hmac
import json
import os
import re
import time
from datetime import timedelta
from hashlib import sha256
from unittest.mock import patch

from odoo import fields, http
from odoo.addons.auth_totp.models.totp import hotp
from odoo.addons.dcasa_seguridad.models import puerta
from odoo.addons.dcasa_seguridad.models.ir_http import INICIO
from odoo.addons.dcasa_seguridad.models.parametros import aplicar_sesiones_admin
from odoo.addons.dcasa_seguridad.models.res_users import RUTA_ENROLAR, ResUsers
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import HOST, Opener, get_db_name
from odoo.tools import mute_logger

SECRETO = 's' * 40


def _firma(mensaje, secreto=SECRETO):
    return hmac.new(secreto.encode(), mensaje.encode(), sha256).hexdigest()


def cabecera(correo, vence=None, secreto=SECRETO, firmar_correo=None):
    """Lo mismo que arma el borde (edge/src/puerta.ts › cabeceraParaOdoo)."""
    vence = int(vence if vence is not None else time.time() + 3600)
    return f'{correo}|{vence}|{_firma(f"cabecera|{firmar_correo or correo}|{vence}", secreto)}'


def modo_firmado(modo='1', exigir_correo=False, vence=None, secreto=SECRETO):
    """Lo mismo que arma el borde (edge/src/puerta.ts › cabeceraDeModo)."""
    vence = int(vence if vence is not None else time.time() + 300)
    exigir = '1' if exigir_correo else '0'
    return f'{modo}|{exigir}|{vence}|{_firma(f"modo|{modo}|{exigir}|{vence}", secreto)}'


def entorno(secreto=SECRETO):
    return patch.dict(os.environ, {'DCASA_PUERTA_SECRETO': secreto})


@tagged('post_install', '-at_install')
class TestPuertaFunciones(TransactionCase):

    def test_sin_secreto_nada_se_verifica_ni_se_exige(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('DCASA_PUERTA_SECRETO', None)
            self.assertEqual(puerta.ajustes_de_la_peticion(modo_firmado('1')), (puerta.APAGADA, False))
            self.assertIsNone(puerta.correo_de_la_puerta(cabecera('a@example.com')))
        for secreto in ('corto', 'x' * 31):
            with entorno(secreto):
                self.assertEqual(puerta.ajustes_de_la_peticion(modo_firmado('1', secreto=secreto)),
                                 (puerta.APAGADA, False), 'Con un secreto corto no se exige nada')

    def test_el_modo_firmado_se_lee_tal_cual(self):
        with entorno():
            self.assertEqual(puerta.ajustes_de_la_peticion(modo_firmado('1', True)), ('1', True))
            self.assertEqual(puerta.ajustes_de_la_peticion(modo_firmado('avisar', False)), ('avisar', False))
            self.assertEqual(puerta.ajustes_de_la_peticion(modo_firmado('0', True)), ('0', True))

    def test_un_modo_que_no_se_puede_verificar_no_exige_nada(self):
        """Sin cabecera (lo que nace dentro del contenedor, p. ej. un PDF) o con una mala: nunca deja a nadie fuera."""
        ahora = int(time.time())
        casos = {
            'ninguna': None, 'vacía': '', 'otro secreto': modo_firmado('1', secreto='z' * 40),
            'vencida': modo_firmado('1', vence=ahora - 5), 'modo inventado': modo_firmado('2'),
            'sin firma': f'1|0|{ahora + 60}|', 'tres partes': f'1|0|{ahora + 60}',
            'cinco partes': modo_firmado('1') + '|x',
            'firma en mayúsculas': modo_firmado('1').upper(), 'vence con letras': f'1|0|abc|{"0" * 64}',
            'vence con superíndice': f'1|0|²|{"0" * 64}',
        }
        with entorno():
            for nombre, valor in casos.items():
                self.assertEqual(puerta.ajustes_de_la_peticion(valor), (puerta.APAGADA, False), nombre)

    def test_cabecera_valida_devuelve_el_correo_en_minusculas(self):
        with entorno():
            self.assertEqual(puerta.correo_de_la_puerta(cabecera('Duena@Example.com')), 'duena@example.com')

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
                'vence con superíndice': f'a@example.com|²|{"0" * 64}',
                'correo sin arroba': cabecera('aexample.com'),
                'correo con espacio': cabecera('a b@example.com'),
                'correo con ñ': cabecera('josé@example.com'),
                'salto de línea al final': cabecera('a@example.com') + '\n',
            }
            for nombre, valor in casos.items():
                self.assertIsNone(puerta.correo_de_la_puerta(valor), nombre)

    def test_la_firma_de_la_cabecera_y_la_del_modo_no_se_intercambian(self):
        """Dominio de cada firma: una no vale por la otra."""
        with entorno():
            vence = int(time.time()) + 300
            self.assertIsNone(puerta.correo_de_la_puerta(f'a@example.com|{vence}|{_firma(f"modo|1|0|{vence}")}'))
            self.assertEqual(puerta.ajustes_de_la_peticion(f'1|0|{vence}|{_firma(f"cabecera|1|{vence}")}'),
                             (puerta.APAGADA, False))

    def test_problema_sin_puerta_y_con_correo_distinto(self):
        usuario = new_test_user(self.env, 'puerta_func', groups='base.group_user', email='Equipo@Example.com')
        with entorno():
            self.assertEqual(puerta.problema(None, usuario), puerta.SIN_PUERTA)
            self.assertIsNone(puerta.problema(cabecera('cualquiera@example.com'), usuario, exigir_correo=False))
            self.assertEqual(puerta.problema(cabecera('cualquiera@example.com'), usuario, exigir_correo=True),
                             puerta.CORREO_DISTINTO)
            self.assertIsNone(puerta.problema(cabecera('equipo@example.com'), usuario, exigir_correo=True))

    def test_el_correo_exigido_tambien_puede_ser_el_usuario(self):
        usuario = new_test_user(self.env, 'jefa@example.com', groups='base.group_user')
        with entorno():
            self.assertIsNone(puerta.problema(cabecera('jefa@example.com'), usuario, exigir_correo=True))
            self.assertEqual(puerta.problema(cabecera('otra@example.com'), usuario, exigir_correo=True),
                             puerta.CORREO_DISTINTO)


@tagged('post_install', '-at_install')
class TestPuertaYApp(TransactionCase):
    """El código de la app es SIEMPRE obligatorio para el personal (pedido de la dueña)."""

    def test_la_llave_de_acceso_ya_no_se_salta_el_codigo_de_la_app(self):
        interno = new_test_user(self.env, 'llave_interno', groups='base.group_user')
        cliente = new_test_user(self.env, 'llave_cliente', groups='base.group_portal')
        sin_segundo_paso = {'uid': 0, 'auth_method': 'passkey', 'mfa': 'skip'}
        ruta = 'odoo.addons.auth_passkey.models.res_users.ResUsers._check_credentials'
        credencial = {'type': 'webauthn', 'webauthn_response': '{}'}
        with patch(ruta, return_value=dict(sin_segundo_paso)):
            self.assertEqual(interno._check_credentials(credencial, {'interactive': True})['mfa'], 'default')
            self.assertEqual(cliente._check_credentials(credencial, {'interactive': True})['mfa'], 'skip',
                             'Los clientes no cambian')

    def test_sin_llave_de_acceso_el_resultado_no_se_toca(self):
        interno = new_test_user(self.env, 'llave_clave', groups='base.group_user')
        ruta = 'odoo.addons.auth_passkey.models.res_users.ResUsers._check_credentials'
        with patch(ruta, return_value={'uid': 1, 'auth_method': 'password', 'mfa': 'default'}):
            self.assertEqual(interno._check_credentials({'type': 'password'}, {})['mfa'], 'default')

    def test_el_dispositivo_de_confianza_no_vale_para_el_personal(self):
        """«No volver a preguntar en este dispositivo» (90 días) saltaría el código; no para el personal."""
        Dispositivo = self.env['auth_totp.device']
        interno = new_test_user(self.env, 'confianza_interno', groups='base.group_user')
        cliente = new_test_user(self.env, 'confianza_cliente', groups='base.group_portal')
        vence = fields.Datetime.now() + timedelta(days=30)
        for usuario, vale in ((interno, False), (cliente, True)):
            llave = Dispositivo.with_user(usuario).sudo()._generate('browser', 'navegador de prueba', vence)
            self.assertEqual(Dispositivo._check_credentials_for_uid(scope='browser', key=llave, uid=usuario.id), vale)


@tagged('post_install', '-at_install')
class TestPuertaHttp(HttpCase):

    SEMILLA = base64.b32encode(b'dcasa-puerta-1234567').decode()

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
        cls.sin_app = new_test_user(cls.env, 'puerta_sin_app', groups='base.group_user', email='sinapp@example.com')
        cls.cliente = new_test_user(cls.env, 'puerta_cliente', groups='base.group_portal',
                                    email='cliente@example.com')
        for usuario in (cls.vendedora, cls.admin):    # con la app ya enrolada, como el personal de verdad
            usuario.sudo().totp_secret = cls.SEMILLA

    def setUp(self):
        super().setUp()
        self.session = http.root.session_store.new()
        self.session.update(http.get_default_session(), db=get_db_name())
        self.opener = Opener(self)
        self.opener.cookies.set('session_id', self.session.sid, domain=HOST, path='/')
        self.env.registry._login_failures = None
        self._paso = 0

    @staticmethod
    def _cabeceras(puerta_abierta=None, modo='1', exigir_correo=False, extra=None):
        """Lo que el borde le manda a Odoo; ``modo=None`` = una petición que no pasó por el borde."""
        cabeceras = dict(extra or {})
        if puerta_abierta:
            cabeceras[puerta.CABECERA] = puerta_abierta
        if modo is not None:
            cabeceras[puerta.CABECERA_MODO] = modo_firmado(modo, exigir_correo)
        return cabeceras

    def _codigo(self):
        """Un código de la app distinto cada vez (Odoo no acepta el mismo dos veces)."""
        self._paso += 1
        return str(hotp(base64.b32decode(self.SEMILLA), int(time.time() / 30) + self._paso - 1)).zfill(6)

    def _entrar(self, login, abierta=None, modo='1', exigir_correo=False, ruta='/master', con_codigo=True):
        """Inicia sesión como el personal: la página del equipo y, si Odoo lo pide, el código de la app."""
        cabeceras = self._cabeceras(abierta, modo, exigir_correo)
        respuesta = self.url_open(ruta, data={
            'login': login, 'password': login, 'csrf_token': http.Request.csrf_token(self)}, headers=cabeceras)
        if con_codigo and respuesta.request.path_url.startswith('/web/login/totp'):
            respuesta = self.url_open('/web/login/totp', data={
                'totp_token': self._codigo(), 'csrf_token': http.Request.csrf_token(self)}, headers=cabeceras)
        return respuesta

    @staticmethod
    def _error_de_login(respuesta):
        encontrado = re.search(r'<p class="alert alert-danger"[^>]*>\s*(.*?)\s*</p>', respuesta.text, re.S)
        return encontrado.group(1) if encontrado else ''

    def _registros(self, usuario, resultado):
        return self.env['dcasa.seguridad.acceso'].search([
            ('user_id', '=', usuario.id), ('resultado', '=', resultado)])

    def _panel(self, abierta=None, modo='1', exigir_correo=False):
        return self.url_open('/odoo', headers=self._cabeceras(abierta, modo, exigir_correo), allow_redirects=False)

    def _datos(self, abierta=None, modo='1', exigir_correo=False):
        """Una llamada de datos del cliente web (``auth='user'``): lo que hace el panel todo el tiempo."""
        cuerpo = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {
            'model': 'res.partner', 'method': 'search_read', 'args': [[]], 'kwargs': {'fields': ['name'], 'limit': 1}}})
        cabeceras = self._cabeceras(abierta, modo, exigir_correo, extra={'Content-Type': 'application/json'})
        return self.url_open('/web/dataset/call_kw/res.partner/search_read', data=cuerpo, headers=cabeceras).json()

    # --- la página /master -----------------------------------------------------------------------------------

    def test_la_pagina_del_equipo_ofrece_clave_y_llave_de_acceso_y_no_se_indexa(self):
        respuesta = self.url_open('/master', headers=self._cabeceras(cabecera('vendedora@example.com')))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Acceso del equipo', respuesta.text)
        self.assertIn('action="/master"', respuesta.text)
        self.assertIn('passkey_login_link', respuesta.text, 'Con llave de acceso, como pidió la dueña')
        self.assertIn('name="webauthn_response"', respuesta.text)
        self.assertIn('Google Authenticator', respuesta.text)
        self.assertNotIn('/web/signup', respuesta.text, 'Sin "crear cuenta" ni "restablecer": es solo para el equipo')
        self.assertIn('noindex', respuesta.headers.get('X-Robots-Tag', ''))
        self.assertIn('no-store', respuesta.headers.get('Cache-Control', ''))

    def test_con_sesion_abierta_la_pagina_del_equipo_manda_al_panel(self):
        abierta = cabecera('vendedora@example.com')
        with entorno():
            self.assertEqual(self._entrar('puerta_vendedora', abierta).request.path_url, '/odoo')
            visita = self.url_open('/master', headers=self._cabeceras(abierta), allow_redirects=False)
        self.assertIn(visita.status_code, (302, 303))
        self.assertEqual(visita.headers.get('Location'), '/odoo')

    def test_el_login_publico_sigue_siendo_para_clientes_y_socios(self):
        with entorno():
            publico = self.url_open('/web/login', headers=self._cabeceras())
        self.assertIn('action="/web/login"', publico.text)
        self.assertNotIn('Acceso del equipo', publico.text)

    # --- apagada o sin cabecera del modo --------------------------------------------------------------------

    def test_el_modo_cero_no_cambia_nada(self):
        with entorno():
            self.assertEqual(self._entrar('puerta_vendedora', modo='0', ruta='/web/login').request.path_url, '/odoo')
        self.assertFalse(self._registros(self.vendedora, puerta.SIN_PUERTA))
        self.assertFalse(self._registros(self.vendedora, puerta.LOGIN_PUBLICO))

    def test_una_peticion_que_no_paso_por_el_borde_no_exige_nada(self):
        """Lo que nace dentro del contenedor (p. ej. el PDF de una factura con la sesión de quien lo pidió)."""
        with entorno():
            self.assertEqual(self._entrar('puerta_vendedora', modo=None, ruta='/web/login').request.path_url, '/odoo')
            self.assertIn('result', self._datos(modo=None), 'La sesión sigue valiendo sin cabecera del modo')
        self.assertFalse(self._registros(self.vendedora, puerta.SIN_PUERTA))

    def test_un_modo_falsificado_no_exige_nada(self):
        falso = {puerta.CABECERA_MODO: modo_firmado('1', secreto='z' * 40)}
        with entorno():
            respuesta = self.url_open('/web/login', data={
                'login': 'puerta_vendedora', 'password': 'puerta_vendedora',
                'csrf_token': http.Request.csrf_token(self)}, headers=falso)
            if respuesta.request.path_url.startswith('/web/login/totp'):
                respuesta = self.url_open('/web/login/totp', data={
                    'totp_token': self._codigo(), 'csrf_token': http.Request.csrf_token(self)}, headers=falso)
        self.assertEqual(respuesta.request.path_url, '/odoo')

    # --- obligatoria: el inicio de sesión --------------------------------------------------------------------

    def test_el_personal_con_clave_correcta_pero_sin_puerta_no_entra(self):
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_vendedora', con_codigo=False)
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertFalse(respuesta.request.path_url.startswith('/web/login/totp'), 'Ni el código se le pide')
        # El mismo mensaje que una clave equivocada: no le dice a quien prueba que la clave estaba bien.
        with entorno(), mute_logger('odoo.addons.base.models.res_users', 'odoo.http'):
            equivocada = self.url_open('/master', data={
                'login': 'puerta_vendedora', 'password': 'otra-clave', 'csrf_token': http.Request.csrf_token(self)},
                headers=self._cabeceras(cabecera('vendedora@example.com')))
        self.assertEqual(self._error_de_login(respuesta), self._error_de_login(equivocada))
        self.assertTrue(self._error_de_login(respuesta))
        with entorno():
            panel = self._panel()
        self.assertIn(panel.status_code, (302, 303), 'No quedó ninguna sesión')
        registro = self._registros(self.vendedora, puerta.SIN_PUERTA)
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.metodo, 'bloqueado')
        self.assertFalse(self._registros(self.vendedora, 'ok'))

    def test_con_la_puerta_abierta_entra_y_queda_el_correo_en_el_registro(self):
        with entorno():
            respuesta = self._entrar('puerta_vendedora', cabecera('vendedora@example.com'))
        self.assertEqual(respuesta.request.path_url, '/odoo')
        registro = self._registros(self.vendedora, 'ok')
        self.assertEqual(registro.puerta, 'vendedora@example.com')

    def test_el_personal_no_inicia_sesion_por_el_login_publico_ni_con_la_puerta_abierta(self):
        abierta = cabecera('vendedora@example.com')
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_vendedora', abierta, ruta='/web/login', con_codigo=False)
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertFalse(respuesta.request.path_url.startswith('/web/login/totp'))
        registro = self._registros(self.vendedora, puerta.LOGIN_PUBLICO)
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.metodo, 'bloqueado')
        self.assertEqual(registro.puerta, 'vendedora@example.com')
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            # La ruta interna de Odoo para iniciar sesión por JSON tampoco sirve para el personal.
            cuerpo = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {
                'db': get_db_name(), 'login': 'puerta_vendedora', 'password': 'puerta_vendedora'}})
            rpc = self.url_open('/web/session/authenticate', data=cuerpo, headers=self._cabeceras(
                abierta, extra={'Content-Type': 'application/json'})).json()
        self.assertNotIn('result', rpc)

    def test_una_cabecera_falsificada_no_abre(self):
        falsa = cabecera('vendedora@example.com', secreto='z' * 40)
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_vendedora', falsa, con_codigo=False)
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertEqual(len(self._registros(self.vendedora, puerta.SIN_PUERTA)), 1)

    def test_un_cliente_del_portal_nunca_pasa_por_la_puerta_y_usa_el_login_publico(self):
        with entorno():
            respuesta = self._entrar('puerta_cliente', ruta='/web/login')
        self.assertFalse(self._registros(self.cliente, puerta.SIN_PUERTA))
        self.assertFalse(self._registros(self.cliente, puerta.LOGIN_PUBLICO))
        self.assertTrue(self._registros(self.cliente, 'ok'))
        self.assertFalse(self._error_de_login(respuesta))

    def test_el_administrador_sin_puerta_tampoco_entra_y_se_avisa(self):
        with entorno(), patch.object(ResUsers, '_dcasa_avisar_admins', autospec=True) as avisar, \
                mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_admin', con_codigo=False)
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertTrue(self._registros(self.admin, puerta.SIN_PUERTA).es_admin)
        avisar.assert_called_once()
        self.assertIn('no pasó por la puerta', avisar.call_args.args[2])
        self.assertIn('no entró', avisar.call_args.args[2])

    # --- el código de la app, siempre ------------------------------------------------------------------------

    def test_quien_aun_no_tiene_la_app_la_enrola_al_entrar_en_modo_obligatorio(self):
        abierta = cabecera('sinapp@example.com')
        with entorno():
            respuesta = self._entrar('puerta_sin_app', abierta)
        self.assertTrue(respuesta.request.path_url.startswith(RUTA_ENROLAR), respuesta.request.path_url)
        self.assertIn('Activa tu doble factor', respuesta.text)
        with entorno():
            sin_sesion = self._panel(abierta)
        self.assertIn(sin_sesion.status_code, (302, 303), 'Sin código no hay panel')

    def test_en_modo_cero_quien_no_tiene_la_app_entra_como_antes(self):
        with entorno():
            respuesta = self._entrar('puerta_sin_app', modo='0', ruta='/web/login')
        self.assertEqual(respuesta.request.path_url, '/odoo')

    def test_el_paso_del_codigo_no_ofrece_no_volver_a_preguntar_al_personal(self):
        abierta = cabecera('vendedora@example.com')
        with entorno():
            paso = self._entrar('puerta_vendedora', abierta, con_codigo=False)
        self.assertTrue(paso.request.path_url.startswith('/web/login/totp'))
        self.assertNotIn('switch-remember', paso.text)

    # --- avisar ----------------------------------------------------------------------------------------------

    def test_en_modo_avisar_entra_pero_queda_anotado(self):
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users'):
            respuesta = self._entrar('puerta_vendedora', modo='avisar', ruta='/web/login')
        self.assertEqual(respuesta.request.path_url, '/odoo')
        registro = self._registros(self.vendedora, puerta.SIN_PUERTA)
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.metodo, 'solo aviso')
        with entorno():
            self.assertEqual(self._panel(modo='avisar').status_code, 200, 'En modo aviso la sesión sigue')
            self.assertIn('result', self._datos(modo='avisar'))

    # --- obligatoria: la sesión ------------------------------------------------------------------------------

    def test_la_sesion_del_personal_solo_vale_con_la_puerta(self):
        abierta = cabecera('vendedora@example.com')
        with entorno():
            self.assertEqual(self._entrar('puerta_vendedora', abierta).request.path_url, '/odoo')
            self.assertEqual(self._panel(abierta).status_code, 200)
            # La misma sesión, sin la cabecera del borde (cookie robada, puerta vencida): se cierra.
            sin = self._panel()
            self.assertIn(sin.status_code, (302, 303))
            self.assertIn('/web/login', sin.headers.get('Location', ''))
            # Y ya no vuelve sola: aun con la cabecera, hay que iniciar sesión otra vez.
            otra = self._panel(abierta)
            self.assertIn(otra.status_code, (302, 303))

    def test_una_sesion_robada_no_ejecuta_ni_una_sola_peticion_de_datos_sin_la_puerta(self):
        """La petición que cierra la sesión no puede correr todavía con los permisos del usuario."""
        abierta = cabecera('admin@example.com')
        with entorno():
            self.assertEqual(self._entrar('puerta_admin', abierta).request.path_url, '/odoo')
            self.assertIn('result', self._datos(abierta), 'Con la puerta, el panel trabaja normal')
            robada = self._datos()          # la cookie de sesión sola, sin pasar por la puerta
            self.assertNotIn('result', robada)
            self.assertEqual(robada['error']['code'], 100, 'Sesión expirada, no datos')
            self.assertNotIn('result', self._datos(abierta), 'Y la sesión no resucita')

    def test_la_sesion_de_un_cliente_no_se_toca(self):
        with entorno():
            self._entrar('puerta_cliente', ruta='/web/login')
            mi_cuenta = self.url_open('/my', headers=self._cabeceras(), allow_redirects=False)
            if mi_cuenta.status_code in (301, 302, 303) and mi_cuenta.headers['Location'].endswith('/mi-cuenta'):
                # Con dcasa_mi_cuenta, /my del cliente es /mi-cuenta: la sesión tiene que seguir valiendo ahí.
                mi_cuenta = self.url_open('/mi-cuenta', headers=self._cabeceras(), allow_redirects=False)
                self.assertIn('o_dcasa_mc_nav', mi_cuenta.text, 'Sigue dentro de su cuenta')
        self.assertEqual(mi_cuenta.status_code, 200)

    # --- la sesión vencida de los administradores (mismo arreglo, otro motivo) --------------------------------

    def test_una_sesion_vencida_por_tiempo_tampoco_ejecuta_la_ultima_peticion(self):
        aplicar_sesiones_admin(self.env, horas=12, minutos=60)
        self.assertEqual(self._entrar('puerta_admin', modo='0', ruta='/web/login').request.path_url, '/odoo')
        self.assertIn('result', self._datos(modo='0'))
        sesion = http.root.session_store.get(self.opener.cookies['session_id'])
        sesion[INICIO] = time.time() - 13 * 3600
        sesion['create_time'] = time.time() - 60
        http.root.session_store.save(sesion)
        vencida = self._datos(modo='0')
        self.assertNotIn('result', vencida)
        self.assertEqual(vencida['error']['code'], 100)

    # --- amarre del correo -----------------------------------------------------------------------------------

    def test_exigir_correo_amarra_la_puerta_a_la_cuenta(self):
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            ajeno = self._entrar('puerta_vendedora', cabecera('admin@example.com'), exigir_correo=True,
                                 con_codigo=False)
        self.assertNotEqual(ajeno.request.path_url, '/odoo')
        registro = self._registros(self.vendedora, puerta.CORREO_DISTINTO)
        self.assertEqual(len(registro), 1)
        self.assertEqual(registro.puerta, 'admin@example.com')
        with entorno():
            propio = self._entrar('puerta_vendedora', cabecera('Vendedora@Example.com'), exigir_correo=True)
        self.assertEqual(propio.request.path_url, '/odoo')

    def test_sin_exigir_correo_cualquier_correo_del_equipo_basta(self):
        with entorno():
            respuesta = self._entrar('puerta_vendedora', cabecera('admin@example.com'), exigir_correo=False)
        self.assertEqual(respuesta.request.path_url, '/odoo')

    # --- aviso a cada acceso del personal ---------------------------------------------------------------------

    def _avisos_por_entrar(self, login, valor='1'):
        self.ICP.set_param('dcasa_seguridad.aviso_telegram', valor)
        with entorno(), patch.object(ResUsers, '_dcasa_avisar_admins', autospec=True, wraps=None) as avisar:
            self._entrar(login, cabecera(f'{login}@example.com'), modo='0', ruta='/web/login', con_codigo=False)
        return avisar

    def test_cada_acceso_del_personal_avisa_al_canal_del_administrador(self):
        avisar = self._avisos_por_entrar('puerta_vendedora')
        avisar.assert_called_once()
        self.assertIn('inicio de sesión del personal', avisar.call_args.args[2])
        self.assertIn('puerta_vendedora', avisar.call_args.args[2])

    def test_el_aviso_de_un_administrador_dice_administrador(self):
        avisar = self._avisos_por_entrar('puerta_admin')
        avisar.assert_called_once()
        self.assertIn('de administrador', avisar.call_args.args[2])

    def test_con_admins_solo_se_avisa_de_los_administradores(self):
        self.assertFalse(self._avisos_por_entrar('puerta_vendedora', 'admins').called)
        self.assertTrue(self._avisos_por_entrar('puerta_admin', 'admins').called)

    def test_un_cliente_no_dispara_el_aviso(self):
        self.assertFalse(self._avisos_por_entrar('puerta_cliente').called)
