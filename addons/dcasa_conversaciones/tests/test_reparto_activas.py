"""Reparto con vendedoras de verdad (pedido de la dueña, 2026-11-03): los turnos rotan y quien no vino no entró al
sistema ni se marcó «No disponible». Juan solo le pasa clientes a quien está activa (usó Odoo o le escribió a un
cliente hace poco) y, si a quien le tocó no le contesta al cliente en 15 minutos, el cliente pasa solo a otra."""
from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .test_reparto_justo import RepartoCase, panama


@tagged('post_install', '-at_install')
class TestSoloRecibenLasActivas(RepartoCase):

    def setUp(self):
        super().setUp()
        self.ajustes.write({'reparto_activa_minutos': 30, 'reparto_reasignar_minutos': 15})
        self.env['mail.presence'].sudo().search([('user_id', 'in', self.equipo.ids)]).unlink()

    def activa(self, usuario, hace_minutos=1):
        """``usuario`` usó Odoo (teclado o ratón) hace ``hace_minutos``."""
        Presencia = self.env['mail.presence'].sudo()
        momento = self.ahora() - timedelta(minutes=hace_minutos)
        presencia = Presencia.search([('user_id', '=', usuario.id)])
        if presencia:
            presencia.write({'last_presence': momento, 'status': 'online'})
        else:
            Presencia.create({'user_id': usuario.id, 'last_presence': momento, 'status': 'online'})

    def ahora(self):
        return fields.Datetime.now()

    # --- De fábrica ---------------------------------------------------------------------------------------------

    def test_de_fabrica_30_minutos_de_actividad_y_15_para_pasar_a_otra(self):
        por_defecto = self.env['dcasa.juan.ajustes'].default_get(
            ['reparto_activa_minutos', 'reparto_reasignar_minutos'])
        self.assertEqual(por_defecto, {'reparto_activa_minutos': 30, 'reparto_reasignar_minutos': 15})

    def test_los_minutos_tienen_limites(self):
        for campo, malos, buenos in (('reparto_activa_minutos', (-1, 481), (0, 30, 480)),
                                     ('reparto_reasignar_minutos', (-1, 4, 241), (0, 5, 15, 240))):
            for malo in malos:
                with self.subTest(campo=campo, valor=malo), self.assertRaises(ValidationError):
                    self.ajustes.write({campo: malo})
            for bueno in buenos:
                self.ajustes.write({campo: bueno})

    # --- Solo reciben las activas ----------------------------------------------------------------------------------

    def test_quien_no_vino_no_recibe_aunque_este_disponible(self):
        self.activa(self.vendedora, 5)
        self.activa(self.beto, 120)       # usó Odoo hace dos horas: se fue o no volvió
        # Carla no entró hoy: ni presencia
        asignadas = {self.pasar().asignada_a for _n in range(4)}
        self.assertEqual(asignadas, {self.vendedora})
        self.assertTrue(self.beto.dcasa_disponible and self.carla.dcasa_disponible,
                        'Nadie tuvo que marcarlas «No disponible»')

    def test_escribirle_a_un_cliente_tambien_cuenta_como_activa(self):
        """Desde Telegram se le contesta al cliente sin abrir Odoo: eso también es estar trabajando."""
        otro = self.cliente()
        self.Mensaje.sudo().create({
            'conversacion_id': otro.id, 'tipo': 'mensaje', 'autor': 'vendedora', 'direccion': 'saliente',
            'texto': 'Hola', 'usuario_id': self.carla.id, 'ts': self.ahora() - timedelta(minutes=10),
            'id_mensaje': 'telegram.carla.1'})
        self.assertEqual(self.pasar().asignada_a, self.carla)

    def test_con_cero_minutos_no_se_mira_y_reciben_todas_las_disponibles(self):
        self.ajustes.reparto_activa_minutos = 0
        asignadas = {self.pasar().asignada_a for _n in range(6)}
        self.assertEqual(asignadas, set(self.equipo))

    def test_por_turnos_tambien_mira_quien_esta_activa(self):
        self.ajustes.reparto_modo = 'turnos'
        self.activa(self.beto, 2)
        self.assertEqual({self.pasar().asignada_a for _n in range(3)}, {self.beto})

    def test_si_nadie_esta_activa_queda_sin_duena_y_se_avisa_a_todo_el_equipo(self):
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.assertIn('Nadie estaba disponible para recibirla', self.avisos(conv))

    def test_la_pantalla_reparto_muestra_quien_no_tiene_actividad(self):
        self.activa(self.vendedora, 5)
        self.activa(self.beto, 90)
        filas = {f['usuario_id']: f for f in self.env['dcasa.juan.panel'].with_user(self.gerente).reparto()['equipo']}
        self.assertEqual(filas[self.vendedora.id]['estado'], 'disponible')
        self.assertEqual(filas[self.beto.id]['estado'], 'inactiva')
        self.assertTrue(filas[self.beto.id]['activa_en'])
        self.assertEqual((filas[self.carla.id]['estado'], filas[self.carla.id]['activa_en']), ('inactiva', None))
        self.carla.dcasa_disponible = False
        estado = {f['usuario_id']: f['estado'] for f in
                  self.env['dcasa.juan.panel'].with_user(self.gerente).reparto()['equipo']}[self.carla.id]
        self.assertEqual(estado, 'no_disponible', '«No disponible» manda sobre «Sin actividad»')

    # --- Pasa a otra si no contesta ---------------------------------------------------------------------------------

    def test_si_no_contesta_en_15_minutos_pasa_a_otra_activa_y_se_avisa_a_gerencia(self):
        self.activa(self.vendedora, 2)
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.Enlace.create({'user_id': self.beto.id, 'chat_id': '5550003'})
        self.Enlace.create({'user_id': self.gerente.id, 'chat_id': '5550777'})
        with freeze_time(self.AHORA + timedelta(minutes=14)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0, 'A los 14 minutos todavía tiene tiempo')
        self.enviar.reset_mock()
        with freeze_time(self.AHORA + timedelta(minutes=16)):
            self.assertEqual(self.Reparto._cron_reasignar(), 1)
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn('Vendedora Prueba no le contestó al cliente en 15 minutos: pasó a Beto Vendedor.',
                      self.avisos(conv))
        destinos = [c.args[0] for c in self.enviar.call_args_list]
        self.assertIn('5550003', destinos, 'A Beto le llega «Te tocó a ti»')
        self.assertIn('5550777', destinos, 'Gerencia se entera')
        libro = self.Reparto.search([('conversacion_id', '=', conv.id)], order='id desc', limit=1)
        self.assertEqual((libro.usuario_id, libro.regla), (self.beto, 'reasignada'))
        self.assertEqual(self.recibidas(self.beto), 1, 'Cuenta como una que recibió hoy')

    def test_el_aviso_de_juan_al_cliente_no_cuenta_como_respuesta(self):
        """Después de pasarla, Juan le dice al cliente «ya avisé a una vendedora»: el cliente sigue esperando."""
        self.activa(self.vendedora, 2)
        conv = self.pasar()
        self.registrar('Listo, ya avisé a una vendedora para que te atienda por aquí.', id_externo=conv.id_externo,
                       autor='bot', ts=self.ahora() + timedelta(seconds=5))
        self.assertEqual(conv.ultimo_mensaje_autor, 'bot')
        with freeze_time(self.AHORA + timedelta(minutes=16)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 1)
        self.assertEqual(conv.asignada_a, self.beto)

    def test_si_vence_la_pausa_y_vuelve_al_asistente_no_se_mueve(self):
        self.activa(self.vendedora, 2)
        conv = self.pasar()
        conv.sudo().pausada_hasta = self.ahora() + timedelta(minutes=5)
        with freeze_time(self.AHORA + timedelta(minutes=10)):
            conv._normalizar_pausa()
            self.assertEqual(conv.estado, 'bot')
            self.assertFalse(conv.reparto_desde)
        with freeze_time(self.AHORA + timedelta(minutes=20)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0)

    def test_no_vuelve_a_quien_ya_la_tuvo_y_sigue_pasando_si_nadie_contesta(self):
        for usuario in self.equipo:
            self.activa(usuario, 1)
        conv = self.pasar()
        primera = conv.asignada_a
        with freeze_time(self.AHORA + timedelta(minutes=16)):
            for usuario in self.equipo:
                self.activa(usuario, 1)
            self.Reparto._cron_reasignar()
        segunda = conv.asignada_a
        self.assertNotIn(segunda, primera)
        with freeze_time(self.AHORA + timedelta(minutes=32)):
            for usuario in self.equipo:
                self.activa(usuario, 1)
            self.Reparto._cron_reasignar()
        tercera = conv.asignada_a
        self.assertEqual(len(primera | segunda | tercera), 3, 'Pasó por las tres, sin repetir')
        with freeze_time(self.AHORA + timedelta(minutes=48)):
            for usuario in self.equipo:
                self.activa(usuario, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0, 'Ya no queda nadie nueva: se queda con la última')
        self.assertEqual(conv.asignada_a, tercera)

    def test_si_le_contesto_no_pasa_a_nadie_aunque_el_cliente_vuelva_a_escribir(self):
        """Revisión adversarial: la vendedora contestó y el cliente respondió «ok, gracias»; eso no es «no le
        contestó» (antes se la quitaban y le decían a Gerencia que no contestó)."""
        self.activa(self.vendedora, 2)
        self.activa(self.beto, 2)
        conv = self.pasar()
        duena = conv.asignada_a
        self.registrar('Hola, te atiendo yo', id_externo=conv.id_externo, autor='vendedora',
                       ts=self.ahora() + timedelta(minutes=3))
        self.assertEqual(conv.ultimo_mensaje_autor, 'vendedora')
        self.registrar('Ok, gracias', id_externo=conv.id_externo, ts=self.ahora() + timedelta(minutes=5))
        self.assertEqual(conv.ultimo_mensaje_autor, 'cliente')
        with freeze_time(self.AHORA + timedelta(minutes=40)):
            for usuario in self.equipo:
                self.activa(usuario, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertEqual(conv.asignada_a, duena)

    def test_un_mensaje_programado_no_la_hace_activa(self):
        """Programar un mensaje para mañana no es estar trabajando ahora."""
        otro = self.cliente()
        self.Mensaje.sudo().create({
            'conversacion_id': otro.id, 'tipo': 'mensaje', 'autor': 'vendedora', 'direccion': 'saliente',
            'texto': 'Buenos días', 'usuario_id': self.carla.id, 'ts': self.ahora() + timedelta(hours=20),
            'estado_envio': 'programado', 'programado_para': self.ahora() + timedelta(hours=20),
            'id_mensaje': 'odoo-programado-carla'})
        self.assertNotIn(self.carla.id, self.Reparto._ultima_actividad(self.carla))
        self.assertFalse(self.pasar().asignada_a)

    def test_lo_de_antes_de_abrir_no_cuenta_como_minutos_sin_contestar(self):
        with freeze_time(panama(2026, 10, 9, 7, 50)):
            self.activa(self.vendedora, 1)
            conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.vendedora)
        with freeze_time(panama(2026, 10, 9, 8, 10)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0, 'Desde las 8:00 solo van 10 minutos')
        with freeze_time(panama(2026, 10, 9, 8, 16)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 1)
        self.assertEqual(conv.asignada_a, self.beto)

    def test_si_vuelve_a_pasarsela_el_mismo_dia_cuenta_de_nuevo(self):
        """La tomó, la devolvió al asistente y Juan se la vuelve a pasar: si esta vez no contesta, pasa a otra."""
        self.activa(self.vendedora, 2)
        conv = self.pasar()
        conv._tomar(self.vendedora)
        conv._devolver(self.vendedora)
        with freeze_time(self.AHORA + timedelta(minutes=30)):
            self.activa(self.vendedora, 1)
            conv._pasar_a_vendedora('Volvió a pedir una persona')
            self.assertEqual(conv.asignada_a, self.vendedora)
        with freeze_time(self.AHORA + timedelta(minutes=46)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 1)
        self.assertEqual(conv.asignada_a, self.beto)

    def test_si_gerencia_la_deja_sin_asignar_el_reparto_no_la_toma(self):
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.Conversacion.with_user(self.gerente).asignar(conv.id, None)
        with freeze_time(self.AHORA + timedelta(minutes=20)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertFalse(conv.asignada_a)

    def test_lo_que_una_persona_tomo_o_asigno_a_mano_no_se_toca(self):
        for usuario in self.equipo:
            self.activa(usuario, 1)
        tomada = self.pasar()
        tomada._tomar(tomada.asignada_a)
        asignada = self.pasar()
        self.Conversacion.with_user(self.gerente).asignar(asignada.id, self.carla.id)
        with freeze_time(self.AHORA + timedelta(minutes=30)):
            for usuario in self.equipo:
                self.activa(usuario, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertEqual(asignada.asignada_a, self.carla)

    def test_fuera_del_horario_no_pasa_nada(self):
        self.activa(self.vendedora, 2)
        conv = self.pasar()
        with freeze_time(panama(2026, 10, 9, 18, 30)):
            self.activa(self.beto, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertEqual(conv.asignada_a, self.vendedora)

    def test_apagado_con_cero_minutos_o_con_el_reparto_manual(self):
        self.activa(self.vendedora, 2)
        conv = self.pasar()
        for cambio in ({'reparto_reasignar_minutos': 0}, {'reparto_reasignar_minutos': 15, 'reparto_modo': 'manual'}):
            self.ajustes.write(cambio)
            with self.subTest(cambio=cambio), freeze_time(self.AHORA + timedelta(minutes=30)):
                self.activa(self.beto, 1)
                self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertEqual(conv.asignada_a, self.vendedora)

    def test_la_que_quedo_sin_duena_se_le_da_a_la_primera_que_se_activa(self):
        conv = self.pasar()
        self.assertFalse(conv.asignada_a, 'A las 10:00 nadie había entrado')
        with freeze_time(self.AHORA + timedelta(minutes=16)):
            self.activa(self.carla, 1)
            self.assertEqual(self.Reparto._cron_reasignar(), 1)
        self.assertEqual(conv.asignada_a, self.carla)
        self.assertIn('Nadie la tenía: pasó a Carla Vendedora, que está activa.', self.avisos(conv))

    def test_si_nadie_mas_esta_activa_se_queda_con_la_que_la_tiene(self):
        self.activa(self.vendedora, 2)
        conv = self.pasar()
        with freeze_time(self.AHORA + timedelta(minutes=20)):
            self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertEqual(conv.asignada_a, self.vendedora)
