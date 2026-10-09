"""Horario laboral y fechas de seguimiento: funciones puras, en hora de Panamá y sin errores de zona horaria."""
from datetime import datetime, time, timedelta

from odoo.tests import BaseCase, tagged

from ..models import horario as H

REGLA = H.ReglaSeguimiento()   # 5 h, 5 días, solo horario laboral, máximo 2 (decisión de la dueña)
TODOS = H.Horario()            # 8:00 a 17:00, todos los días, America/Panama


def panama(anio, mes, dia, hora=0, minuto=0):
    """Una hora de Panamá (UTC−5) como UTC ingenuo, que es como guarda Odoo las fechas."""
    return datetime(anio, mes, dia, hora, minuto) + timedelta(hours=5)


@tagged('post_install', '-at_install')
class TestHorarioLaboral(BaseCase):

    def test_por_defecto_es_de_8_a_17_todos_los_dias(self):
        self.assertEqual(TODOS.inicio, time(8, 0))
        self.assertEqual(TODOS.fin, time(17, 0))
        self.assertEqual(TODOS.dias, frozenset(range(7)))
        self.assertEqual(TODOS.zona, 'America/Panama')

    def test_dentro_y_fuera_se_miden_en_hora_de_panama_no_en_utc(self):
        # 7:59 a. m. en Panamá = 12:59 UTC: todavía fuera.
        self.assertFalse(H.dentro_de_horario(panama(2026, 10, 9, 7, 59), TODOS))
        self.assertTrue(H.dentro_de_horario(panama(2026, 10, 9, 8, 0), TODOS))
        self.assertTrue(H.dentro_de_horario(panama(2026, 10, 9, 16, 59), TODOS))
        # Las 17:00 ya son fuera (el fin no cuenta).
        self.assertFalse(H.dentro_de_horario(panama(2026, 10, 9, 17, 0), TODOS))
        # 21:30 UTC es 4:30 p. m. en Panamá: dentro, aunque en UTC sea de noche.
        self.assertTrue(H.dentro_de_horario(datetime(2026, 10, 9, 21, 30), TODOS))

    def test_medianoche_utc_no_cambia_el_dia_de_panama(self):
        # 2026-10-10 03:00 UTC es todavía viernes 9 a las 10 p. m. en Panamá.
        local = H.a_local(datetime(2026, 10, 10, 3, 0), TODOS)
        self.assertEqual((local.day, local.hour), (9, 22))
        self.assertEqual(H.dia_js(local), 5)   # viernes
        self.assertEqual(H.a_utc(local), datetime(2026, 10, 10, 3, 0))

    def test_siguiente_horario_laboral(self):
        dentro = panama(2026, 10, 9, 10, 15)
        self.assertEqual(H.siguiente_horario_laboral(dentro, TODOS), dentro)
        # Viernes a las 10 p. m. → sábado a las 8:00 a. m. (todos los días atienden).
        self.assertEqual(H.siguiente_horario_laboral(panama(2026, 10, 9, 22), TODOS), panama(2026, 10, 10, 8))
        # Madrugada: el mismo día a las 8:00.
        self.assertEqual(H.siguiente_horario_laboral(panama(2026, 10, 9, 3), TODOS), panama(2026, 10, 9, 8))
        # A las 17:00 en punto ya cerró.
        self.assertEqual(H.siguiente_horario_laboral(panama(2026, 10, 9, 17), TODOS), panama(2026, 10, 10, 8))

    def test_con_dias_cerrados_salta_al_siguiente_dia_abierto(self):
        lunes_a_viernes = H.Horario(dias=frozenset({1, 2, 3, 4, 5}))
        # Viernes 9 de octubre de 2026 a las 6 p. m. → lunes 12 a las 8:00.
        self.assertEqual(H.siguiente_horario_laboral(panama(2026, 10, 9, 18), lunes_a_viernes), panama(2026, 10, 12, 8))
        # Sábado a mediodía → lunes.
        self.assertEqual(H.siguiente_horario_laboral(panama(2026, 10, 10, 12), lunes_a_viernes), panama(2026, 10, 12, 8))
        self.assertFalse(H.dentro_de_horario(panama(2026, 10, 11, 12), lunes_a_viernes))   # domingo

    def test_sin_dias_no_hay_horario(self):
        self.assertIsNone(H.siguiente_horario_laboral(panama(2026, 10, 9, 10), H.Horario(dias=frozenset())))

    def test_horario_invalido(self):
        with self.assertRaises(ValueError):
            H.Horario(inicio=time(17, 0), fin=time(8, 0))
        with self.assertRaises(ValueError):
            H.Horario(dias=frozenset({7}))

    def test_horas_de_odoo_a_texto(self):
        self.assertEqual(H.float_a_hora(8.0), time(8, 0))
        self.assertEqual(H.float_a_hora(17.5), time(17, 30))
        self.assertEqual(H.hora_a_float(time(17, 30)), 17.5)
        self.assertEqual(H.texto_hora(time(8, 5)), '08:05')
        self.assertEqual(H.texto_hora_amable(time(8, 0)), '8:00 a. m.')
        self.assertEqual(H.texto_hora_amable(time(17, 0)), '5:00 p. m.')
        self.assertEqual(H.texto_hora_amable(time(12, 0)), '12:00 p. m.')
        with self.assertRaises(ValueError):
            H.float_a_hora(24.0)

    def test_fechas_iso_del_contrato(self):
        self.assertEqual(H.de_iso('2026-10-09T14:03:00Z'), datetime(2026, 10, 9, 14, 3))
        self.assertEqual(H.de_iso('2026-10-09T09:03:00-05:00'), datetime(2026, 10, 9, 14, 3))
        self.assertEqual(H.de_iso('2026-10-09T14:03:00'), datetime(2026, 10, 9, 14, 3))
        self.assertEqual(H.a_iso(datetime(2026, 10, 9, 14, 3)), '2026-10-09T14:03:00Z')
        self.assertIsNone(H.a_iso(None))
        for malo in ('ayer', '', None, 5, '2026-13-45T00:00:00Z'):
            with self.assertRaises(ValueError):
                H.de_iso(malo)

    def test_json_del_horario_para_el_worker(self):
        self.assertEqual(TODOS.como_json(), {
            'inicio': '08:00', 'fin': '17:00', 'dias': [0, 1, 2, 3, 4, 5, 6], 'zona': 'America/Panama'})

    def test_fecha_en_texto(self):
        self.assertEqual(H.texto_fecha_hora(datetime(2026, 10, 9, 14, 3), TODOS), 'viernes 9 de octubre de 2026, 9:03 a. m.')


@tagged('post_install', '-at_install')
class TestFechasDeSeguimiento(BaseCase):
    """Decisión de la dueña: 1.º a las 5 h del último mensaje, solo en horario laboral; 2.º a los 5 días; máximo 2."""

    def proximo(self, enviados, ultimo_mensaje, ultimo_seguimiento=None, regla=REGLA, horario=TODOS):
        return H.proximo_seguimiento(enviados, ultimo_mensaje, ultimo_seguimiento, regla, horario)

    def test_el_primero_es_a_las_5_horas_si_cae_en_horario(self):
        # Mensaje a las 9:00 a. m. → seguimiento a las 2:00 p. m., dentro del horario.
        self.assertEqual(self.proximo(0, panama(2026, 10, 9, 9)), panama(2026, 10, 9, 14))
        # Justo al límite: a las 12:00 + 5 h = 5:00 p. m. ya está fuera → mañana a las 8:00.
        self.assertEqual(self.proximo(0, panama(2026, 10, 9, 12)), panama(2026, 10, 10, 8))
        # A las 11:59 + 5 h = 4:59 p. m.: todavía dentro.
        self.assertEqual(self.proximo(0, panama(2026, 10, 9, 11, 59)), panama(2026, 10, 9, 16, 59))

    def test_si_cae_fuera_de_horario_espera_al_siguiente(self):
        # Mensaje a las 3:00 p. m. → +5 h = 8:00 p. m. → mañana a las 8:00 a. m.
        self.assertEqual(self.proximo(0, panama(2026, 10, 9, 15)), panama(2026, 10, 10, 8))
        # Mensaje de madrugada a las 12:30 a. m. → +5 h = 5:30 a. m. → ese mismo día a las 8:00.
        self.assertEqual(self.proximo(0, panama(2026, 10, 9, 0, 30)), panama(2026, 10, 9, 8))

    def test_el_segundo_es_a_los_5_dias_del_primero(self):
        primero = panama(2026, 10, 10, 8)
        self.assertEqual(self.proximo(1, panama(2026, 10, 9, 15), primero), panama(2026, 10, 15, 8))
        # Si los 5 días caen fuera de horario, espera al siguiente horario laboral.
        primero = panama(2026, 10, 10, 16, 30)
        self.assertEqual(self.proximo(1, panama(2026, 10, 9, 15), primero), panama(2026, 10, 15, 16, 30))
        self.assertEqual(self.proximo(1, None, panama(2026, 10, 10, 8, 0)), panama(2026, 10, 15, 8))

    def test_maximo_dos_seguimientos(self):
        self.assertIsNone(self.proximo(2, panama(2026, 10, 9, 9), panama(2026, 10, 14, 9)))
        self.assertIsNone(self.proximo(3, panama(2026, 10, 9, 9)))
        solo_uno = H.ReglaSeguimiento(maximo=1)
        self.assertIsNone(self.proximo(1, panama(2026, 10, 9, 9), panama(2026, 10, 9, 14), regla=solo_uno))
        self.assertIsNone(self.proximo(0, panama(2026, 10, 9, 9), regla=H.ReglaSeguimiento(maximo=0)))

    def test_sin_mensaje_no_hay_seguimiento(self):
        self.assertIsNone(self.proximo(0, None))

    def test_sin_restriccion_de_horario_es_exacto(self):
        libre = H.ReglaSeguimiento(solo_horario_laboral=False)
        self.assertEqual(self.proximo(0, panama(2026, 10, 9, 22), regla=libre), panama(2026, 10, 10, 3))

    def test_horario_con_dias_cerrados(self):
        lunes_a_viernes = H.Horario(dias=frozenset({1, 2, 3, 4, 5}))
        # Viernes a las 3 p. m. + 5 h = 8 p. m. → el lunes a las 8:00.
        self.assertEqual(self.proximo(0, panama(2026, 10, 9, 15), horario=lunes_a_viernes), panama(2026, 10, 12, 8))

    def test_frases_para_el_cliente_segun_el_horario(self):
        self.assertEqual(H.cuando_atienden(panama(2026, 10, 9, 10), TODOS), 'ahora')
        self.assertEqual(H.cuando_atienden(panama(2026, 10, 9, 22), TODOS), 'mañana a primera hora, desde las 8:00 a. m.')
        self.assertEqual(H.cuando_atienden(panama(2026, 10, 9, 5), TODOS), 'hoy desde las 8:00 a. m.')
        cerrado_el_fin_de_semana = H.Horario(dias=frozenset({1, 2, 3, 4, 5}))
        self.assertEqual(H.cuando_atienden(panama(2026, 10, 9, 18), cerrado_el_fin_de_semana),
                         'el lunes desde las 8:00 a. m.')


@tagged('post_install', '-at_install')
class TestPideNoContactar(BaseCase):

    def test_pedidos_claros(self):
        for texto in ('No me escribas más', 'por favor no me contacten', 'Ya no me molestes', 'deja de escribirme',
                      'no quiero que me escriban', 'NO ME VUELVAS A ESCRIBIR', 'no me llames ni me escribas',
                      'Borra mi número'):
            with self.subTest(texto=texto):
                self.assertTrue(H.pide_no_contactar(texto))

    def test_conversacion_normal_no_lo_activa(self):
        for texto in ('Hola, ¿tienen camas queen?', 'Escríbeme mañana por la tarde', 'me interesa el colchón',
                      '¿Me puedes escribir el precio?', '', None):
            with self.subTest(texto=texto):
                self.assertFalse(H.pide_no_contactar(texto))
