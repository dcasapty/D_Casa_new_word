"""Ola 2 · reparto por turnos: cuando el asistente pasa una conversación a una persona y nadie la tenía, le toca a quien
lleva más tiempo sin recibir una, entre quienes están disponibles."""
from unittest.mock import MagicMock, patch

from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import JuanCase


@tagged('post_install', '-at_install')
class TestRepartoPorTurnos(JuanCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.beto = new_test_user(cls.env, login='juan_beto', name='Beto Vendedor',
                                 groups='base.group_user,sales_team.group_sale_salesman')
        cls.carla = new_test_user(cls.env, login='juan_carla', name='Carla Vendedora',
                                  groups='base.group_user,sales_team.group_sale_salesman')

    def setUp(self):
        super().setUp()
        self.ajustes.reparto_modo = 'turnos'
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.enviar = MagicMock()
        parche = patch.object(type(self.Enlace), '_enviar', self.enviar)
        parche.start()
        self.addCleanup(parche.stop)
        # Las vendedoras de prueba: Ana, Beto y Carla (Gerencia y administradores no reciben: ver test_reparto_justo).
        self.equipo = self.vendedora | self.beto | self.carla
        self.Conversacion._usuarios_del_panel().write({'dcasa_disponible': False, 'dcasa_turno': 0})
        self.equipo.write({'dcasa_disponible': True})

    def pasar(self, n):
        conv = self.conversacion(nombre=f'Cliente {n}', id_externo=f'5076100{n:04d}')
        conv._pasar_a_vendedora('Quiere una cotización')
        return conv

    def test_por_defecto_nadie_reparte(self):
        self.ajustes.reparto_modo = 'manual'
        conv = self.pasar(1)
        self.assertFalse(conv.asignada_a)

    def test_le_toca_a_quien_lleva_mas_tiempo_sin_recibir_y_el_turno_rota(self):
        self.vendedora.dcasa_turno = 30
        self.beto.dcasa_turno = 10
        self.carla.dcasa_turno = 20
        orden = [self.pasar(n).asignada_a for n in range(1, 5)]
        self.assertEqual(orden, [self.beto, self.carla, self.vendedora, self.beto])

    def test_quien_nunca_recibio_va_primero(self):
        self.vendedora.dcasa_turno = 4
        self.assertIn(self.pasar(1).asignada_a, (self.beto, self.carla))

    def test_solo_entre_quienes_estan_disponibles(self):
        (self.beto | self.carla).dcasa_disponible = False
        self.assertEqual([self.pasar(n).asignada_a for n in range(1, 4)], [self.vendedora] * 3)

    def test_si_nadie_esta_disponible_sigue_el_camino_de_siempre(self):
        self.equipo.dcasa_disponible = False
        conv = self.pasar(1)
        self.assertFalse(conv.asignada_a)
        actividad = conv.activity_ids
        self.assertEqual(actividad.user_id, self.ajustes.responsable_id)

    def test_una_conversacion_que_ya_tenia_quien_la_atendiera_no_se_reparte(self):
        conv = self.conversacion(nombre='Ya asignada')
        conv.asignada_a = self.vendedora
        conv._pasar_a_vendedora('Duda')
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertFalse(self.beto.dcasa_turno, 'No gasta el turno de nadie')

    def test_la_actividad_y_el_aviso_van_a_quien_le_toco(self):
        self.Enlace.create({'user_id': self.beto.id, 'chat_id': '5550003'})
        self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.vendedora.dcasa_turno = 5
        self.carla.dcasa_turno = 6
        conv = self.pasar(1)
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertEqual(conv.activity_ids.user_id, self.beto)
        (destino, texto), = [c.args for c in self.enviar.call_args_list]
        self.assertEqual(destino, '5550003', 'Solo a quien le tocó')
        self.assertIn('Te tocó a ti', texto)
        avisos = [m.texto for m in conv.mensaje_ids if m.tipo == 'aviso']
        self.assertTrue(any('Le tocó a Beto Vendedor por turno' in a for a in avisos), avisos)

    def test_si_a_quien_le_toco_no_tiene_telegram_el_aviso_va_a_las_demas(self):
        self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.beto.dcasa_turno = 7
        self.carla.dcasa_turno = 8
        conv = self.pasar(1)
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertEqual([c.args[0] for c in self.enviar.call_args_list], ['5550001'])

    def test_el_turno_rota_aunque_dos_lleguen_en_el_mismo_segundo(self):
        elegidas = [self.pasar(n).asignada_a for n in range(1, 7)]
        self.assertEqual(sorted(e.id for e in elegidas[:3]), sorted(self.equipo.ids), 'Las tres, una vez cada una')
        self.assertEqual(elegidas[:3], elegidas[3:], 'Y vuelta a empezar en el mismo orden')

    def test_el_juan_tecnico_no_entra_al_reparto(self):
        for n in range(1, 8):
            self.assertNotEqual(self.pasar(n).asignada_a, self.juan)


@tagged('post_install', '-at_install')
class TestDisponibilidad(JuanCase):

    def setUp(self):
        super().setUp()
        self.panel = self.Conversacion.with_user(self.vendedora)

    def test_cada_persona_cambia_solo_la_suya(self):
        self.assertTrue(self.panel.iniciar_panel()['usuario']['disponible'])
        self.assertEqual(self.panel.fijar_disponible(False), {'disponible': False})
        self.assertFalse(self.vendedora.dcasa_disponible)
        self.assertTrue(self.gerente.dcasa_disponible)
        self.assertFalse(self.panel.iniciar_panel()['usuario']['disponible'])
        self.panel.fijar_disponible(True)
        self.assertTrue(self.vendedora.dcasa_disponible)

    def test_la_pantalla_conoce_el_modo_de_reparto(self):
        self.assertEqual(self.panel.iniciar_panel()['reparto'], 'manual')
        self.ajustes.reparto_modo = 'turnos'
        self.assertEqual(self.panel.iniciar_panel()['reparto'], 'turnos')

    def test_valida_lo_que_recibe_y_exige_ser_de_ventas(self):
        for malo in ('si', 1, None, [True]):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.fijar_disponible(malo)
        for usuario in (self.interno, self.portal):
            with self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.conversacion'], 'fijar_disponible', [False], {})

    def test_no_se_puede_cambiar_por_escritura_directa(self):
        """El campo no es de los que una persona puede escribirse sola: solo por el método de arriba."""
        with self.assertRaises(AccessError):
            self.vendedora.with_user(self.vendedora).write({'dcasa_disponible': False})
