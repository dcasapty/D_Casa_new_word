"""El cliente de Resend para campañas (sin base de datos y sin red: ``requests.request`` está sustituido)."""
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import BaseCase, tagged

from ..models import resend_campanas as RC
from .comun import CLAVE_CAMPANAS, ResendFalso, respuesta


@tagged('post_install', '-at_install')
class TestClienteCampanas(BaseCase):

    def setUp(self):
        super().setUp()
        self.resend = ResendFalso()
        parche = patch('requests.request', self.resend)
        parche.start()
        self.addCleanup(parche.stop)
        self.cliente = RC.ClienteCampanas(CLAVE_CAMPANAS, pausa=0)

    def test_segmento_contactos_y_broadcast_con_la_forma_de_la_api(self):
        segmento = self.cliente.buscar_o_crear_segmento('Segmento ZZCM')
        self.assertEqual(self.cliente.buscar_o_crear_segmento('Segmento ZZCM'), segmento, 'No lo crea dos veces')
        self.cliente.agregar_contacto('ana.zzcm@example.com', None, segmento)
        self.resend.contacto('beto.zzcm@example.com')          # ya existía (otra lista): se agrega al segmento
        self.cliente.agregar_contacto('beto.zzcm@example.com', None, segmento)
        self.assertEqual(set(self.resend.en_segmento(segmento)), {'ana.zzcm@example.com', 'beto.zzcm@example.com'})
        self.assertNotIn('first_name', self.resend.llamadas[-3][2], 'Solo el correo: nada más de la persona')
        broadcast = self.cliente.crear_broadcast(segmento, '"D\'CASA Panamá" <ventas@example.com>', 'Asunto',
                                                 '<p>Hola {{{RESEND_UNSUBSCRIBE_URL}}}</p>',
                                                 responder_a='info@example.com', nombre='Novedades')
        metodo, ruta, cuerpo, _params = self.resend.llamadas[-1]
        self.assertEqual((metodo, ruta), ('POST', '/broadcasts'))
        self.assertEqual(cuerpo, {'segment_id': segmento, 'from': '"D\'CASA Panamá" <ventas@example.com>',
                                  'subject': 'Asunto', 'html': '<p>Hola {{{RESEND_UNSUBSCRIBE_URL}}}</p>',
                                  'reply_to': 'info@example.com', 'name': 'Novedades'})
        self.assertEqual(self.cliente.estado_broadcast(broadcast), 'draft')
        self.cliente.enviar_broadcast(broadcast)
        self.assertEqual(self.resend.llamadas[-1][:2], ('POST', f'/broadcasts/{broadcast}/send'))

    def test_lee_todas_las_paginas_del_segmento(self):
        segmento = self.cliente.buscar_o_crear_segmento('Grande')
        for i in range(250):
            self.resend.contacto(f'c{i}.zzcm@example.com', segmentos=[segmento])
        contactos = self.cliente.contactos_del_segmento(segmento)
        self.assertEqual(len(contactos), 250)
        paginas = [p for _m, r, _c, p in self.resend.llamadas if r.endswith('/contacts')]
        self.assertEqual(len(paginas), 3)
        self.assertEqual(paginas[0], {'limit': 100})
        self.assertIn('after', paginas[1])

    def test_dar_de_baja_y_sacar_aunque_no_exista(self):
        segmento = self.cliente.buscar_o_crear_segmento('S')
        self.resend.contacto('ana.zzcm@example.com', segmentos=[segmento])
        self.cliente.dar_de_baja('ana.zzcm@example.com')
        self.assertTrue(self.resend.contactos['ana.zzcm@example.com']['unsubscribed'])
        self.cliente.sacar_del_segmento('ana.zzcm@example.com', segmento)
        self.assertEqual(self.resend.en_segmento(segmento), {})
        self.assertEqual(self.cliente.dar_de_baja('nadie@example.com'), {}, 'Si no existe, no hay nada que hacer')
        self.assertEqual(self.cliente.sacar_del_segmento('nadie@example.com', segmento), {})

    def test_la_clave_de_solo_envio_se_dice_en_palabras_sencillas(self):
        self.resend.fallar.append(('GET', '/segments', 401, 'This API key is restricted to only send emails.'))
        with self.assertRaises(RC.ErrorResend) as error:
            self.cliente.buscar_o_crear_segmento('S')
        self.assertIn('Full access', error.exception.mensaje)
        self.assertNotIn(CLAVE_CAMPANAS, str(error.exception))

    def test_espera_con_429_y_no_suelta_la_clave(self):
        llamadas = MagicMock(side_effect=[
            respuesta(429, {'message': 'Too many requests'}, {'retry-after': '1'}),
            respuesta(200, {'data': []})])
        with patch('requests.request', llamadas):
            self.assertEqual(self.cliente._llamar('GET', '/segments'), {'data': []})
        self.assertEqual(llamadas.call_count, 2)
        eco = MagicMock(return_value=respuesta(500, {'message': f'falló con {CLAVE_CAMPANAS} y ana@example.com'}))
        with patch('requests.request', eco), self.assertRaises(RC.ErrorResend) as error:
            self.cliente._llamar('GET', '/segments')
        self.assertTrue(error.exception.temporal)
        self.assertNotIn(CLAVE_CAMPANAS, error.exception.mensaje)
        self.assertNotIn('ana@example.com', error.exception.mensaje)
        self.assertNotIn(CLAVE_CAMPANAS, repr(self.cliente))

    def test_sin_red_es_temporal(self):
        with patch('requests.request', MagicMock(side_effect=requests.ConnectionError('sin red'))), \
                self.assertRaises(RC.ErrorResend) as error:
            self.cliente._llamar('GET', '/segments')
        self.assertTrue(error.exception.temporal)
