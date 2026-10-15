"""Reparto parejo: cuando el asistente pasa una conversación a una persona, le toca a quien lleva menos hoy (entre las
disponibles), un cliente que vuelve se queda con su vendedora, y quien está de vacaciones o ausente no recibe nada."""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged

from .common import JuanCase


def panama(anio, mes, dia, hora=0, minuto=0):
    """Una hora de Panamá (UTC−5) como UTC ingenuo, que es como guarda Odoo las fechas."""
    return datetime(anio, mes, dia, hora, minuto) + timedelta(hours=5)


class RepartoCase(JuanCase):
    """Un equipo de tres vendedoras (Ana, Beto y Carla), el reparto parejo encendido y el reloj quieto un viernes."""

    AHORA = panama(2026, 10, 9, 10, 0)    # viernes 9 de octubre, 10:00 a. m. en Panamá

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.beto = new_test_user(cls.env, login='juan_beto_justo', name='Beto Vendedor',
                                 groups='base.group_user,sales_team.group_sale_salesman')
        cls.carla = new_test_user(cls.env, login='juan_carla_justo', name='Carla Vendedora',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        cls.Reparto = cls.env['dcasa.reparto']

    def setUp(self):
        super().setUp()
        self.reloj = freeze_time(self.AHORA)
        self.reloj.start()
        self.addCleanup(self.reloj.stop)
        self.ajustes.reparto_modo = 'parejo'
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.enviar = MagicMock()
        parche = patch.object(type(self.Enlace), '_enviar', self.enviar)
        parche.start()
        self.addCleanup(parche.stop)
        # El equipo de la prueba: las vendedoras Ana, Beto y Carla. Gema (Gerencia) y el administrador de la base están
        # «disponibles» a propósito: aun así no reciben nada (solo reciben las vendedoras).
        self.equipo = self.vendedora | self.beto | self.carla
        self.administrador = self.env.ref('base.user_admin')
        self.Conversacion._usuarios_del_panel().write({'dcasa_turno': 0})
        (self.equipo | self.gerente | self.administrador).write({'dcasa_disponible': True})
        self.numero = 0

    # --- Ayudas -----------------------------------------------------------------------------------------------

    def cliente(self, **kw):
        """Un cliente nuevo que acaba de escribir (su conversación sigue con el asistente)."""
        self.numero += 1
        id_externo = f'5076200{self.numero:04d}'
        return self.conversacion(nombre=f'Cliente {id_externo}', id_externo=id_externo, **kw)

    def pasar(self, motivo='Quiere una cotización'):
        """Un cliente nuevo pasa a una vendedora. Devuelve la conversación."""
        conv = self.cliente()
        conv._pasar_a_vendedora(motivo)
        return conv

    def dar(self, usuario, cuantas):
        """Le anota ``cuantas`` conversaciones recibidas hoy a ``usuario`` sin repartir nada de verdad."""
        for _n in range(cuantas):
            self.Reparto._anotar(self.cliente(), usuario, 'parejo')

    def hacer_esperar(self, usuario, cuantos):
        """``cuantos`` clientes le esperan a ``usuario`` (conversaciones suyas, con una persona, sin responder)."""
        for _n in range(cuantos):
            self.cliente().sudo().write({'estado': 'humano', 'asignada_a': usuario.id})

    def recibidas(self, usuario=None):
        """Cuántas le pasó Juan hoy: ``{usuario: n}``, o solo el número de ``usuario``."""
        hoy = self.Reparto._hoy()
        cuentas = self.Reparto._cuentas(self.equipo, hoy, hoy)
        por_persona = {u: cuentas[u.id]['recibidas'] for u in self.equipo}
        return por_persona[usuario] if usuario else por_persona

    def avisos(self, conv):
        """Lo que el sistema escribió en el hilo, todo junto."""
        return ' '.join(m.texto for m in conv.mensaje_ids if m.tipo == 'aviso')


@tagged('post_install', '-at_install')
class TestRepartoParejo(RepartoCase):

    # --- Lo central: parejo ---------------------------------------------------------------------------------

    def test_treinta_conversaciones_entre_tres_nunca_se_separan_mas_de_una(self):
        for n in range(1, 31):
            self.pasar()
            cuentas = list(self.recibidas().values())
            self.assertLessEqual(max(cuentas) - min(cuentas), 1, f'Después de {n}: {cuentas}')
        self.assertEqual(sorted(self.recibidas().values()), [10, 10, 10])

    def test_con_cuatro_vendedoras_y_treinta_y_una_conversaciones_la_diferencia_es_de_una(self):
        self.equipo |= new_test_user(self.env, login='juan_julia_justo', name='Julia Vendedora',
                                     groups='base.group_user,sales_team.group_sale_salesman')
        for _n in range(31):
            self.pasar()
        cuentas = sorted(self.recibidas().values())
        self.assertEqual(sum(cuentas), 31)
        self.assertLessEqual(cuentas[-1] - cuentas[0], 1, cuentas)

    def test_gana_quien_lleva_menos_hoy(self):
        self.dar(self.vendedora, 2)
        self.dar(self.carla, 2)
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn(f'Le tocó a {self.beto.name}', self.avisos(conv))
        self.assertIn('Era quien llevaba menos conversaciones hoy (0)', self.avisos(conv))

    def test_quien_no_esta_disponible_se_salta(self):
        self.beto.dcasa_disponible = False
        asignadas = [self.pasar().asignada_a for _n in range(10)]
        self.assertNotIn(self.beto, asignadas)
        self.assertEqual(self.recibidas(self.vendedora), 5)
        self.assertEqual(self.recibidas(self.carla), 5)

    def test_quien_esta_fuera_del_reparto_no_recibe_aunque_este_disponible_y_conserva_sus_permisos(self):
        self.carla.write({'dcasa_fuera_del_reparto': True})
        self.assertTrue(self.carla.dcasa_disponible)
        asignadas = [self.pasar().asignada_a for _n in range(8)]
        self.assertNotIn(self.carla, asignadas)
        self.assertTrue(self.carla.has_group('sales_team.group_sale_salesman'), 'No le quita ningún permiso')

    def test_la_fecha_de_regreso_la_devuelve_al_reparto_sola(self):
        self.carla.write({'dcasa_fuera_del_reparto': True, 'dcasa_fuera_hasta': date(2026, 10, 12)})
        self.assertNotIn(self.carla, [self.pasar().asignada_a for _n in range(6)])
        with freeze_time(panama(2026, 10, 11, 23, 59)):
            self.assertNotIn(self.carla, self.Reparto._equipo(), 'Todavía no es el día')
        with freeze_time(panama(2026, 10, 12, 0, 1)):
            self.assertIn(self.carla, self.Reparto._equipo(), 'Ya llegó el día en que vuelve')

    def test_sin_fecha_de_regreso_sigue_fuera_hasta_que_gerencia_la_vuelva_a_meter(self):
        self.carla.write({'dcasa_fuera_del_reparto': True})
        with freeze_time(panama(2027, 10, 9, 10, 0)):
            self.assertNotIn(self.carla, self.Reparto._equipo())

    def test_una_persona_que_no_es_de_ventas_nunca_entra(self):
        self.interno.write({'dcasa_disponible': True})
        for _n in range(6):
            self.assertNotIn(self.pasar().asignada_a, self.interno | self.juan)

    # --- Desempates ----------------------------------------------------------------------------------------

    def test_con_empate_gana_quien_tiene_menos_clientes_esperando(self):
        # Las tres tienen 0 hoy. A Ana y a Carla les espera un cliente; a Beto, ninguno.
        self.hacer_esperar(self.vendedora, 1)
        self.hacer_esperar(self.carla, 1)
        self.assertEqual(sorted(self.recibidas().values()), [0, 0, 0])
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn('a quien menos clientes le esperaban', self.avisos(conv))

    def test_con_empate_total_gana_quien_lleva_mas_tiempo_sin_recibir(self):
        self.vendedora.dcasa_turno = 30
        self.beto.dcasa_turno = 10
        self.carla.dcasa_turno = 20
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn('más tiempo sin recibir', self.avisos(conv))

    def test_la_que_acaba_de_recibir_pasa_al_final_de_la_fila(self):
        primera = self.pasar().asignada_a
        self.assertGreater(primera.dcasa_turno, 0)
        self.assertEqual(max(self.equipo.mapped('dcasa_turno')), primera.dcasa_turno)

    def test_la_conversacion_que_se_esta_repartiendo_no_le_pesa_a_su_duena_anterior(self):
        conv = self.pasar()
        duena = conv.asignada_a
        hoy = self.Reparto._hoy()
        self.assertEqual(self.Reparto._cuentas(duena, hoy, hoy)[duena.id]['abiertas'], 1)
        self.assertEqual(self.Reparto._cuentas(duena, hoy, hoy, excepto=conv)[duena.id]['abiertas'], 0)

    def test_cada_decision_queda_en_el_libro(self):
        conv = self.pasar()
        linea = self.Reparto.search([('conversacion_id', '=', conv.id)])
        self.assertEqual((linea.usuario_id, linea.regla, linea.dia), (conv.asignada_a, 'parejo', date(2026, 10, 9)))
        self.assertEqual(linea.momento, self.AHORA)
        self.assertIn('Le tocó a', linea.razon)

    def test_la_misma_conversacion_el_mismo_dia_cuenta_una_sola_vez(self):
        conv = self.pasar()
        duena = conv.asignada_a
        conv._devolver(duena)
        conv._pasar_a_vendedora('Otra vez')
        self.assertEqual(conv.asignada_a, duena)
        self.assertEqual(self.recibidas(duena), 1)
        self.assertEqual(self.Reparto.search_count([('conversacion_id', '=', conv.id)]), 1)

    # --- El cliente que vuelve ---------------------------------------------------------------------------

    def test_el_cliente_que_vuelve_se_queda_con_su_vendedora_aunque_lleve_mas_que_las_otras(self):
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        self.dar(duena, 5)
        self.assertEqual(self.recibidas(duena), 6)
        primera._pasar_a_vendedora('Volvió a preguntar')
        self.assertEqual(primera.asignada_a, duena)
        self.assertIn(f'Sigue con {duena.name}: ya atendió a este cliente hoy', self.avisos(primera))
        self.assertEqual(self.recibidas(duena), 6, 'Era la misma conversación del mismo día: no cuenta otra vez')

    def test_si_el_cliente_vuelve_otro_dia_dentro_del_plazo_se_queda_con_ella_y_dice_hace_cuanto(self):
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        with freeze_time(panama(2026, 10, 12, 11, 0)):
            primera._pasar_a_vendedora('Volvió')
            self.assertEqual(primera.asignada_a, duena)
            self.assertIn('hace 3 días', self.avisos(primera))
            self.assertEqual(self.recibidas(duena), 1, 'Otro día, otra conversación recibida')

    def test_el_telegram_de_quien_ya_atendia_al_cliente_dice_que_es_suyo(self):
        primera = self.pasar()
        duena = primera.asignada_a
        self.Enlace.create({'user_id': duena.id, 'chat_id': '5550009'})
        primera._devolver(duena)
        self.enviar.reset_mock()
        primera._pasar_a_vendedora('Volvió')
        (destino, texto), = [c.args for c in self.enviar.call_args_list]
        self.assertEqual(destino, '5550009')
        self.assertIn('Es un cliente tuyo', texto)

    def test_pasados_los_dias_el_cliente_se_reparte_de_nuevo(self):
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        self.hacer_esperar(duena, 2)
        with freeze_time(self.AHORA + timedelta(days=15)):
            primera._pasar_a_vendedora('Volvió tarde')
            self.assertNotEqual(primera.asignada_a, duena)
            self.assertNotIn('Sigue con', self.avisos(primera))
            self.assertIn(f'Antes la tenía {duena.name}', self.avisos(primera))

    def test_el_plazo_se_cambia_en_ajustes(self):
        self.ajustes.reparto_dias_misma_vendedora = 2
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        self.hacer_esperar(duena, 2)
        with freeze_time(self.AHORA + timedelta(days=3)):
            primera._pasar_a_vendedora('Volvió')
            self.assertNotEqual(primera.asignada_a, duena, 'Con 2 días de memoria, 3 días después se reparte otra vez')

    def test_con_cero_dias_no_hay_memoria(self):
        self.ajustes.reparto_dias_misma_vendedora = 0
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        self.hacer_esperar(duena, 2)
        primera._pasar_a_vendedora('Volvió')
        self.assertNotEqual(primera.asignada_a, duena)
        self.assertNotIn('Sigue con', self.avisos(primera))

    def test_si_su_vendedora_no_esta_disponible_le_toca_a_otra_y_se_dice(self):
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        duena.dcasa_disponible = False
        primera._pasar_a_vendedora('Volvió')
        self.assertNotEqual(primera.asignada_a, duena)
        self.assertIn(f'Antes la tenía {duena.name}', self.avisos(primera))

    def test_si_su_vendedora_esta_fuera_del_reparto_tambien_se_reparte(self):
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        duena.write({'dcasa_fuera_del_reparto': True})
        primera._pasar_a_vendedora('Volvió')
        self.assertNotEqual(primera.asignada_a, duena)

    def test_el_mismo_cliente_por_otro_canal_tambien_vuelve_con_su_vendedora(self):
        primera = self.pasar()
        duena = primera.asignada_a
        otro = self.conversacion(nombre='Mismo cliente', id_externo='7770001', canal='telegram')
        otro.sudo().partner_id = primera.partner_id
        otro._pasar_a_vendedora('Misma persona, otro canal')
        self.assertEqual(otro.asignada_a, duena)

    def test_lo_que_ella_le_escribio_al_cliente_tambien_cuenta_como_haberlo_atendido(self):
        conv = self.cliente()
        conv._crear_mensaje_de_odoo('Hola, te ayudo con tu cama', usuario=self.beto)
        conv._devolver(self.beto)
        conv.sudo().asignada_a = False   # aunque el campo esté vacío, su mensaje deja huella
        self.hacer_esperar(self.beto, 2)
        conv._pasar_a_vendedora('Volvió')
        self.assertEqual(conv.asignada_a, self.beto)

    def test_una_asignacion_a_mano_tambien_cuenta_y_no_suma_a_las_recibidas(self):
        conv = self.cliente()
        self.Conversacion.with_user(self.vendedora).asignar(conv.id, self.carla.id)
        self.assertEqual(self.recibidas(self.carla), 0, 'La eligió una persona, no Juan')
        conv.sudo().write({'estado': 'bot', 'asignada_a': False})
        conv._pasar_a_vendedora('Duda')
        self.assertEqual(conv.asignada_a, self.carla, 'Pero sí es «su» cliente')

    # --- Nadie disponible -----------------------------------------------------------------------------------

    def test_si_nadie_esta_disponible_queda_con_el_responsable_y_se_avisa_a_todas(self):
        self.Enlace.create({'user_id': self.beto.id, 'chat_id': '5550003'})
        self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.equipo.write({'dcasa_disponible': False})
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.assertEqual(conv.estado, 'humano')
        self.assertEqual(conv.activity_ids.user_id, self.ajustes.responsable_id)
        self.assertEqual(sorted(c.args[0] for c in self.enviar.call_args_list), ['5550001', '5550003'])
        self.assertIn('Nadie estaba disponible', self.enviar.call_args_list[0].args[1])
        self.assertIn('Nadie estaba disponible para recibirla', self.avisos(conv))
        self.assertIn(self.ajustes.responsable_id.name, self.avisos(conv))
        self.assertFalse(self.Reparto.search([('conversacion_id', '=', conv.id)]))

    def test_si_todas_estan_fuera_del_reparto_pasa_lo_mismo(self):
        self.equipo.write({'dcasa_fuera_del_reparto': True})
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.assertEqual(conv.estado, 'humano', 'Igual el asistente calla: una persona la toma cuando pueda')
        self.assertIn('Nadie estaba disponible', self.avisos(conv))

    def test_en_cuanto_alguien_vuelve_a_estar_disponible_recibe(self):
        self.equipo.write({'dcasa_disponible': False})
        self.assertFalse(self.pasar().asignada_a)
        self.beto.dcasa_disponible = True
        self.assertEqual(self.pasar().asignada_a, self.beto)

    # --- Los días y los otros modos -------------------------------------------------------------------------

    def test_la_cuenta_de_hoy_cambia_a_medianoche_de_panama_no_de_utc(self):
        with freeze_time(panama(2026, 10, 9, 23, 30)):   # 04:30 UTC del 10: en Panamá sigue siendo el 9
            self.pasar()
            self.pasar()
            self.assertEqual(sum(self.recibidas().values()), 2)
        with freeze_time(panama(2026, 10, 10, 0, 30)):   # ya es otro día en Panamá
            self.assertEqual(sum(self.recibidas().values()), 0)
            self.pasar()
            self.assertEqual(sum(self.recibidas().values()), 1)

    def test_un_dia_nuevo_empieza_de_cero(self):
        self.beto.dcasa_disponible = False
        for _n in range(4):
            self.pasar()    # entre Ana y Carla
        self.beto.dcasa_disponible = True
        with freeze_time(panama(2026, 10, 10, 9, 0)):
            self.assertEqual(sorted(self.recibidas().values()), [0, 0, 0])
            self.assertEqual(self.pasar().asignada_a, self.beto, 'A Beto nadie lo espera y no ha recibido nada')

    def test_en_manual_no_se_asigna_a_nadie_ni_se_anota(self):
        self.ajustes.reparto_modo = 'manual'
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.assertFalse(self.Reparto.search([('conversacion_id', '=', conv.id)]))
        self.assertNotIn('Nadie estaba disponible', self.avisos(conv))

    def test_el_reparto_por_turnos_de_siempre_sigue_igual_pero_respeta_a_quien_esta_fuera(self):
        self.ajustes.reparto_modo = 'turnos'
        self.vendedora.dcasa_turno = 30
        self.beto.dcasa_turno = 10
        self.carla.dcasa_turno = 20
        self.beto.dcasa_fuera_del_reparto = True
        orden = [self.pasar().asignada_a for _n in range(3)]
        self.assertEqual(orden, [self.carla, self.vendedora, self.carla])
        self.assertEqual(self.Reparto.search_count([('regla', '=', 'turno')]), 3, 'También queda en el libro')

    def test_el_juan_tecnico_no_entra_al_reparto(self):
        for _n in range(8):
            self.assertNotEqual(self.pasar().asignada_a, self.juan)


@tagged('post_install', '-at_install')
class TestAjustesDelReparto(JuanCase):

    def test_de_fabrica_el_reparto_arranca_apagado_y_con_14_dias_de_memoria(self):
        por_defecto = self.env['dcasa.juan.ajustes'].default_get(['reparto_modo', 'reparto_dias_misma_vendedora'])
        self.assertEqual(por_defecto, {'reparto_modo': 'manual', 'reparto_dias_misma_vendedora': 14})

    def test_los_dias_de_memoria_van_de_0_a_365(self):
        for malo in (-1, 366):
            with self.assertRaises(ValidationError):
                self.ajustes.reparto_dias_misma_vendedora = malo
        for bueno in (0, 14, 365):
            self.ajustes.reparto_dias_misma_vendedora = bueno

    def test_el_modo_parejo_es_una_opcion_mas(self):
        opciones = dict(self.env['dcasa.juan.ajustes']._fields['reparto_modo'].selection)
        self.assertEqual(list(opciones), ['manual', 'parejo', 'turnos'])
        self.ajustes.reparto_modo = 'parejo'
        self.assertEqual(self.ajustes.reparto_modo, 'parejo')


@tagged('post_install', '-at_install')
class TestSoloLasVendedorasRecibenReparto(RepartoCase):
    """Gerencia y los administradores intervienen en cualquier conversación, pero el reparto no se las pasa."""

    def test_gerencia_y_administrador_nunca_reciben_aunque_esten_disponibles(self):
        self.assertTrue(self.gerente.dcasa_disponible and self.administrador.dcasa_disponible)
        asignadas = [self.pasar().asignada_a for _n in range(12)]
        self.assertFalse({self.gerente, self.administrador} & set(asignadas))
        self.assertEqual(sorted(self.recibidas().values()), [4, 4, 4])
        self.assertEqual(self.Reparto._disponibles(), self.equipo)

    def test_lo_mismo_con_el_reparto_por_turnos(self):
        self.ajustes.reparto_modo = 'turnos'
        asignadas = [self.pasar().asignada_a for _n in range(9)]
        self.assertFalse({self.gerente, self.administrador} & set(asignadas))
        self.assertEqual(sorted(self.recibidas().values()), [3, 3, 3])

    def test_el_reparto_no_cambia_quien_ve_ni_a_quien_se_le_avisa(self):
        panel = self.Conversacion._usuarios_del_panel()
        self.assertIn(self.gerente, panel)
        self.assertIn(self.administrador, panel)
        self.assertIn(self.gerente.id, [u['id'] for u in self.Conversacion.with_user(self.vendedora).equipo()],
                      'Se les puede asignar a mano y mencionar')
        self.assertEqual(self.Reparto._no_reciben(), self.gerente | self.administrador)

    def test_si_solo_hay_gerencia_y_administrador_queda_como_hoy(self):
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.Enlace.create({'user_id': self.gerente.id, 'chat_id': '5550777'})
        self.equipo.write({'dcasa_disponible': False})
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.assertEqual(conv.activity_ids.user_id, self.ajustes.responsable_id)
        destinos = [c.args[0] for c in self.enviar.call_args_list]
        self.assertEqual(destinos, ['5550777'], 'El aviso sí le llega a Gerencia')
        self.assertIn('Nadie estaba disponible', self.avisos(conv))

    def test_borde_una_vendedora_que_ademas_es_gerente_deja_de_recibir(self):
        manager = self.env.ref('sales_team.group_sale_manager')
        self.carla.write({'group_ids': [(4, manager.id)]})
        self.assertNotIn(self.carla, self.Reparto._vendedoras())
        self.assertIn(self.carla, self.Reparto._no_reciben(), 'Gerencia lo ve en la pantalla, en «No reciben»')
        asignadas = [self.pasar().asignada_a for _n in range(6)]
        self.assertNotIn(self.carla, asignadas)
        self.assertEqual(self.carla.dcasa_disponible, True)
        # Quitándole el rol de Gerencia vuelve a recibir.
        self.carla.write({'group_ids': [(3, manager.id)]})
        self.assertIn(self.carla, self.Reparto._vendedoras())
        self.assertEqual(self.pasar().asignada_a, self.carla, 'Es quien menos lleva')

    def test_gerencia_conserva_lo_que_ve_y_puede_tomar_y_escribir(self):
        conv = self.pasar()
        panel = self.Conversacion.with_user(self.gerente)
        self.assertIn(conv.id, [c['id'] for c in panel.lista()['conversaciones']])
        otra = self.cliente()
        panel.tomar(otra.id)
        self.assertEqual((otra.estado, otra.asignada_a), ('humano', self.gerente))
        otra.with_user(self.gerente)._crear_mensaje_de_odoo('Yo te ayudo', usuario=self.gerente)
        self.assertEqual(otra.asignada_a, self.gerente)

    def test_si_la_tenia_gerencia_y_la_devolvio_al_asistente_el_reparto_la_pasa_a_una_vendedora(self):
        for modo in ('parejo', 'turnos'):
            with self.subTest(modo=modo):
                self.ajustes.reparto_modo = modo
                conv = self.cliente()
                conv.sudo().asignada_a = self.gerente
                conv._pasar_a_vendedora('Duda')
                self.assertIn(conv.asignada_a, self.equipo)

    def test_una_conversacion_asignada_a_una_vendedora_que_recibe_se_queda_con_ella_en_turnos(self):
        self.ajustes.reparto_modo = 'turnos'
        conv = self.cliente()
        conv.sudo().asignada_a = self.vendedora
        conv._pasar_a_vendedora('Duda')
        self.assertEqual(conv.asignada_a, self.vendedora)


@tagged('post_install', '-at_install')
class TestReinicioDeLaManana(RepartoCase):
    """«No disponible» (almuerzo, fin del día) se reinicia solo cada mañana, antes de abrir la tienda."""

    AHORA = panama(2026, 10, 9, 10, 0)    # ya pasó el corte de hoy (6:00 a. m. con el horario de 8:00)

    def marcar(self, usuario, desde=None):
        usuario.write({'dcasa_disponible': False, 'dcasa_no_disponible_desde': desde or False})

    def reiniciar(self):
        return self.Reparto._cron_reiniciar_disponibilidad()

    def test_deja_disponibles_a_las_que_se_marcaron_antes_del_corte(self):
        self.marcar(self.beto, panama(2026, 10, 8, 17, 30))
        self.marcar(self.carla, panama(2026, 10, 9, 5, 0))
        self.assertEqual(self.reiniciar(), 2)
        self.assertTrue(self.beto.dcasa_disponible and self.carla.dcasa_disponible)
        self.assertFalse(self.beto.dcasa_no_disponible_desde)

    def test_una_marca_vieja_sin_fecha_tambien_se_reinicia(self):
        self.marcar(self.beto)
        self.assertEqual(self.reiniciar(), 1)
        self.assertTrue(self.beto.dcasa_disponible)

    def test_no_borra_lo_que_se_marco_despues_del_corte(self):
        """Si el contenedor durmió y el cron corre tarde, la pausa de hace un rato se respeta."""
        self.marcar(self.beto, panama(2026, 10, 9, 9, 40))
        self.assertEqual(self.reiniciar(), 0)
        self.assertFalse(self.beto.dcasa_disponible)

    def test_antes_del_corte_no_hace_nada(self):
        self.marcar(self.beto, panama(2026, 10, 8, 17, 30))
        with freeze_time(panama(2026, 10, 9, 5, 59)):
            self.assertEqual(self.reiniciar(), 0)
            self.assertFalse(self.beto.dcasa_disponible)
        with freeze_time(panama(2026, 10, 9, 6, 0)):
            self.assertEqual(self.reiniciar(), 1)
            self.assertTrue(self.beto.dcasa_disponible)

    def test_el_corte_sigue_al_horario_de_la_tienda_dos_horas_antes_de_abrir(self):
        self.ajustes.horario_inicio = 10.0     # abre a las 10:00 → corte a las 8:00
        self.marcar(self.beto, panama(2026, 10, 8, 17, 30))
        with freeze_time(panama(2026, 10, 9, 7, 30)):
            self.assertEqual(self.reiniciar(), 0)
        with freeze_time(panama(2026, 10, 9, 8, 0)):
            self.assertEqual(self.reiniciar(), 1)

    def test_si_abren_de_madrugada_el_corte_nunca_es_antes_de_medianoche(self):
        self.ajustes.horario_inicio = 1.0
        self.marcar(self.beto, panama(2026, 10, 8, 23, 0))
        with freeze_time(panama(2026, 10, 9, 0, 5)):
            self.assertEqual(self.reiniciar(), 1)

    def test_no_toca_a_quien_gerencia_saco_del_reparto(self):
        self.carla.write({'dcasa_fuera_del_reparto': True})
        self.marcar(self.carla, panama(2026, 10, 8, 17, 30))
        self.marcar(self.beto, panama(2026, 10, 8, 17, 30))
        self.assertEqual(self.reiniciar(), 1)
        self.assertFalse(self.carla.dcasa_disponible, 'Sigue como estaba mientras esté de vacaciones')
        self.assertTrue(self.carla.dcasa_fuera_del_reparto)
        self.assertEqual(self.carla.dcasa_no_disponible_desde, panama(2026, 10, 8, 17, 30))

    def test_el_dia_que_vuelve_de_vacaciones_tambien_se_reinicia(self):
        self.carla.write({'dcasa_fuera_del_reparto': True, 'dcasa_fuera_hasta': date(2026, 10, 9)})
        self.marcar(self.carla, panama(2026, 10, 1, 17, 30))
        self.assertEqual(self.reiniciar(), 1)
        self.assertTrue(self.carla.dcasa_disponible)

    def test_no_toca_a_gerencia_ni_a_administradores(self):
        for usuario in (self.gerente, self.administrador):
            self.marcar(usuario, panama(2026, 10, 8, 17, 30))
        self.assertEqual(self.reiniciar(), 0)
        self.assertFalse(self.gerente.dcasa_disponible or self.administrador.dcasa_disponible)

    def test_es_idempotente_y_no_toca_a_las_que_ya_estan_disponibles(self):
        self.marcar(self.beto, panama(2026, 10, 8, 17, 30))
        self.assertEqual((self.reiniciar(), self.reiniciar()), (1, 0))
        self.assertTrue(self.vendedora.dcasa_disponible)

    def test_marcarse_no_disponible_anota_cuando_y_volver_a_disponible_lo_borra(self):
        panel = self.Conversacion.with_user(self.vendedora)
        panel.fijar_disponible(False)
        self.assertEqual((self.vendedora.dcasa_disponible, self.vendedora.dcasa_no_disponible_desde),
                         (False, self.AHORA))
        panel.fijar_disponible(True)
        self.assertEqual((self.vendedora.dcasa_disponible, self.vendedora.dcasa_no_disponible_desde), (True, False))

    def test_de_punta_a_punta_se_marca_de_tarde_y_a_la_manana_siguiente_vuelve(self):
        panel = self.Conversacion.with_user(self.beto)
        with freeze_time(panama(2026, 10, 9, 17, 5)):
            panel.fijar_disponible(False)
            self.assertNotIn(self.beto, [self.pasar().asignada_a for _n in range(4)])
        with freeze_time(panama(2026, 10, 10, 6, 30)):
            self.assertEqual(self.reiniciar(), 1)
            self.assertIn(self.beto, [self.pasar().asignada_a for _n in range(3)])
        with freeze_time(panama(2026, 10, 10, 12, 0)):
            panel.fijar_disponible(False)       # el almuerzo de hoy
        with freeze_time(panama(2026, 10, 10, 13, 0)):
            self.assertEqual(self.reiniciar(), 0, 'Lo de hoy se respeta hasta mañana')

    def test_el_cron_existe_corre_cada_hora_y_llama_a_lo_correcto(self):
        cron = self.env.ref('dcasa_conversaciones.ir_cron_reiniciar_disponibilidad')
        self.assertTrue(cron.active)
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'hours'))
        self.assertEqual(cron.model_id.model, 'dcasa.reparto')
        self.assertEqual(cron.code.strip(), 'model._cron_reiniciar_disponibilidad()')
        self.marcar(self.beto, panama(2026, 10, 8, 17, 30))
        cron.ir_actions_server_id.sudo().run()     # lo mismo que corre el planificador, en esta transacción
        self.assertTrue(self.beto.dcasa_disponible, 'El cron de verdad hace el reinicio')
