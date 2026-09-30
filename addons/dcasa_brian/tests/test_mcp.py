import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.tests import HttpCase, new_test_user, tagged


@herramienta(nombre='prueba_canal_leer', descripcion='Repite un texto (prueba de canales).',
             parametros={'texto': {'type': 'string', 'description': 'Texto a repetir'}},
             requeridos=['texto'], nivel='lectura')
def _h_prueba_canal_leer(self, texto):
    if texto == 'falla':
        raise BrianError('No puedo repetir «falla».')
    return {'eco': texto, 'usuario': self.env.user.login}


@herramienta(nombre='prueba_canal_sensible', descripcion='Crea un contacto de prueba (sensible).',
             parametros={'nombre': {'type': 'string', 'description': 'Nombre del contacto'}},
             requeridos=['nombre'], nivel='sensible')
def _h_prueba_canal_sensible(self, nombre):
    return {'id': self.env['res.partner'].create({'name': nombre}).id}


def parchar_herramientas(clase_de_prueba):
    """Agrega las herramientas de prueba al modelo (visible también en el hilo HTTP)."""
    clase = type(clase_de_prueba.env['brian.herramientas'])
    for metodo in (_h_prueba_canal_leer, _h_prueba_canal_sensible):
        clase_de_prueba.startClassPatcher(patch.object(clase, metodo.__name__, metodo, create=True))


@tagged('post_install', '-at_install')
class TestBrianMCP(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        parchar_herramientas(cls)
        cls.usuario = new_test_user(cls.env, login='brian_mcp', groups='base.group_user,base.group_partner_manager',
                                    name='Usuario MCP')
        cls.clave = cls.env['res.users.apikeys'].with_user(cls.usuario).sudo()._generate(
            'brian', 'Cliente MCP de prueba', fields.Datetime.now() + timedelta(days=1))

    def rpc(self, metodo, params=None, clave=True, id_=1, headers=None, cuerpo=None):
        cabeceras = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if clave:
            cabeceras['Authorization'] = f'Bearer {self.clave if clave is True else clave}'
        cabeceras.update(headers or {})
        if cuerpo is None:
            cuerpo = {'jsonrpc': '2.0', 'method': metodo}
            if id_ is not None:
                cuerpo['id'] = id_
            if params is not None:
                cuerpo['params'] = params
        return self.url_open('/brian/mcp', data=json.dumps(cuerpo), headers=cabeceras)

    def llamar(self, nombre, argumentos):
        respuesta = self.rpc('tools/call', {'name': nombre, 'arguments': argumentos})
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.json()

    def test_initialize(self):
        respuesta = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                            'clientInfo': {'name': 'prueba', 'version': '1'}})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.headers.get('Mcp-Session-Id'))
        resultado = respuesta.json()['result']
        self.assertEqual(resultado['protocolVersion'], '2025-06-18')
        self.assertEqual(resultado['serverInfo']['name'], 'brian-dcasa')
        self.assertEqual(resultado['capabilities'], {'tools': {'listChanged': False}})
        self.assertIn('español', resultado['instructions'])
        # Versión desconocida: el servidor propone la suya.
        otra = self.rpc('initialize', {'protocolVersion': '1999-01-01'}).json()['result']
        self.assertEqual(otra['protocolVersion'], '2025-06-18')

    def test_notificacion_y_ping(self):
        respuesta = self.rpc('notifications/initialized', id_=None)
        self.assertEqual(respuesta.status_code, 202)
        self.assertEqual(respuesta.content, b'')
        self.assertEqual(self.rpc('ping', id_=7).json(), {'jsonrpc': '2.0', 'id': 7, 'result': {}})

    def test_sin_clave_401(self):
        respuesta = self.rpc('tools/list', clave=False)
        self.assertEqual(respuesta.status_code, 401)
        self.assertIn('Bearer', respuesta.headers.get('WWW-Authenticate', ''))
        respuesta = self.rpc('tools/list', clave='clave-falsa')
        self.assertEqual(respuesta.status_code, 401)
        self.assertIn('invalid_token', respuesta.headers.get('WWW-Authenticate', ''))

    def test_clave_de_otro_alcance_no_sirve(self):
        otra = self.env['res.users.apikeys'].with_user(self.usuario).sudo()._generate(
            'otra_cosa', 'Otra', fields.Datetime.now() + timedelta(days=1))
        self.assertEqual(self.rpc('tools/list', clave=otra).status_code, 401)

    def test_tools_list(self):
        respuesta = self.rpc('tools/list')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers.get('Content-Type', '').split(';')[0], 'application/json')
        herramientas = {h['name']: h for h in respuesta.json()['result']['tools']}
        leer = herramientas['prueba_canal_leer']
        self.assertEqual(leer['inputSchema']['required'], ['texto'])
        self.assertTrue(leer['annotations']['readOnlyHint'])
        self.assertFalse(leer['annotations']['destructiveHint'])
        self.assertFalse(leer['annotations']['openWorldHint'])
        sensible = herramientas['prueba_canal_sensible']
        self.assertTrue(sensible['annotations']['destructiveHint'])
        self.assertFalse(sensible['annotations']['readOnlyHint'])
        self.assertIn('rechazar_accion', herramientas)
        self.assertNotIn('confirmar_accion', herramientas, 'Por defecto MCP no confirma acciones sensibles')

    def test_tools_call_lectura(self):
        resultado = self.llamar('prueba_canal_leer', {'texto': 'hola'})['result']
        self.assertFalse(resultado['isError'])
        self.assertEqual(resultado['structuredContent'], {'eco': 'hola', 'usuario': 'brian_mcp'})
        self.assertEqual(json.loads(resultado['content'][0]['text'])['eco'], 'hola')
        accion = self.env['brian.accion'].search([('herramienta', '=', 'prueba_canal_leer')], limit=1)
        self.assertEqual((accion.canal, accion.estado, accion.create_uid), ('mcp', 'hecha', self.usuario))

    def test_tools_call_errores(self):
        desconocida = self.llamar('no_existe', {})
        self.assertEqual(desconocida['error']['code'], -32602)
        falla = self.llamar('prueba_canal_leer', {'texto': 'falla'})['result']
        self.assertTrue(falla['isError'])
        self.assertIn('falla', falla['content'][0]['text'])
        faltan = self.llamar('prueba_canal_leer', {})['result']
        self.assertTrue(faltan['isError'])
        self.assertEqual(self.rpc('recursos/raros').json()['error']['code'], -32601)

    def test_sensible_no_se_ejecuta_sin_confirmacion(self):
        resultado = self.llamar('prueba_canal_sensible', {'nombre': 'Contacto MCP sensible'})['result']
        self.assertTrue(resultado['isError'])
        datos = resultado['structuredContent']
        self.assertTrue(datos['requiere_confirmacion'])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Contacto MCP sensible')]))
        accion = self.env['brian.accion'].browse(datos['accion_id'])
        self.assertEqual(accion.estado, 'por_confirmar')
        # confirmar_accion no existe en MCP salvo que el administrador lo active.
        self.assertEqual(self.llamar('confirmar_accion', {'accion_id': accion.id})['error']['code'], -32602)
        self.assertEqual(accion.estado, 'por_confirmar')
        # Rechazar sí se puede.
        self.assertFalse(self.llamar('rechazar_accion', {'accion_id': accion.id})['result']['isError'])
        self.assertEqual(accion.estado, 'rechazada')

    def test_confirmar_si_el_administrador_lo_activa(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.mcp_permite_confirmar', 'True')
        datos = self.llamar('prueba_canal_sensible', {'nombre': 'Contacto MCP confirmado'})['result']
        resultado = self.llamar('confirmar_accion', {'accion_id': datos['structuredContent']['accion_id']})
        self.assertFalse(resultado['result']['isError'])
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Contacto MCP confirmado')]))

    def test_transporte(self):
        lote = self.rpc(None, cuerpo=[{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}])
        self.assertEqual(lote.status_code, 400)
        self.assertEqual(lote.json()['error']['code'], -32600)
        self.assertEqual(self.url_open('/brian/mcp').status_code, 405)
        malo = self.url_open('/brian/mcp', data='{no json', headers={'Authorization': f'Bearer {self.clave}'})
        self.assertEqual(malo.json()['error']['code'], -32700)
        origen = self.rpc('ping', headers={'Origin': 'https://sitio-malo.example'})
        self.assertEqual(origen.status_code, 403)
        version = self.rpc('ping', headers={'MCP-Protocol-Version': '1999-01-01'})
        self.assertEqual(version.status_code, 400)
        self.assertEqual(self.rpc('ping', headers={'MCP-Protocol-Version': '2025-06-18'}).status_code, 200)
