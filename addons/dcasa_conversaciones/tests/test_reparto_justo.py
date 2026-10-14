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


@tagged('post_install', '-at_install')
class TestRepartoParejo(JuanCase):

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
        otras = self.Conversacion._usuarios_del_panel() - self.equipo
        otras.write({'dcasa_fuera_del_reparto': True})
        self.Conversacion._usuarios_del_panel().write({'dcasa_turno': 0})
        self.equipo.write({'dcasa_disponible': True})
        self.numero = 0

    # --- Ayudas -----------------------------------------------------------------------------------------------

    def pasar(self, id_externo=None, motivo='Quiere una cotización'):
        """Un cliente (nuevo, salvo que se repita ``id_externo``) pasa a una vendedora. Devuelve la conversación."""
        if id_externo is None:
            self.numero += 1
            id_externo = f'5076200{self.numero:04d}'
        conv = self.conversacion(nombre=f'Cliente {id_externo}', id_externo=id_externo, ts=fields_ahora())
        conv._pasar_a_vendedora(motivo)
        return conv

    def recibidas(self, usuario=None):
        """Cuántas le pasó Juan hoy a cada quien: ``{usuario: n}`` (o solo la de ``usuario``)."""
        hoy = self.Reparto._hoy()
        cuentas = self.Reparto._cuentas(self.equipo, hoy, hoy)
        por_persona = {u: cuentas[u.id]['recibidas'] for u in self.equipo}
        return por_persona[usuario] if usuario else por_persona

    def avisos(self, conv):
        return [m.texto for m in conv.mensaje_ids if m.tipo == 'aviso']

    # --- Lo central: parejo ---------------------------------------------------------------------------------

    def test_treinta_conversaciones_entre_tres_nunca_se_separan_mas_de_una(self):
        for n in range(1, 31):
            self.pasar()
            cuentas = list(self.recibidas().values())
            self.assertLessEqual(max(cuentas) - min(cuentas), 1, f'Después de {n}: {cuentas}')
        self.assertEqual(sorted(self.recibidas().values()), [10, 10, 10])

    def test_con_cuatro_vendedoras_y_treinta_y_una_conversaciones_la_diferencia_es_de_una(self):
        julia = new_test_user(self.env, login='juan_julia_justo', name='Julia Vendedora',
                              groups='base.group_user,sales_team.group_sale_salesman')
        self.equipo |= julia
        for _n in range(31):
            self.pasar()
        cuentas = sorted(self.recibidas().values())
        self.assertEqual(sum(cuentas), 31)
        self.assertLessEqual(cuentas[-1] - cuentas[0], 1, cuentas)

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

    def test_gana_quien_lleva_menos_hoy_aunque_le_toque_otro_por_turno(self):
        self.pasar()
        self.pasar()
        self.pasar()
        # Cada quien tiene 1. Gema recibe una más «a mano» (no cuenta) y Beto una de Juan.
        self.Reparto._anotar(self.pasar(), self.beto, 'parejo')
        cuentas = self.recibidas()
        menos = min(cuentas.values())
        self.assertEqual(self.pasar().asignada_a, next(u for u in self.equipo if cuentas[u] == menos
                                                       and u != self.beto))

    def test_con_empate_gana_quien_tiene_menos_clientes_esperando(self):
        # Las tres tienen 0 hoy. Ana y Gema tienen un cliente esperándoles; Beto, ninguno.
        for dueña, id_externo in ((self.vendedora, '50762111111'), (self.gerente, '50762222222')):
            conv = self.conversacion(nombre=id_externo, id_externo=id_externo, ts=fields_ahora())
            conv.sudo().write({'estado': 'humano', 'asignada_a': dueña.id})
        self.assertEqual(self.recibidas(), {self.vendedora: 0, self.beto: 0, self.gerente: 0})
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn('menos clientes', ' '.join(self.avisos(conv)) + ' a ella le esperan menos clientes')

    def test_con_empate_total_gana_quien_lleva_mas_tiempo_sin_recibir(self):
        self.vendedora.dcasa_turno = 30
        self.beto.dcasa_turno = 10
        self.gerente.dcasa_turno = 20
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn('más tiempo sin recibir', ' '.join(self.avisos(conv)))

    def test_el_aviso_del_hilo_dice_por_que_le_toco(self):
        self.pasar()
        conv = self.pasar()
        texto = ' '.join(self.avisos(conv))
        self.assertIn(f'Le tocó a {conv.asignada_a.name}', texto)
        self.assertIn('menos conversaciones hoy (0)', texto)

    def test_cada_decision_queda_en_el_libro(self):
        conv = self.pasar()
        linea = self.Reparto.search([('conversacion_id', '=', conv.id)])
        self.assertEqual((linea.usuario_id, linea.regla, linea.dia), (conv.asignada_a, 'parejo', date(2026, 10, 9)))
        self.assertIn('Le tocó a', linea.razon)

    def test_la_misma_conversacion_el_mismo_dia_cuenta_una_sola_vez(self):
        conv = self.pasar()
        dueña = conv.asignada_a
        conv._devolver(dueña)
        conv._pasar_a_vendedora('Otra vez')
        self.assertEqual(conv.asignada_a, dueña)
        self.assertEqual(self.recibidas(dueña), 1)
        self.assertEqual(self.Reparto.search_count([('conversacion_id', '=', conv.id)]), 1)

    # --- El cliente que vuelve ---------------------------------------------------------------------------

    def test_el_cliente_que_vuelve_se_queda_con_su_vendedora(self):
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        primera._devolver(dueña)
        # Llegan 5 más: quien tenía a este cliente ya lleva más que las otras.
        for _n in range(5):
            self.pasar()
        antes = self.recibidas()
        primera._pasar_a_vendedora('Volvió a preguntar')
        self.assertEqual(primera.asignada_a, dueña)
        self.assertIn('Sigue con', ' '.join(self.avisos(primera)))
        self.assertEqual(self.recibidas(), antes, 'Era la misma conversación del mismo día: no cuenta otra vez')

    def test_si_el_cliente_vuelve_otro_dia_dentro_de_los_dias_se_queda_con_ella_y_dice_cuanto_hace(self):
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        primera._devolver(dueña)
        with freeze_time(panama(2026, 10, 12, 11, 0)):
            primera._pasar_a_vendedora('Volvió')
            self.assertEqual(primera.asignada_a, dueña)
            self.assertIn('hace 3 días', ' '.join(self.avisos(primera)))
            self.assertEqual(self.recibidas(dueña), 1, 'Otro día, otra conversación recibida')

    def test_el_telegram_de_quien_ya_atendia_al_cliente_dice_que_es_suyo(self):
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        self.Enlace.create({'user_id': dueña.id, 'chat_id': '5550009'})
        primera._devolver(dueña)
        self.enviar.reset_mock()
        primera._pasar_a_vendedora('Volvió')
        (destino, texto), = [c.args for c in self.enviar.call_args_list]
        self.assertEqual(destino, '5550009')
        self.assertIn('cliente tuyo', texto)

    def test_pasados_los_dias_el_cliente_se_reparte_de_nuevo(self):
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        primera._devolver(dueña)
        for _n in range(3):
            self.pasar()
        with freeze_time(self.AHORA + timedelta(days=15)):
            # 15 días después ya nadie lleva nada hoy: gana quien lleva más tiempo sin recibir una (la de siempre
            # no, porque recibió la primera, después de las dos primeras de las otras).
            primera._pasar_a_vendedora('Volvió tarde')
            self.assertNotEqual(primera.asignada_a, dueña)
            self.assertIn(f'Antes la tenía {dueña.name}', ' '.join(self.avisos(primera)))

    def test_con_cero_dias_no_hay_memoria(self):
        self.ajustes.reparto_dias_misma_vendedora = 0
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        primera._devolver(dueña)
        with freeze_time(panama(2026, 10, 9, 15, 0)):
            self.pasar()
            self.pasar()
            primera._pasar_a_vendedora('Volvió')
        self.assertNotIn('Sigue con', ' '.join(self.avisos(primera)))

    def test_si_su_vendedora_no_esta_disponible_le_toca_a_otra_y_se_dice(self):
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        primera._devolver(dueña)
        dueña.dcasa_disponible = False
        primera._pasar_a_vendedora('Volvió')
        self.assertNotEqual(primera.asignada_a, dueña)
        self.assertIn(f'Antes la tenía {dueña.name}', ' '.join(self.avisos(primera)))

    def test_si_su_vendedora_esta_fuera_del_reparto_tambien_se_reparte(self):
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        primera._devolver(dueña)
        dueña.write({'dcasa_fuera_del_reparto': True})
        primera._pasar_a_vendedora('Volvió')
        self.assertNotEqual(primera.asignada_a, dueña)

    def test_el_mismo_cliente_por_otro_canal_tambien_vuelve_con_su_vendedora(self):
        primera = self.pasar('50762999999')
        dueña = primera.asignada_a
        otro = self.conversacion(nombre='Mismo cliente', id_externo='7770001', canal='telegram', ts=fields_ahora())
        otro.sudo().partner_id = primera.partner_id
        otro._pasar_a_vendedora('Misma persona, otro canal')
        self.assertEqual(otro.asignada_a, dueña)

    def test_lo_que_ella_le_escribio_al_cliente_tambien_cuenta_como_haberlo_atendido(self):
        conv = self.conversacion(nombre='Cliente de Beto', id_externo='50762888888', ts=fields_ahora())
        conv._crear_mensaje_de_odoo('Hola, te ayudo con tu cama', usuario=self.beto)
        conv._devolver(self.beto)
        conv.sudo().asignada_a = False   # aunque el campo esté vacío, su mensaje deja huella
        self.pasar()
        conv._pasar_a_vendedora('Volvió')
        self.assertEqual(conv.asignada_a, self.beto)

    def test_una_asignacion_a_mano_tambien_cuenta_y_no_suma_a_las_recibidas(self):
        conv = self.conversacion(nombre='Cliente de Gema', id_externo='50762777777', ts=fields_ahora())
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
        self.assertEqual(conv.activity_ids.user_id, self.ajustes.responsable_id)
        self.assertEqual(sorted(c.args[0] for c in self.enviar.call_args_list), ['5550001', '5550003'])
        self.assertIn('Nadie estaba disponible', self.enviar.call_args_list[0].args[1])
        self.assertTrue(any('Nadie estaba disponible' in a for a in self.avisos(conv)), self.avisos(conv))
        self.assertFalse(self.Reparto.search([('conversacion_id', '=', conv.id)]))

    def test_si_todas_estan_fuera_del_reparto_pasa_lo_mismo(self):
        self.equipo.write({'dcasa_fuera_del_reparto': True})
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.assertEqual(conv.estado, 'humano', 'Igual el asistente calla: una persona la toma cuando pueda')

    def test_en_cuanto_alguien_vuelve_a_estar_disponible_recibe(self):
        self.equipo.write({'dcasa_disponible': False})
        self.assertFalse(self.pasar().asignada_a)
        self.beto.dcasa_disponible = True
        self.assertEqual(self.pasar().asignada_a, self.beto)

    # --- Los días y los otros modos -------------------------------------------------------------------------

    def test_la_cuenta_de_hoy_empieza_de_cero_a_medianoche_de_panama_no_de_utc(self):
        with freeze_time(panama(2026, 10, 9, 23, 30)):   # 04:30 UTC del 10: en Panamá sigue siendo el 9
            self.pasar()
            self.pasar()
            self.assertEqual(sum(self.recibidas().values()), 2)
        with freeze_time(panama(2026, 10, 10, 0, 30)):   # ya es otro día en Panamá
            self.assertEqual(sum(self.recibidas().values()), 0)
            self.pasar()
            self.assertEqual(sum(self.recibidas().values()), 1)

    def test_un_dia_nuevo_empieza_parejo_aunque_ayer_hayan_quedado_desiguales(self):
        self.beto.dcasa_disponible = False
        for _n in range(4):
            self.pasar()    # entre Ana y Gema
        self.beto.dcasa_disponible = True
        with freeze_time(panama(2026, 10, 10, 9, 0)):
            self.assertEqual(sorted(self.recibidas().values()), [0, 0, 0])
            self.assertEqual(self.pasar().asignada_a, self.beto, 'Quien lleva más tiempo sin recibir una')

    def test_en_manual_no_se_asigna_a_nadie_ni_se_anota(self):
        self.ajustes.reparto_modo = 'manual'
        conv = self.pasar()
        self.assertFalse(conv.asignada_a)
        self.assertFalse(self.Reparto.search([('conversacion_id', '=', conv.id)]))
        self.assertFalse(any('Nadie estaba disponible' in a for a in self.avisos(conv)))

    def test_el_reparto_por_turnos_de_siempre_sigue_igual_pero_respeta_a_quien_esta_fuera(self):
        self.ajustes.reparto_modo = 'turnos'
        self.vendedora.dcasa_turno = 30
        self.beto.dcasa_turno = 10
        self.gerente.dcasa_turno = 20
        self.beto.dcasa_fuera_del_reparto = True
        orden = [self.pasar().asignada_a for _n in range(3)]
        self.assertEqual(orden, [self.gerente, self.vendedora, self.gerente])
        # Y también quedó en el libro, para la pantalla «Reparto».
        self.assertEqual(self.Reparto.search_count([('regla', '=', 'turno')]), 3)

    def test_el_juan_tecnico_no_entra_al_reparto(self):
        for _n in range(8):
            self.assertNotEqual(self.pasar().asignada_a, self.juan)

    def test_los_dias_de_memoria_van_de_0_a_365(self):
        for malo in (-1, 366):
            with self.assertRaises(ValidationError):
                self.ajustes.reparto_dias_misma_vendedora = malo
        self.ajustes.reparto_dias_misma_vendedora = 365
        self.assertEqual(self.env['dcasa.juan.ajustes'].create_date and 14, 14)

    def test_de_fabrica_son_14_dias_y_el_reparto_arranca_apagado(self):
        campos = self.env['dcasa.juan.ajustes']._fields
        self.assertEqual(campos['reparto_dias_misma_vendedora'].default(self.ajustes), 14)
        self.assertEqual(campos['reparto_modo'].default(self.ajustes), 'manual')


def fields_ahora():
    """Ahora (congelado por la prueba): para que el mensaje del cliente sea de hoy."""
    from odoo import fields
    return fields.Datetime.now()
