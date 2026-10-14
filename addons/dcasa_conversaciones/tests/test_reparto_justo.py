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
    """Un equipo de tres (Ana, Beto y Gema), el reparto parejo encendido y el reloj quieto un viernes por la mañana."""

    AHORA = panama(2026, 10, 9, 10, 0)    # viernes 9 de octubre, 10:00 a. m. en Panamá

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.beto = new_test_user(cls.env, login='juan_beto_justo', name='Beto Vendedor',
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
        # El equipo de la prueba: Ana (vendedora), Beto y Gema (gerente). Cualquier otra persona de ventas (el
        # administrador de la base de pruebas) queda fuera del reparto para no meterse en las cuentas.
        self.equipo = self.vendedora | self.beto | self.gerente
        (self.Conversacion._usuarios_del_panel() - self.equipo).write({'dcasa_fuera_del_reparto': True})
        self.Conversacion._usuarios_del_panel().write({'dcasa_turno': 0})
        self.equipo.write({'dcasa_disponible': True})
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
        self.dar(self.gerente, 2)
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn(f'Le tocó a {self.beto.name}', self.avisos(conv))
        self.assertIn('Era quien llevaba menos conversaciones hoy (0)', self.avisos(conv))

    def test_quien_no_esta_disponible_se_salta(self):
        self.beto.dcasa_disponible = False
        asignadas = [self.pasar().asignada_a for _n in range(10)]
        self.assertNotIn(self.beto, asignadas)
        self.assertEqual(self.recibidas(self.vendedora), 5)
        self.assertEqual(self.recibidas(self.gerente), 5)

    def test_quien_esta_fuera_del_reparto_no_recibe_aunque_este_disponible_y_conserva_sus_permisos(self):
        self.gerente.write({'dcasa_fuera_del_reparto': True})
        self.assertTrue(self.gerente.dcasa_disponible)
        asignadas = [self.pasar().asignada_a for _n in range(8)]
        self.assertNotIn(self.gerente, asignadas)
        self.assertTrue(self.gerente.has_group('sales_team.group_sale_manager'), 'No le quita ningún permiso')

    def test_la_fecha_de_regreso_la_devuelve_al_reparto_sola(self):
        self.gerente.write({'dcasa_fuera_del_reparto': True, 'dcasa_fuera_hasta': date(2026, 10, 12)})
        self.assertNotIn(self.gerente, [self.pasar().asignada_a for _n in range(6)])
        with freeze_time(panama(2026, 10, 11, 23, 59)):
            self.assertNotIn(self.gerente, self.Reparto._equipo(), 'Todavía no es el día')
        with freeze_time(panama(2026, 10, 12, 0, 1)):
            self.assertIn(self.gerente, self.Reparto._equipo(), 'Ya llegó el día en que vuelve')

    def test_sin_fecha_de_regreso_sigue_fuera_hasta_que_gerencia_la_vuelva_a_meter(self):
        self.gerente.write({'dcasa_fuera_del_reparto': True})
        with freeze_time(panama(2027, 10, 9, 10, 0)):
            self.assertNotIn(self.gerente, self.Reparto._equipo())

    def test_una_persona_que_no_es_de_ventas_nunca_entra(self):
        self.interno.write({'dcasa_disponible': True})
        for _n in range(6):
            self.assertNotIn(self.pasar().asignada_a, self.interno | self.juan)

    # --- Desempates ----------------------------------------------------------------------------------------

    def test_con_empate_gana_quien_tiene_menos_clientes_esperando(self):
        # Las tres tienen 0 hoy. A Ana y a Gema les espera un cliente; a Beto, ninguno.
        self.hacer_esperar(self.vendedora, 1)
        self.hacer_esperar(self.gerente, 1)
        self.assertEqual(sorted(self.recibidas().values()), [0, 0, 0])
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn('a quien menos clientes le esperaban', self.avisos(conv))

    def test_con_empate_total_gana_quien_lleva_mas_tiempo_sin_recibir(self):
        self.vendedora.dcasa_turno = 30
        self.beto.dcasa_turno = 10
        self.gerente.dcasa_turno = 20
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
        self.Conversacion.with_user(self.vendedora).asignar(conv.id, self.gerente.id)
        self.assertEqual(self.recibidas(self.gerente), 0, 'La eligió una persona, no Juan')
        conv.sudo().write({'estado': 'bot', 'asignada_a': False})
        conv._pasar_a_vendedora('Duda')
        self.assertEqual(conv.asignada_a, self.gerente, 'Pero sí es «su» cliente')

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
            self.pasar()    # entre Ana y Gema
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
        self.gerente.dcasa_turno = 20
        self.beto.dcasa_fuera_del_reparto = True
        orden = [self.pasar().asignada_a for _n in range(3)]
        self.assertEqual(orden, [self.gerente, self.vendedora, self.gerente])
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
