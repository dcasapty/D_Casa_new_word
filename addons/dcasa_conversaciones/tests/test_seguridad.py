"""Superficie RPC y secretos: nadie llama por RPC lo que escribe con sudo; los tokens no están en ningún sitio."""
import os
import re
from pathlib import Path
from unittest.mock import patch

import requests

from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import tagged

from .common import JuanCase

MODULO = Path(__file__).resolve().parent.parent
RAIZ_REPO = MODULO.parent.parent


@tagged('post_install', '-at_install')
class TestSuperficieRpc(JuanCase):

    def rpc(self, usuario, modelo, metodo, args=(), kwargs=None):
        return call_kw(self.env(user=usuario)[modelo], metodo, list(args), kwargs or {})

    def assertBloqueado(self, usuario, modelo, metodo, args=(), kwargs=None):
        with self.subTest(modelo=modelo, metodo=metodo, usuario=usuario.login), self.assertRaises(AccessError):
            self.rpc(usuario, modelo, metodo, args, kwargs)

    def test_lo_que_escribe_con_sudo_es_privado(self):
        datos = self.datos('Hola')
        conv = self.conversacion()
        llamadas = [
            ('dcasa.conversacion', '_registrar_mensaje', [datos]),
            ('dcasa.conversacion', '_pasar_a_vendedora', [[conv.id], 'x']),
            ('dcasa.conversacion', '_seguimiento_hecho', [[conv.id], 1, 'enviado']),
            ('dcasa.conversacion', '_poner_en_humano', [[conv.id]]),
            ('dcasa.conversacion', '_cron_seguimientos', []),
            ('dcasa.conversacion', '_oportunidad', [[conv.id], 'x']),
            ('dcasa.mensaje', '_enviar', [[conv.mensaje_ids.id]]),
            ('dcasa.mensaje', '_crear_si_no_existe', [{}]),
            ('dcasa.juan.cliente', 'enviar', ['whatsapp_qr', '1', 'hola']),
            ('dcasa.juan.cliente', 'cambiar_estado', ['whatsapp_qr', '1', 'humano']),
            ('dcasa.juan.cliente', 'pedir_seguimiento', [1, 'whatsapp_qr', '1', 1]),
            ('dcasa.juan.cliente', 'salud', []),
            ('dcasa.juan.ajustes', 'obtener', []),
            ('dcasa.juan.ajustes', 'token_odoo', []),
            ('dcasa.juan.ajustes', 'token_worker', []),
            ('dcasa.juan.ajustes', 'como_json', [[self.ajustes.id]]),
            ('dcasa.juan.ajustes', 'horario', [[self.ajustes.id]]),
            ('dcasa.juan.ajustes', 'precios_ia', [[self.ajustes.id]]),
            ('dcasa.juan.ajustes', 'lista_lecciones', [[self.ajustes.id]]),
            ('dcasa.conocimiento', '_buscar', ['horario']),
            ('dcasa.pregunta_pendiente', '_registrar', ['¿Instalan?', None, conv.id]),
            ('brian.herramientas', 'ejecutar', ['juan_horario_y_tienda', {}]),
            ('brian.accion', 'registrar', [{'nombre': 'x'}, {}]),
        ]
        for usuario in (self.vendedora, self.interno, self.portal):
            for modelo, metodo, args in llamadas:
                self.assertBloqueado(usuario, modelo, metodo, args)
        self.assertEqual(self.Conversacion.search_count([('id_externo', '=', '50761234567')]), 1)

    def test_los_botones_exigen_ventas_tambien_por_rpc(self):
        conv = self.conversacion()
        for usuario in (self.interno, self.portal):
            for metodo in ('action_atender', 'action_devolver_al_bot', 'action_cerrar', 'action_crear_oportunidad',
                           'action_reintentar_envios'):
                self.assertBloqueado(usuario, 'dcasa.conversacion', metodo, [[conv.id]])
        self.assertEqual(conv.estado, 'bot')

    def test_el_historial_no_se_edita_por_rpc(self):
        mensaje = self.conversacion().mensaje_ids
        for usuario in (self.vendedora, self.gerente):
            self.assertBloqueado(usuario, 'dcasa.mensaje', 'write', [[mensaje.id], {'texto': 'otra cosa'}])
            self.assertBloqueado(usuario, 'dcasa.mensaje', 'create', [{
                'conversacion_id': mensaje.conversacion_id.id, 'id_mensaje': 'falso', 'direccion': 'entrante',
                'autor': 'cliente', 'texto': 'inventado'}])
        self.assertEqual(mensaje.texto, 'Hola, ¿tienen camas queen?')

    def test_ni_ventas_crea_conversaciones_a_mano(self):
        self.assertBloqueado(self.vendedora, 'dcasa.conversacion', 'create', [{
            'canal': 'whatsapp_qr', 'id_externo': '50760000000'}])

    def test_el_personal_sin_ventas_y_el_portal_no_ven_las_conversaciones(self):
        self.conversacion()
        for usuario in (self.interno, self.portal):
            self.assertBloqueado(usuario, 'dcasa.conversacion', 'search_read', [[]], {'fields': ['name']})
            self.assertBloqueado(usuario, 'dcasa.mensaje', 'search_read', [[]], {'fields': ['texto']})
        self.assertTrue(self.rpc(self.vendedora, 'dcasa.conversacion', 'search_read', [[]], {'fields': ['name']}))

    def test_las_herramientas_de_juan_no_se_ejecutan_por_rpc_ni_como_otro_usuario(self):
        for usuario in (self.vendedora, self.gerente, self.interno):
            resultado = self.env['brian.herramientas'].with_user(usuario).ejecutar('juan_buscar_productos',
                                                                                 {'consulta': 'cama'})
            self.assertFalse(resultado['ok'])


@tagged('post_install', '-at_install')
class TestSecretos(JuanCase):

    def test_ningun_token_se_instala_con_el_modulo(self):
        parametros = self.env['ir.config_parameter'].sudo()
        self.assertFalse(parametros.get_param('dcasa_conversaciones.juan_odoo_token'))
        self.assertFalse(parametros.get_param('dcasa_conversaciones.juan_worker_token'))
        self.assertFalse(self.env['dcasa.juan.ajustes'].token_odoo())

    def test_el_usuario_juan_no_tiene_clave_de_api_ni_contrasena(self):
        self.assertFalse(self.env['res.users.apikeys'].sudo().search([('user_id', '=', self.juan.id)]))
        self.assertFalse(self.juan.sudo().password)
        self.assertFalse(self.juan.sudo().totp_secret if 'totp_secret' in self.juan._fields else False)

    def test_el_codigo_no_trae_valores_de_token(self):
        """Ni en Python, ni en XML, ni en la documentación del módulo: solo los NOMBRES de las variables."""
        patron = re.compile(
            r'(JUAN_(?:ODOO|WORKER)_TOKEN|juan_(?:odoo|worker)_token)\s*[:=]\s*[\'"]?([A-Za-z0-9_\-]{20,})')
        for archivo in MODULO.rglob('*'):
            if not archivo.is_file() or archivo.suffix not in {'.py', '.xml', '.csv', '.md', '.json', '.scss'}:
                continue
            if 'tests' in archivo.parts:
                continue
            for coincidencia in patron.finditer(archivo.read_text(encoding='utf-8')):
                self.fail(f'{archivo.name} parece traer un valor de token: {coincidencia.group(1)}')

    def test_el_arranque_no_imprime_los_tokens(self):
        entrypoint = RAIZ_REPO / 'docker' / 'entrypoint.sh'
        if not entrypoint.exists():
            self.skipTest('El repositorio no está junto al módulo (imagen de producción).')
        texto = entrypoint.read_text(encoding='utf-8')
        for variable in ('JUAN_ODOO_TOKEN', 'JUAN_WORKER_TOKEN'):
            self.assertNotIn(variable, texto, f'{variable} no debe aparecer en el arranque: lo imprimiría')
        self.assertNotRegex(texto, r'^\s*(set -x|printenv|env\s*$)', 'El arranque no vuelca el entorno')

    def test_el_cliente_del_worker_nunca_escribe_el_token_en_los_registros(self):
        token = 'T' * 40
        cliente = self.env['dcasa.juan.cliente']
        with patch.dict(os.environ, {'JUAN_WORKER_TOKEN': token, 'JUAN_URL': 'https://juan.prueba.example.com'}), \
                patch('requests.request', side_effect=requests.ConnectionError(f'fallo con {token}')), \
                self.assertLogs('odoo.addons.dcasa_conversaciones', level='DEBUG') as registros:
            resultado = cliente._llamar('POST', '/odoo/enviar', {'texto': 'x'})
        self.assertFalse(resultado['ok'])
        self.assertNotIn(token, '\n'.join(registros.output))
        self.assertNotIn(token, str(resultado))
