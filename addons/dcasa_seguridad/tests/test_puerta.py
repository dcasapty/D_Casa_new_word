"""La puerta del equipo (models/puerta.py, edge/src/puerta.ts): el personal solo entra con la puerta abierta."""
import hmac
import json
import os
import re
import time
from hashlib import sha256
from unittest.mock import patch

from odoo import http
from odoo.addons.dcasa_seguridad.models import puerta
from odoo.addons.dcasa_seguridad.models.ir_http import INICIO
from odoo.addons.dcasa_seguridad.models.parametros import aplicar_sesiones_admin
from odoo.addons.dcasa_seguridad.models.res_users import ResUsers
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

    @staticmethod
    def _cabeceras(puerta_abierta=None, modo='1', exigir_correo=False, extra=None):
        """Lo que el borde le manda a Odoo; ``modo=None`` = una petición que no pasó por el borde."""
        cabeceras = dict(extra or {})
        if puerta_abierta:
            cabeceras[puerta.CABECERA] = puerta_abierta
        if modo is not None:
            cabeceras[puerta.CABECERA_MODO] = modo_firmado(modo, exigir_correo)
        return cabeceras

    def _entrar(self, login, abierta=None, modo='1', exigir_correo=False):
        return self.url_open('/web/login', data={
            'login': login, 'password': login, 'csrf_token': http.Request.csrf_token(self)},
            headers=self._cabeceras(abierta, modo, exigir_correo))

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

    # --- apagada o sin cabecera del modo --------------------------------------------------------------------

    def test_el_modo_cero_no_cambia_nada(self):
        with entorno():
            self.assertEqual(self._entrar('puerta_vendedora', modo='0').request.path_url, '/odoo')
        self.assertFalse(self._registros(self.vendedora, puerta.SIN_PUERTA))

    def test_una_peticion_que_no_paso_por_el_borde_no_exige_nada(self):
        """Lo que nace dentro del contenedor (p. ej. el PDF de una factura con la sesión de quien lo pidió)."""
        with entorno():
            self.assertEqual(self._entrar('puerta_vendedora', modo=None).request.path_url, '/odoo')
            self.assertIn('result', self._datos(modo=None), 'La sesión sigue valiendo sin cabecera del modo')
        self.assertFalse(self._registros(self.vendedora, puerta.SIN_PUERTA))

    def test_un_modo_falsificado_no_exige_nada(self):
        falso = {puerta.CABECERA_MODO: modo_firmado('1', secreto='z' * 40)}
        with entorno():
            respuesta = self.url_open('/web/login', data={
                'login': 'puerta_vendedora', 'password': 'puerta_vendedora',
                'csrf_token': http.Request.csrf_token(self)}, headers=falso)
        self.assertEqual(respuesta.request.path_url, '/odoo')

    # --- obligatoria: el inicio de sesión --------------------------------------------------------------------

    def test_el_personal_con_clave_correcta_pero_sin_puerta_no_entra(self):
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_vendedora')
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertTrue(respuesta.request.path_url.startswith('/web/login'))
        # El mismo mensaje que una clave equivocada: no le dice a quien prueba que la clave estaba bien.
        with entorno(), mute_logger('odoo.addons.base.models.res_users', 'odoo.http'):
            equivocada = self.url_open('/web/login', data={
                'login': 'puerta_vendedora', 'password': 'otra-clave', 'csrf_token': http.Request.csrf_token(self)},
                headers=self._cabeceras())
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

    def test_una_cabecera_falsificada_no_abre(self):
        falsa = cabecera('vendedora@example.com', secreto='z' * 40)
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_vendedora', falsa)
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertEqual(len(self._registros(self.vendedora, puerta.SIN_PUERTA)), 1)

    def test_un_cliente_del_portal_nunca_pasa_por_la_puerta(self):
        with entorno():
            respuesta = self._entrar('puerta_cliente')
        self.assertFalse(self._registros(self.cliente, puerta.SIN_PUERTA))
        self.assertTrue(self._registros(self.cliente, 'ok'))
        self.assertFalse(self._error_de_login(respuesta))

    def test_el_administrador_sin_puerta_tampoco_entra_y_se_avisa(self):
        with entorno(), patch.object(ResUsers, '_dcasa_avisar_admins', autospec=True) as avisar, \
                mute_logger('odoo.addons.dcasa_seguridad.models.res_users', 'odoo.http'):
            respuesta = self._entrar('puerta_admin')
        self.assertNotEqual(respuesta.request.path_url, '/odoo')
        self.assertTrue(self._registros(self.admin, puerta.SIN_PUERTA).es_admin)
        avisar.assert_called_once()
        self.assertIn('no pasó por la puerta', avisar.call_args.args[2])
        self.assertIn('no entró', avisar.call_args.args[2])

    # --- avisar ----------------------------------------------------------------------------------------------

    def test_en_modo_avisar_entra_pero_queda_anotado(self):
        with entorno(), mute_logger('odoo.addons.dcasa_seguridad.models.res_users'):
            respuesta = self._entrar('puerta_vendedora', modo='avisar')
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
            self._entrar('puerta_cliente')
            mi_cuenta = self.url_open('/my', headers=self._cabeceras(), allow_redirects=False)
        self.assertEqual(mi_cuenta.status_code, 200)

    # --- la sesión vencida de los administradores (mismo arreglo, otro motivo) --------------------------------

    def test_una_sesion_vencida_por_tiempo_tampoco_ejecuta_la_ultima_peticion(self):
        aplicar_sesiones_admin(self.env, horas=12, minutos=60)
        self.assertEqual(self._entrar('puerta_admin', modo='0').request.path_url, '/odoo')
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
            ajeno = self._entrar('puerta_vendedora', cabecera('admin@example.com'), exigir_correo=True)
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
