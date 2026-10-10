"""Las reglas FIJAS del CRM que se ajusta solo (``models/crm_reglas.py``): puras, sin base de datos."""
from odoo.tests import BaseCase, tagged

from ..models import crm_reglas as R

H = R.Hechos


@tagged('post_install', '-at_install')
class TestTemperatura(BaseCase):

    def test_sin_senales_es_fria(self):
        nivel, motivo = R.temperatura(H())
        self.assertEqual((nivel, motivo), (R.FRIO, 'sin señales de compra todavía'))

    def test_solo_la_cotizacion_es_tibia(self):
        self.assertEqual(R.temperatura(H(cotizacion=True))[0], R.TIBIO)

    def test_cotizacion_y_para_cuando_es_caliente_y_dice_por_que(self):
        nivel, motivo = R.temperatura(H(cotizacion=True, cuando=True))
        self.assertEqual(nivel, R.CALIENTE)
        self.assertEqual(motivo, 'pidió cotización, dijo para cuándo lo quiere')

    def test_los_umbrales_son_exactos(self):
        # 4 puntos = tibio, 5 = caliente (cotización 3 + zona 1 + escribió hace poco 1 = 5).
        self.assertEqual(R.temperatura(H(cotizacion=True, zona=True))[0], R.TIBIO)
        self.assertEqual(R.temperatura(H(cotizacion=True, zona=True, horas_sin_escribir=1))[0], R.CALIENTE)
        # 2 puntos = frío, 3 = tibio.
        self.assertEqual(R.temperatura(H(cuando=True))[0], R.FRIO)
        self.assertEqual(R.temperatura(H(cuando=True, zona=True))[0], R.TIBIO)

    def test_escribir_hace_poco_y_seguido_suman(self):
        self.assertEqual(R.hechos_que_suman(H(horas_sin_escribir=47)), ['reciente'])
        self.assertEqual(R.hechos_que_suman(H(horas_sin_escribir=49)), [])
        self.assertEqual(R.hechos_que_suman(H(mensajes_semana=3)), [])
        self.assertEqual(R.hechos_que_suman(H(mensajes_semana=4)), ['constante'])
        self.assertEqual(R.hechos_que_suman(H(atiende_persona=True)), ['persona'])

    def test_se_enfria_con_el_tiempo(self):
        caliente = dict(cotizacion=True, cuando=True)
        self.assertEqual(R.temperatura(H(**caliente, horas_sin_escribir=24 * 6))[0], R.CALIENTE)
        nivel, motivo = R.temperatura(H(**caliente, horas_sin_escribir=24 * 8))
        self.assertEqual(nivel, R.TIBIO, 'más de 7 días sin escribir: como mucho tibia')
        self.assertIn('no escribe hace 8 días', motivo)
        self.assertEqual(R.temperatura(H(**caliente, horas_sin_escribir=24 * 15))[0], R.FRIO)

    def test_una_tibia_no_sube_por_enfriarse_y_nunca_escribio_no_se_enfria(self):
        self.assertEqual(R.temperatura(H(cotizacion=True, horas_sin_escribir=24 * 10))[0], R.TIBIO)
        self.assertEqual(R.temperatura(H(cotizacion=True, cuando=True, horas_sin_escribir=None))[0], R.CALIENTE)

    def test_los_niveles_se_ordenan_como_texto(self):
        """Odoo ordena una selección por su valor: «Mayor temperatura primero» es un simple orden descendente."""
        self.assertEqual(sorted([R.CALIENTE, R.FRIO, R.TIBIO]), [R.FRIO, R.TIBIO, R.CALIENTE])
        self.assertEqual(set(R.NOMBRE_TEMPERATURA), {R.FRIO, R.TIBIO, R.CALIENTE})


@tagged('post_install', '-at_install')
class TestDatosDelCliente(BaseCase):

    def test_una_linea_de_texto_plano_con_tope(self):
        self.assertEqual(R.limpiar_dato('  La   Chorrera\n centro  '), 'La Chorrera centro')
        self.assertEqual(len(R.limpiar_dato('x' * 500)), R.MAX_TEXTO_DATO)

    def test_lo_que_no_sirve_queda_vacio(self):
        for basura in (None, '', '   ', '---', '¿?', 0):
            self.assertEqual(R.limpiar_dato(basura), '', repr(basura))

    def test_el_html_se_deja_como_texto(self):
        """Se escapa al mostrarlo (Char): aquí solo se asegura que sea una línea y de tamaño fijo."""
        self.assertEqual(R.limpiar_dato('<b>Arraiján</b>'), '<b>Arraiján</b>')


@tagged('post_install', '-at_install')
class TestPerderPorSinRespuesta(BaseCase):

    def test_con_0_dias_nunca(self):
        self.assertFalse(R.toca_perder(400, 0, False))
        self.assertFalse(R.toca_perder(400, None, False))

    def test_pasados_los_dias_se_archiva(self):
        self.assertFalse(R.toca_perder(29, 30, False))
        self.assertTrue(R.toca_perder(30, 30, False))
        self.assertTrue(R.toca_perder(90, 30, False))

    def test_si_una_persona_la_trabaja_no_se_archiva(self):
        self.assertFalse(R.toca_perder(90, 30, True))

    def test_sin_mensajes_no_hay_de_donde_contar(self):
        self.assertFalse(R.toca_perder(None, 30, False))
