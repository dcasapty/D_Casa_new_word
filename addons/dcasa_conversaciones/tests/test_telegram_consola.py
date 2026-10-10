"""Ola 4 · la consola de Telegram: «Atender» en el aviso y responder al aviso para escribirle al cliente.

Lo que más importa aquí es lo que NO debe pasar: que algo salga hacia un cliente sin que la persona lo confirme, que lo
confirme otra persona, que lo mande alguien sin permiso o que un doble toque lo mande dos veces.
"""
from datetime import timedelta
from itertools import count
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.addons.dcasa_brian.models import telegram as brian_telegram
from odoo.tests import tagged

from ..models.conversacion import PIE_DE_AVISO
from .common import URL_WORKER, JuanCase, respuesta_http

_ids_de_update = count(1000)


@tagged('post_install', '-at_install')
class TestConsolaDeTelegram(JuanCase):

    def setUp(self):
        super().setUp()
        brian_telegram._mensajes.clear()      # el límite de velocidad de Brian es por chat y vive en memoria
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.Borrador = self.env['dcasa.telegram_borrador'].sudo()
        self.enlace_ana = self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.enlace_gema = self.Enlace.create({'user_id': self.gerente.id, 'chat_id': '5550002'})
        self.enlace_sin_ventas = self.Enlace.create({'user_id': self.interno.id, 'chat_id': '5550003'})
        self.enviar = MagicMock()
        self.api = MagicMock(return_value={'message_id': 1})
        for nombre, simulado in (('_enviar', self.enviar), ('_api', self.api)):
            parche = patch.object(type(self.Enlace), nombre, simulado)
            parche.start()
            self.addCleanup(parche.stop)
        self.ajustes.usuarios_aviso_ids = [(6, 0, (self.vendedora | self.gerente).ids)]
        self.conv = self.conversacion('Hola, quiero una cama queen', nombre='Karen', id_externo='50761230001')
        self.conv._poner_en_humano()
        self.n_mensajes = lambda: self.Mensaje.search_count([('conversacion_id', '=', self.conv.id),
                                                              ('autor', '=', 'vendedora')])

    # -- armar updates como los manda Telegram ------------------------------------------------------------------

    def aviso_del_bot(self, conv=None):
        return {'message_id': 77, 'from': {'is_bot': True, 'id': 999}, 'chat': {'id': 5550001, 'type': 'private'},
                'text': f'Karen espera.\n\n{PIE_DE_AVISO % (conv or self.conv).id}'}

    def respuesta(self, texto, chat_id='5550001', aviso=None, **extra):
        return {'update_id': next(_ids_de_update), 'message': {
            'message_id': 78, 'chat': {'id': int(chat_id), 'type': 'private'}, 'from': {'id': int(chat_id)},
            'text': texto, 'reply_to_message': aviso or self.aviso_del_bot(), **extra}}

    def pulsar(self, dato, chat_id='5550001', tipo='private', quien=None):
        return {'update_id': next(_ids_de_update), 'callback_query': {
            'id': 'cb1', 'data': dato, 'from': {'id': int(quien or chat_id)},
            'message': {'message_id': 90, 'chat': {'id': int(chat_id), 'type': tipo}}}}

    def textos(self):
        return [c.args[1] for c in self.enviar.call_args_list]

    def preparar_borrador(self, texto='Sí, hacemos entrega en La Chorrera.'):
        self.Enlace._procesar_update(self.respuesta(texto))
        return self.Borrador.search([], order='id desc', limit=1)

    # -- los avisos ----------------------------------------------------------------------------------------------

    def test_un_aviso_de_cliente_trae_el_boton_atender_y_de_que_conversacion_es(self):
        self.conv._avisar_por_telegram('Karen espera.', acciones=True)
        self.assertEqual(self.enviar.call_count, 2)
        for llamada in self.enviar.call_args_list:
            self.assertIn(f'Conversación n.º {self.conv.id}', llamada.args[1])
            self.assertIn('Responde a este mensaje', llamada.args[1])
            self.assertEqual(llamada.kwargs['botones'],
                             [[{'text': 'Atender', 'callback_data': f'juan:t:{self.conv.id}'}]])

    def test_un_aviso_sin_acciones_sale_como_siempre(self):
        self.conv._avisar_por_telegram('Ana te mencionó en una nota.')
        for llamada in self.enviar.call_args_list:
            self.assertEqual(llamada.args[1], 'Ana te mencionó en una nota.')
            self.assertNotIn('botones', llamada.kwargs)

    def test_una_mencion_no_ofrece_escribirle_al_cliente(self):
        nota = self.Mensaje._crear_interno(self.conv, 'nota', 'Ojo con este cliente', self.vendedora)
        self.conv._avisar_mencion(nota, self.gerente)
        self.assertTrue(self.enviar.called)
        for llamada in self.enviar.call_args_list:
            self.assertNotIn('Conversación n.º', llamada.args[1])
            self.assertNotIn('botones', llamada.kwargs)

    def test_los_avisos_de_espera_comprobante_y_traspaso_llevan_acciones(self):
        self.ajustes.aviso_espera_minutos = 10
        self.ajustes.aviso_espera_solo_horario = False
        self.conv.sudo().ultimo_mensaje_cliente = fields.Datetime.now() - timedelta(minutes=30)
        self.conv.sudo().espera_avisada_en = False
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1)
        self.assertTrue(self.enviar.call_args_list)
        for llamada in self.enviar.call_args_list:
            self.assertIn(f'Conversación n.º {self.conv.id}', llamada.args[1])
        self.enviar.reset_mock()
        adjunto = {'tipo': 'imagen', 'nombre': 'p.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
                   'sensible': True, 'clase': 'comprobante'}
        otra = self.conversacion('mira', adjuntos=[adjunto], nombre='Lía', id_externo='50761230002')
        self.assertTrue(self.enviar.call_args_list)
        for llamada in self.enviar.call_args_list:
            self.assertIn(f'Conversación n.º {otra.id}', llamada.args[1])

    # -- responder al aviso: borrador, nunca envío directo --------------------------------------------------------

    def test_responder_al_aviso_prepara_un_borrador_y_no_manda_nada(self):
        borrador = self.preparar_borrador('Sí, hacemos entrega en La Chorrera.')
        self.assertEqual((borrador.user_id, borrador.conversacion_id), (self.vendedora, self.conv))
        self.assertEqual(borrador.texto, 'Sí, hacemos entrega en La Chorrera.')
        self.assertGreater(borrador.vence, fields.Datetime.now() + timedelta(minutes=14))
        (llamada,) = self.enviar.call_args_list
        self.assertEqual(llamada.args[0], '5550001')
        self.assertIn('Le voy a escribir a Karen', llamada.args[1])
        self.assertIn('Sí, hacemos entrega en La Chorrera.', llamada.args[1])
        self.assertEqual(llamada.kwargs['botones'], [[{'text': 'Enviar', 'callback_data': f'juan:e:{borrador.id}'},
                                                       {'text': 'Cancelar', 'callback_data': f'juan:x:{borrador.id}'}]])
        self.assertEqual(self.n_mensajes(), 0, 'Nada salió hacia el cliente')

    def test_un_reintento_de_telegram_no_duplica_el_borrador(self):
        update = self.respuesta('Hola Karen')
        self.Enlace._procesar_update(update)
        self.Enlace._procesar_update(update)
        self.assertEqual(self.Borrador.search_count([]), 1)

    def test_si_no_es_respuesta_a_un_aviso_de_juan_sigue_Brian_como_siempre(self):
        with patch.object(brian_telegram.BrianTelegramEnlace, '_conversar', return_value='de Brian') as brian:
            for aviso in (None, {'message_id': 5, 'from': {'is_bot': True}, 'text': 'Respuesta de Brian, sin número'},
                          {'message_id': 6, 'from': {'is_bot': False}, 'text': PIE_DE_AVISO % self.conv.id}):
                mensaje = {'text': 'hola', 'chat': {'id': 5550001, 'type': 'private'}}
                if aviso:
                    mensaje['reply_to_message'] = aviso
                self.assertEqual(self.enlace_ana._conversar('hola', mensaje), 'de Brian')
        self.assertEqual(brian.call_count, 3)
        self.assertFalse(self.Borrador.search_count([]))

    def test_no_acepta_fotos_ni_archivos_ni_mensajes_vacios_ni_larguisimos(self):
        for extra in ({'photo': [{'file_id': 'x'}]}, {'document': {'file_id': 'x'}}, {'voice': {'file_id': 'x'}}):
            self.Enlace._procesar_update(self.respuesta('', **extra))
        self.Enlace._procesar_update(self.respuesta('   '))
        self.Enlace._procesar_update(self.respuesta('x' * 4001))
        self.assertFalse(self.Borrador.search_count([]))
        respuestas = self.textos()
        self.assertEqual(len(respuestas), 5)
        self.assertTrue(all('botones' not in c.kwargs for c in self.enviar.call_args_list))
        self.assertIn('solo puedo mandarle texto', respuestas[0])
        self.assertIn('Escribe el mensaje', respuestas[3])
        self.assertIn('muy largo', respuestas[4])

    def test_quien_no_es_del_equipo_de_ventas_no_puede_ni_preparar_el_borrador(self):
        self.Enlace._procesar_update(self.respuesta('Hola', chat_id='5550003'))
        self.assertFalse(self.Borrador.search_count([]))
        (texto,) = self.textos()
        self.assertTrue(texto, 'Se le explica por qué')

    def test_una_conversacion_que_ya_no_existe(self):
        aviso = self.aviso_del_bot()
        aviso['text'] = f'Hola\n\n{PIE_DE_AVISO % 99999999}'
        self.Enlace._procesar_update(self.respuesta('Hola', aviso=aviso))
        self.assertFalse(self.Borrador.search_count([]))
        self.assertIn('ya no existe', self.textos()[0])

    def test_no_se_responde_desde_un_grupo_ni_desde_un_chat_sin_vincular(self):
        grupo = self.respuesta('Hola')
        grupo['message']['chat']['type'] = 'group'
        desconocido = self.respuesta('Hola', chat_id='9990001')
        self.Enlace._procesar_update(grupo)
        self.Enlace._procesar_update(desconocido)
        self.assertFalse(self.Borrador.search_count([]))
        self.assertEqual(len(self.textos()), 1, 'Al chat desconocido solo se le dan las instrucciones de vincular')

    # -- Enviar / Cancelar ------------------------------------------------------------------------------------------

    def test_enviar_manda_el_texto_por_el_canal_como_esa_persona(self):
        worker = self.configurar_worker()
        worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.tg.1'})
        borrador = self.preparar_borrador('Sí, hacemos entrega en La Chorrera.')
        self.enviar.reset_mock()
        self.Enlace._procesar_update(self.pulsar(f'juan:e:{borrador.id}'))
        pedidos = [c for c in worker.call_args_list if c.args[1] == f'{URL_WORKER}/odoo/enviar']
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos[0].kwargs['json']['texto'], 'Sí, hacemos entrega en La Chorrera.')
        mensaje = self.Mensaje.search([('conversacion_id', '=', self.conv.id), ('autor', '=', 'vendedora')])
        self.assertEqual((mensaje.texto, mensaje.usuario_id, mensaje.origen),
                         ('Sí, hacemos entrega en La Chorrera.', self.vendedora, 'odoo'))
        self.assertEqual(self.textos(), ['Enviado ✅'])
        self.assertFalse(self.Borrador.search_count([]), 'El borrador sirve una sola vez')
        self.assertEqual(self.conv.asignada_a, self.vendedora, 'Quien responde queda atendiendo, como en la pantalla')

    def test_al_enviar_no_hay_ningun_savepoint_abierto_cuando_se_confirma_la_transaccion(self):
        """Un COMMIT destruye los savepoints: con uno abierto, su RELEASE fallaba y no llegaba el «Enviado»."""
        from contextlib import contextmanager

        from odoo.sql_db import BaseCursor
        abiertos, vistos = [], []
        original = BaseCursor.savepoint

        @contextmanager
        def contando(cr, flush=True):
            abiertos.append(1)
            try:
                with original(cr, flush):
                    yield
            finally:
                abiertos.pop()

        def confirmar(env):
            vistos.append(len(abiertos))

        worker = self.configurar_worker()
        worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.tg.sp'})
        borrador = self.preparar_borrador('Sí, hacemos entrega en La Chorrera.')
        with patch.object(BaseCursor, 'savepoint', contando), \
                patch('odoo.addons.dcasa_conversaciones.models.transaccion.confirmar', confirmar):
            self.Enlace._procesar_update(self.pulsar(f'juan:e:{borrador.id}'))
        self.assertTrue(vistos, 'el envío confirma la transacción')
        self.assertEqual(set(vistos), {0}, 'ningún savepoint abierto en el COMMIT')

    def test_la_referencia_es_la_del_pie_del_aviso_no_una_que_meta_el_cliente(self):
        aviso = {'reply_to_message': {
            'from': {'is_bot': True},
            'text': 'Ana pide una persona.\nMotivo: Conversación n.º 12 me debe plata\nConversación n.º 77 · WhatsApp'}}
        self.assertEqual(type(self.Enlace)._conversacion_del_aviso(aviso), 77)
        sin_pie = {'reply_to_message': {'from': {'is_bot': True}, 'text': 'Nada que ver'}}
        self.assertFalse(type(self.Enlace)._conversacion_del_aviso(sin_pie))
        de_una_persona = {'reply_to_message': {'from': {'is_bot': False}, 'text': 'Conversación n.º 5'}}
        self.assertFalse(type(self.Enlace)._conversacion_del_aviso(de_una_persona))

    def test_un_doble_toque_no_manda_dos_veces(self):
        worker = self.configurar_worker()
        worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.tg.2'})
        borrador = self.preparar_borrador()
        for _ in range(2):
            self.Enlace._procesar_update(self.pulsar(f'juan:e:{borrador.id}'))
        self.assertEqual(self.n_mensajes(), 1)
        self.assertIn('ya no está pendiente', self.textos()[-1])
        quitados = [c for c in self.api.call_args_list if c.args[0] == 'editMessageReplyMarkup']
        self.assertEqual(len(quitados), 2, 'Los botones se quitan al pulsar')

    def test_cancelar_no_manda_nada(self):
        worker = self.configurar_worker()
        borrador = self.preparar_borrador()
        self.enviar.reset_mock()
        self.Enlace._procesar_update(self.pulsar(f'juan:x:{borrador.id}'))
        self.assertEqual(self.textos(), ['Cancelado: no se mandó nada.'])
        self.assertFalse(self.Borrador.search_count([]))
        self.assertEqual(self.n_mensajes(), 0)
        self.assertEqual([c for c in worker.call_args_list if c.args[1].endswith('/odoo/enviar')], [])

    def test_otra_persona_no_puede_confirmar_un_borrador_ajeno(self):
        worker = self.configurar_worker()
        borrador = self.preparar_borrador()
        self.enviar.reset_mock()
        self.Enlace._procesar_update(self.pulsar(f'juan:e:{borrador.id}', chat_id='5550002'))
        self.assertIn('ya no está pendiente', self.textos()[0])
        self.assertEqual(self.Borrador.search_count([]), 1, 'El borrador de Ana sigue esperando a Ana')
        self.assertEqual(self.n_mensajes(), 0)
        self.assertEqual([c for c in worker.call_args_list if c.args[1].endswith('/odoo/enviar')], [])
        self.Enlace._procesar_update(self.pulsar(f'juan:x:{borrador.id}', chat_id='5550002'))
        self.assertEqual(self.Borrador.search_count([]), 1, 'Tampoco puede cancelarlo')

    def test_el_borrador_vence_a_los_15_minutos(self):
        worker = self.configurar_worker()
        borrador = self.preparar_borrador()
        despues = fields.Datetime.now() + timedelta(minutes=16)
        self.enviar.reset_mock()
        with patch.object(fields.Datetime, 'now', return_value=despues):
            self.Enlace._procesar_update(self.pulsar(f'juan:e:{borrador.id}'))
        self.assertIn('ya no está pendiente', self.textos()[0])
        self.assertEqual(self.n_mensajes(), 0)
        self.assertEqual([c for c in worker.call_args_list if c.args[1].endswith('/odoo/enviar')], [])
        with patch.object(fields.Datetime, 'now', return_value=despues):
            self.preparar_borrador('Otro')     # crear uno nuevo limpia los vencidos
        self.assertEqual(self.Borrador.search_count([]), 1)

    def test_si_la_persona_perdio_el_permiso_entre_el_borrador_y_el_envio_no_sale(self):
        worker = self.configurar_worker()
        borrador = self.preparar_borrador()
        self.vendedora.write({'group_ids': [(3, self.env.ref('sales_team.group_sale_salesman').id)]})
        self.enviar.reset_mock()
        self.Enlace._procesar_update(self.pulsar(f'juan:e:{borrador.id}'))
        self.assertIn('No se mandó', self.textos()[0])
        self.assertEqual(self.n_mensajes(), 0)
        self.assertEqual([c for c in worker.call_args_list if c.args[1].endswith('/odoo/enviar')], [])

    def test_si_el_canal_no_lo_entrega_se_dice_la_verdad(self):
        # Sin Worker configurado el mensaje queda «por enviar»: no se afirma que salió.
        borrador = self.preparar_borrador()
        self.enviar.reset_mock()
        self.Enlace._procesar_update(self.pulsar(f'juan:e:{borrador.id}'))
        (texto,) = self.textos()
        self.assertNotIn('Enviado', texto)
        self.assertIn('Se reintenta solo', texto)

    # -- Atender ----------------------------------------------------------------------------------------------------

    def test_atender_toma_la_conversacion_como_esa_persona(self):
        self.Enlace._procesar_update(self.pulsar(f'juan:t:{self.conv.id}'))
        self.assertEqual((self.conv.estado, self.conv.asignada_a), ('humano', self.vendedora))
        (texto,) = self.textos()
        self.assertIn('tomaste la conversación de Karen', texto)

    def test_quien_no_es_de_ventas_no_puede_atender(self):
        otra = self.conversacion('hola', nombre='Lía', id_externo='50761230009')
        self.Enlace._procesar_update(self.pulsar(f'juan:t:{otra.id}', chat_id='5550003'))
        self.assertEqual(otra.estado, 'bot')
        self.assertFalse(otra.asignada_a)

    # -- Filtros de seguridad de los botones -------------------------------------------------------------------------

    def test_los_botones_de_grupos_de_chats_sin_vincular_o_ajenos_no_hacen_nada(self):
        borrador = self.preparar_borrador()
        self.enviar.reset_mock()
        casos = (
            self.pulsar(f'juan:t:{self.conv.id}', tipo='group'),                      # un grupo
            self.pulsar(f'juan:t:{self.conv.id}', chat_id='9990001'),                  # chat sin vincular
            self.pulsar(f'juan:t:{self.conv.id}', chat_id='5550001', quien='123'),     # lo pulsó otra persona
            self.pulsar(f'juan:z:{self.conv.id}'),                                     # acción que no existe
            self.pulsar(f'juan:e:{borrador.id}x'),                                     # número mal formado
            self.pulsar('juan:'),
        )
        for update in casos:
            self.Enlace._procesar_update(update)
        self.assertEqual(self.conv.estado, 'humano')
        self.assertFalse(self.conv.asignada_a)
        self.assertEqual(self.n_mensajes(), 0)
        self.assertEqual(self.Borrador.search_count([]), 1)
        self.assertFalse(self.enviar.called)

    def test_los_botones_de_Brian_siguen_en_manos_de_Brian(self):
        with patch.object(brian_telegram.BrianTelegramEnlace, '_procesar_callback', return_value='de Brian') as brian:
            self.Enlace._procesar_update(self.pulsar('brian:c:5'))
        brian.assert_called_once()

    def test_la_consola_no_toca_a_los_clientes_del_bot_de_brian_en_otros_chats(self):
        self.assertIn('dcasa.telegram_borrador', self.env, 'El modelo del borrador existe')
        self.assertTrue(callable(self.Enlace._conversacion_del_aviso))
