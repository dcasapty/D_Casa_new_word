import json
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests

from odoo import fields
from odoo.addons.dcasa_brian.models import telegram as modulo_telegram
from odoo.addons.dcasa_brian.tests.test_mcp import parchar_herramientas
from odoo.exceptions import UserError
from odoo.tests import HttpCase, new_test_user, tagged

SECRETO = 'secreto-de-prueba_123'


class RespuestaFalsa:
    def __init__(self, cuerpo=None, contenido=b'', status_code=200):
        self._cuerpo, self.content, self.status_code = cuerpo, contenido, status_code

    def json(self):
        return self._cuerpo


@tagged('post_install', '-at_install')
class TestBrianTelegram(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        parchar_herramientas(cls)
        cls.startClassPatcher(patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': '123:TOKEN-PRUEBA',
                                                      'BRIAN_TELEGRAM_SECRETO': SECRETO}))
        cls.usuario = new_test_user(cls.env, login='brian_tg', groups='base.group_user,base.group_partner_manager',
                                    name='Usuario Telegram')
        cls.Enlace = cls.env['brian.telegram.enlace']

    def setUp(self):
        super().setUp()
        self.llamadas = []
        falso = MagicMock()
        falso.RequestException = requests.RequestException

        def post(url, json=None, timeout=None):
            self.assertIsNotNone(timeout)
            metodo = url.rsplit('/', 1)[-1]
            self.llamadas.append((metodo, json or {}))
            if metodo == 'getFile':
                return RespuestaFalsa({'ok': True, 'result': {'file_path': 'photos/f.jpg', 'file_size': 4}})
            return RespuestaFalsa({'ok': True, 'result': {'message_id': 99}})

        falso.post.side_effect = post
        falso.get.side_effect = lambda url, timeout=None: RespuestaFalsa(contenido=b'\xff\xd8\xff\xe0')
        patcher = patch.object(modulo_telegram, 'requests', falso)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------------

    def webhook(self, update, secreto=SECRETO, encabezado=SECRETO):
        cabeceras = {'Content-Type': 'application/json'}
        if encabezado:
            cabeceras['X-Telegram-Bot-Api-Secret-Token'] = encabezado
        return self.url_open(f'/brian/telegram/{secreto}', data=json.dumps(update), headers=cabeceras)

    def mensaje(self, chat_id, texto, update_id=1, **extra):
        mensaje = {'message_id': update_id, 'chat': {'id': chat_id, 'type': 'private'},
                   'from': {'id': chat_id, 'first_name': 'Ana', 'username': 'ana_dcasa'}, 'text': texto}
        mensaje.update(extra)
        return self.webhook({'update_id': update_id, 'message': mensaje})

    def textos(self):
        return [datos.get('text', '') for metodo, datos in self.llamadas if metodo == 'sendMessage']

    def vincular(self, chat_id):
        codigo = self.Enlace.with_user(self.usuario).generar_codigo()
        self.mensaje(chat_id, f'/vincular {codigo}')
        enlace = self.Enlace.sudo().search([('chat_id', '=', str(chat_id))])
        self.assertTrue(enlace.activo)
        self.llamadas.clear()
        return enlace

    # ------------------------------------------------------------------

    def test_secreto_invalido(self):
        self.assertEqual(self.mensaje(1, 'hola').status_code, 200)
        self.assertEqual(self.webhook({'update_id': 1}, secreto='otro').status_code, 404)
        self.assertEqual(self.webhook({'update_id': 1}, encabezado=None).status_code, 404)
        self.assertEqual(self.webhook({'update_id': 1}, encabezado='otro').status_code, 404)

    def test_chat_no_vinculado_recibe_instrucciones(self):
        self.mensaje(1001, '¿cómo van las ventas?')
        self.assertEqual(len(self.textos()), 1)
        self.assertIn('/vincular', self.textos()[0])
        # En grupos no responde nada.
        self.llamadas.clear()
        self.webhook({'update_id': 2, 'message': {'message_id': 1, 'chat': {'id': -5, 'type': 'group'},
                                                   'text': 'hola'}})
        self.assertFalse(self.textos())

    def test_vincular(self):
        codigo = self.Enlace.with_user(self.usuario).generar_codigo()
        self.assertRegex(codigo, r'^\d{6}$')
        incorrecto = '000000' if codigo != '000000' else '111111'
        self.mensaje(1002, f'/vincular {incorrecto}')
        self.assertIn('no es válido', self.textos()[-1])
        self.mensaje(1002, f'/vincular {codigo}', update_id=2)
        enlace = self.Enlace.sudo().search([('chat_id', '=', '1002')])
        self.assertEqual(enlace.user_id, self.usuario)
        self.assertIn('@ana_dcasa', enlace.nombre)
        self.assertIn('quedó vinculado', self.textos()[-1])
        # Un solo uso.
        self.mensaje(1003, f'/vincular {codigo}', update_id=3)
        self.assertFalse(self.Enlace.sudo().search([('chat_id', '=', '1003')]))

    def test_codigo_vencido(self):
        codigo = self.Enlace.with_user(self.usuario).generar_codigo()
        self.env['brian.telegram.codigo'].sudo().search([('user_id', '=', self.usuario.id)]).vence = \
            fields.Datetime.now() - timedelta(minutes=1)
        self.mensaje(1004, f'/vincular {codigo}')
        self.assertFalse(self.Enlace.sudo().search([('chat_id', '=', '1004')]))
        self.assertIn('venció', self.textos()[-1])

    def test_codigo_desde_la_ficha_solo_propio(self):
        accion = self.usuario.with_user(self.usuario).action_dcasa_brian_vincular_telegram()
        self.assertIn('/vincular', accion['params']['message'])
        with self.assertRaises(UserError):
            self.env.ref('base.user_admin').with_user(self.usuario).action_dcasa_brian_vincular_telegram()

    def test_mensaje_vinculado_llega_a_la_conversacion(self):
        enlace = self.vincular(1005)
        recibido = {}

        def enviar(conversacion, texto, adjunto_ids=None, contexto=None):
            recibido.update(uid=conversacion.env.uid, texto=texto, adjuntos=adjunto_ids,
                            canal=conversacion.canal)
            return {'ok': True, 'mensajes': [
                {'rol': 'user', 'texto': texto},
                {'rol': 'assistant', 'texto': 'x' * 5000},
            ]}

        with patch.object(type(self.env['brian.conversacion']), 'enviar', enviar):
            self.mensaje(1005, 'Hola Brian', update_id=10,
                         photo=[{'file_id': 'a', 'file_size': 1, 'width': 90}, {'file_id': 'b', 'file_size': 4}])
        self.assertEqual(recibido['uid'], self.usuario.id)
        self.assertEqual(recibido['texto'], 'Hola Brian')
        self.assertEqual(recibido['canal'], 'telegram')
        adjunto = self.env['ir.attachment'].sudo().browse(recibido['adjuntos'])
        self.assertEqual(len(adjunto), 1)
        self.assertEqual(adjunto.raw, b'\xff\xd8\xff\xe0')
        self.assertIn(('getFile', {'file_id': 'b'}), self.llamadas)
        # Mensaje largo partido en trozos de ≤ 4096.
        self.assertEqual([len(t) for t in self.textos()], [4096, 904])
        self.assertTrue(enlace.conversacion_id)
        # /nuevo suelta la conversación activa; un reintento del mismo update se ignora.
        self.mensaje(1005, '/nuevo', update_id=11)
        self.assertFalse(enlace.conversacion_id)
        antes = len(self.llamadas)
        self.mensaje(1005, '/nuevo', update_id=11)
        self.assertEqual(len(self.llamadas), antes)

    def test_confirmar_con_botones(self):
        self.vincular(1006)
        Herramientas = self.env['brian.herramientas'].with_user(self.usuario)
        propuesta = Herramientas.ejecutar('prueba_canal_sensible', {'nombre': 'Contacto por Telegram'}, canal='mcp')
        self.assertTrue(propuesta['requiere_confirmacion'])
        # Aviso fuera de banda con botones.
        self.Enlace.notificar_confirmacion(self.usuario, propuesta['accion_id'], propuesta['resumen'])
        aviso = [d for m, d in self.llamadas if m == 'sendMessage'][-1]
        botones = aviso['reply_markup']['inline_keyboard']
        self.assertEqual(botones[0][0]['callback_data'], f'brian:c:{propuesta["accion_id"]}')
        # Permitir / Rechazar, nada más (no existe «Siempre»), y el detalle exacto de lo que va a hacer.
        self.assertEqual([[b['text'] for b in fila] for fila in botones], [['Permitir', 'Rechazar']])
        self.assertIn('tu permiso', aviso['text'])
        self.assertIn('Detalle exacto', aviso['text'])
        self.assertIn('• Nombre: Contacto por Telegram', aviso['text'])

        def callback(chat_id, datos, update_id, desde=None):
            return self.webhook({'update_id': update_id, 'callback_query': {
                'id': 'cb', 'data': datos, 'from': {'id': desde or chat_id},
                'message': {'message_id': 5, 'chat': {'id': chat_id, 'type': 'private'}}}})

        # Otro chat (no dueño) no puede confirmar.
        callback(1007, botones[0][0]['callback_data'], 20)
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Contacto por Telegram')]))
        callback(1006, botones[0][0]['callback_data'], 21)
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Contacto por Telegram')]))
        self.assertEqual(self.env['brian.accion'].browse(propuesta['accion_id']).estado, 'hecha')
        self.assertIn('answerCallbackQuery', [m for m, _d in self.llamadas])

        otra = Herramientas.ejecutar('prueba_canal_sensible', {'nombre': 'No se crea'}, canal='mcp')
        callback(1006, f'brian:r:{otra["accion_id"]}', 22)
        self.assertEqual(self.env['brian.accion'].browse(otra['accion_id']).estado, 'rechazada')
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'No se crea')]))

    def test_boton_viejo_de_una_conversacion_borrada_no_ejecuta(self):
        enlace = self.vincular(1010)
        conversacion = enlace._conversacion()
        Herramientas = self.env['brian.herramientas'].with_user(self.usuario)
        propuesta = Herramientas.ejecutar('prueba_canal_sensible', {'nombre': 'Contacto borrado'},
                                          canal='telegram', conversacion=conversacion.id)
        conversacion.unlink()
        self.env.invalidate_all()
        self.assertFalse(enlace.conversacion_id)

        def pulsar(accion_id, update_id):
            self.webhook({'update_id': update_id, 'callback_query': {
                'id': 'cb', 'data': f'brian:c:{accion_id}', 'from': {'id': 1010},
                'message': {'message_id': 5, 'chat': {'id': 1010, 'type': 'private'}}}})

        pulsar(propuesta['accion_id'], 50)
        self.env.invalidate_all()
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Contacto borrado')]))
        self.assertEqual(self.env['brian.accion'].browse(propuesta['accion_id']).estado, 'rechazada')
        self.assertIn('ya no está pendiente', self.textos()[-1])

        # Acción de chat que quedó pendiente sin conversación (borrada antes de este arreglo).
        huerfana = Herramientas.ejecutar('prueba_canal_sensible', {'nombre': 'Contacto huérfano'}, canal='telegram')
        pulsar(huerfana['accion_id'], 51)
        self.env.invalidate_all()
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Contacto huérfano')]))
        self.assertEqual(self.env['brian.accion'].browse(huerfana['accion_id']).estado, 'rechazada')
        self.assertIn('se borró', self.textos()[-1])

        # El siguiente mensaje abre una conversación nueva, sin errores.
        self.assertTrue(enlace._conversacion().exists())

    def test_confirmar_en_conversacion(self):
        enlace = self.vincular(1009)
        conversacion = enlace._conversacion()
        Herramientas = self.env['brian.herramientas'].with_user(self.usuario)
        propuesta = Herramientas.ejecutar('prueba_canal_sensible', {'nombre': 'Contacto conversado'},
                                          canal='telegram', conversacion=conversacion.id)
        recibido = {}

        def confirmar_accion(conv, accion_id):
            recibido.update(uid=conv.env.uid, conversacion=conv.id, accion=accion_id)
            return {'ok': True, 'mensajes': [
                {'rol': 'assistant', 'texto': 'Viejo', 'confirmacion': {'accion_id': accion_id, 'estado': 'hecha'}},
                {'rol': 'assistant', 'texto': 'Listo, creé el contacto.', 'confirmacion': None},
                {'rol': 'assistant', 'texto': 'Y ahora esto:', 'confirmacion': {
                    'accion_id': 999, 'estado': 'por_confirmar', 'resumen': 'Crear otro contacto.',
                    'detalle': [{'etiqueta': 'Nombre', 'valor': 'Segundo'}, {'etiqueta': 'Vacío', 'valor': ''}]}}]}

        with patch.object(type(self.env['brian.conversacion']), 'confirmar_accion', confirmar_accion):
            self.webhook({'update_id': 40, 'callback_query': {
                'id': 'cb', 'data': f'brian:c:{propuesta["accion_id"]}', 'from': {'id': 1009},
                'message': {'message_id': 5, 'chat': {'id': 1009, 'type': 'private'}}}})
        self.assertEqual(recibido, {'uid': self.usuario.id, 'conversacion': conversacion.id,
                                    'accion': propuesta['accion_id']})
        self.assertEqual(self.textos(), [
            'Listo, creé el contacto.',
            'Y ahora esto:\n\nNecesito tu permiso:\n\nCrear otro contacto.\n\n'
            'Detalle exacto de lo que voy a hacer:\n• Nombre: Segundo'])
        tarjeta = [d for m, d in self.llamadas if m == 'sendMessage'][-1]
        self.assertEqual([b['text'] for b in tarjeta['reply_markup']['inline_keyboard'][0]], ['Permitir', 'Rechazar'])

    def test_desvincular(self):
        enlace = self.vincular(1008)
        self.mensaje(1008, '/desvincular', update_id=30)
        self.assertFalse(enlace.activo)
        self.mensaje(1008, 'hola', update_id=31)
        self.assertIn('/vincular', self.textos()[-1])

    def test_partir_texto(self):
        partes = modulo_telegram.partir_texto('linea\n' * 1000, limite=100)
        self.assertTrue(all(len(p) <= 100 for p in partes))
        self.assertEqual(''.join(partes).count('linea'), 1000)
