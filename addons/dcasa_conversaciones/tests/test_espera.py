"""Ola 2 · el cliente que espera: aviso por Telegram a quien lo atiende y cuánto lleva esperando, en la lista."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import JuanCase

# Un lunes a media mañana en Panamá (UTC-5): dentro del horario laboral por defecto (8:00 a 17:00).
LUNES_10AM = datetime(2026, 10, 12, 15, 0)


@tagged('post_install', '-at_install')
class TestClienteEsperando(JuanCase):

    def setUp(self):
        super().setUp()
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.enlace_ana = self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.enlace_gema = self.Enlace.create({'user_id': self.gerente.id, 'chat_id': '5550002'})
        self.enviar = MagicMock()
        parche = patch.object(type(self.Enlace), '_enviar', self.enviar)
        parche.start()
        self.addCleanup(parche.stop)
        self.ahora = LUNES_10AM
        reloj = patch.object(fields.Datetime, 'now', staticmethod(lambda: self.ahora))
        reloj.start()
        self.addCleanup(reloj.stop)
        self.ajustes.aviso_espera_minutos = 10
        self.ajustes.aviso_espera_solo_horario = True
        # Las vendedoras y la gerente reciben avisos; la prueba elige a quién.
        self.ajustes.usuarios_aviso_ids = [(6, 0, (self.vendedora | self.gerente).ids)]

    def espera(self, minutos=15, atiende=None, **kw):
        """Una conversación en manos de una persona cuyo cliente escribió hace ``minutos``."""
        conv = self.conversacion(nombre='Karen', ts=self.ahora - timedelta(minutes=minutos), **kw)
        if atiende:
            conv.with_user(atiende).action_atender()   # quien la toma queda como quien la atiende
        else:
            conv._poner_en_humano()   # como cuando el asistente la pasa a una vendedora: nadie la tiene todavía
        return conv

    def destinos(self):
        return sorted(c.args[0] for c in self.enviar.call_args_list)

    def textos(self):
        return [c.args[1] for c in self.enviar.call_args_list]

    def test_avisa_a_quien_la_atiende_cuando_pasa_el_tiempo(self):
        conv = self.espera(15, atiende=self.vendedora)
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1)
        self.assertEqual(self.destinos(), ['5550001'], 'Solo a quien la atiende')
        (texto,) = self.textos()
        self.assertIn('Karen lleva 15 min esperando respuesta', texto)
        self.assertIn('La atiende Vendedora Prueba', texto)
        self.assertEqual(conv.espera_avisada_en, self.ahora)

    def test_no_avisa_antes_de_tiempo(self):
        self.espera(9)
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0)
        self.assertFalse(self.enviar.called)

    def test_una_sola_vez_por_espera_y_otra_vez_si_el_cliente_vuelve_a_escribir_sin_respuesta(self):
        conv = self.espera(15, atiende=self.vendedora)
        self.Conversacion._avisar_clientes_esperando()
        self.ahora += timedelta(minutes=5)
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0, 'La misma espera no se avisa dos veces')
        # El cliente insiste y sigue sin respuesta.
        self.registrar('¿Hola? ¿alguien?', id_externo=conv.id_externo, ts=self.ahora)
        self.ahora += timedelta(minutes=12)
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1)
        self.assertEqual(len(self.textos()), 2)

    def test_sin_quien_la_atienda_avisa_a_las_personas_de_siempre(self):
        self.espera(15)
        self.Conversacion._avisar_clientes_esperando()
        self.assertEqual(self.destinos(), ['5550001', '5550002'])
        self.assertIn('Nadie la atiende todavía', self.textos()[0])

    def test_si_quien_la_atiende_no_tiene_telegram_avisa_a_las_demas(self):
        conv = self.espera(15, atiende=self.vendedora)
        self.enlace_ana.activo = False
        self.Conversacion._avisar_clientes_esperando()
        self.assertEqual(self.destinos(), ['5550002'])
        self.assertTrue(conv.espera_avisada_en)

    def test_una_conversacion_con_el_asistente_o_ya_contestada_no_avisa(self):
        self.conversacion(nombre='Con bot', ts=self.ahora - timedelta(minutes=30), id_externo='50761000009')
        contestada = self.espera(30, id_externo='50761000008')
        self.registrar('Ya te ayudo', id_externo=contestada.id_externo, autor='vendedora',
                       ts=self.ahora - timedelta(minutes=5))
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0)
        self.assertFalse(self.enviar.called)

    def test_apagado_con_cero(self):
        self.espera(60)
        self.ajustes.aviso_espera_minutos = 0
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0)
        self.assertFalse(self.enviar.called)

    def test_fuera_del_horario_laboral_espera_a_que_abran(self):
        self.espera(60)
        self.ahora = datetime(2026, 10, 13, 2, 0)   # 21:00 del lunes en Panamá
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0)
        self.ajustes.aviso_espera_solo_horario = False
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1)

    def test_una_espera_de_mas_de_un_dia_ya_no_se_avisa(self):
        self.espera(25 * 60)
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0)

    def test_si_el_telegram_falla_no_se_rompe_el_mantenimiento_ni_se_repite_el_aviso(self):
        conv = self.espera(15, atiende=self.vendedora)
        self.enviar.side_effect = RuntimeError('sin red')
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1)
        self.assertTrue(conv.espera_avisada_en)
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0)

    def test_el_mantenimiento_de_cada_5_minutos_lo_incluye(self):
        self.espera(15, atiende=self.vendedora)
        self.configurar_worker()
        self.Conversacion._cron_mantenimiento()
        self.assertEqual(len(self.textos()), 1)

    def test_el_rango_del_ajuste(self):
        for malo in (-1, 1441):
            with self.assertRaises(ValidationError):
                self.ajustes.aviso_espera_minutos = malo
        self.ajustes.aviso_espera_minutos = 1440


@tagged('post_install', '-at_install')
class TestEsperaEnLaPantalla(JuanCase):

    def setUp(self):
        super().setUp()
        self.panel = self.Conversacion.with_user(self.vendedora)

    def test_la_fila_dice_desde_cuando_espera_solo_si_una_persona_debe_contestar(self):
        esperando = self.conversacion(nombre='Karen', id_externo='50761000001', ts=datetime(2026, 10, 9, 14, 0))
        esperando.with_user(self.vendedora).action_atender()
        con_bot = self.conversacion(nombre='Luis', id_externo='50761000002')
        contestada = self.conversacion(nombre='Marta', id_externo='50761000003')
        contestada.with_user(self.vendedora).action_atender()
        self.registrar('Ya voy', id_externo='50761000003', autor='vendedora')
        filas = {f['nombre']: f for f in self.panel.lista()['conversaciones']}
        self.assertEqual(filas['Karen']['esperando_desde'], '2026-10-09T14:00:00Z')
        self.assertIsNone(filas['Luis']['esperando_desde'])
        self.assertIsNone(filas['Marta']['esperando_desde'])
        self.assertTrue(con_bot and filas['Karen']['necesita_atencion'])

    def test_la_pantalla_conoce_el_umbral(self):
        self.ajustes.aviso_espera_minutos = 7
        self.assertEqual(self.panel.iniciar_panel()['limites']['espera_aviso_minutos'], 7)
