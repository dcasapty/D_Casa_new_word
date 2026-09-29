"""Las reglas puras, portadas de pruebas/*.test.ts de DCasa-Referidos."""
from datetime import datetime

from odoo.tests import BaseCase, tagged

from ..models import reglas as R


@tagged('post_install', '-at_install')
class TestPuntos(BaseCase):

    def setUp(self):
        super().setUp()
        self.reglas = R.cargar_reglas()

    def con(self, **acumulacion):
        return {**self.reglas, 'acumulacion': {**self.reglas['acumulacion'], **acumulacion}}

    def test_sin_puntos_por_dolar_lanza_en_vez_de_devolver_cero(self):
        with self.assertRaises(R.FaltaConfigurar):
            R.puntos_de_compra(10000, self.con(puntosPorDolar=None))

    def test_sin_base_decidida_no_acredita(self):
        with self.assertRaises(R.FaltaConfigurar):
            R.puntos_de_compra(10000, self.con(baseDeCalculo='PENDIENTE'))

    def test_con_la_economia_puesta_no_falta_nada(self):
        self.assertEqual(R.falta_para_acreditar(self.reglas), [])
        self.assertEqual(R.falta_para_referir(self.reglas), [])

    def test_base_total_y_subtotal(self):
        self.assertEqual(R.base_de_compra(10700, self.reglas), 10700)
        self.assertEqual(R.base_de_compra(10700, self.con(baseDeCalculo='subtotal')), 10000)

    def test_monto_invalido(self):
        for monto in (0, -100, 10.5):
            with self.assertRaises(ValueError):
                R.base_de_compra(monto, self.reglas)

    def test_redondea_hacia_abajo(self):
        self.assertEqual(R.puntos_de_compra(35309, self.reglas), 353)  # factura real INV/2026/00821
        self.assertEqual(R.puntos_de_compra(10799, self.reglas), 107)

    def test_importes_grandes_sin_coma_flotante(self):
        self.assertEqual(R.puntos_de_compra(4_999_999, self.reglas), 49_999)

    def test_tasa_fraccionaria_redondea_hacia_abajo(self):
        self.assertEqual(R.puntos_de_compra(10099, self.con(puntosPorDolar=1.5)), 151)

    def test_compra_minima(self):
        self.assertEqual(R.puntos_de_compra(1999, self.reglas), 0)
        self.assertEqual(R.puntos_de_compra(2000, self.reglas), 20)

    def test_tope_por_compra(self):
        self.assertEqual(R.puntos_de_compra(10_000_000, self.con(puntosMaximosPorCompra=50000)), 50000)

    def test_saldo_y_reverso(self):
        self.assertEqual(R.saldo([100, 250, -50]), 300)
        self.assertEqual(R.saldo([100, 250, -250]), 100)
        self.assertEqual(R.faltan_para(700, 500), 0)
        self.assertEqual(R.faltan_para(300, 500), 200)

    def test_formatos(self):
        self.assertEqual(R.como_dolares(107000), '$1,070.00')
        self.assertEqual(R.como_dolares(-5), '-$0.05')
        self.assertEqual(R.como_puntos(1250), '1,250')
        self.assertEqual(R.a_centavos(353.09), 35309)
        self.assertEqual(R.a_centavos(0.1 + 0.2), 30)

    def test_reglas_de_dcasa(self):
        """Las cifras aprobadas el 2026-09-22 (datos/puntos.json de Abrinay)."""
        a, ref = self.reglas['acumulacion'], self.reglas['referido']
        self.assertEqual(a['puntosPorDolar'], 1)
        self.assertEqual(a['baseDeCalculo'], 'total')
        self.assertEqual(a['compraMinimaCentavos'], 2000)
        self.assertEqual((ref['puntosAlPadrino'], ref['puntosAlAhijado']), (500, 250))
        self.assertEqual(ref['topeDePuntosPorPadrinoAlMes'] // ref['puntosAlPadrino'], 10)
        self.assertEqual(self.reglas['bienvenida']['puntos'], 0)
        self.assertEqual(self.reglas['canje']['vigenciaDelCodigoHoras'], 72)


@tagged('post_install', '-at_install')
class TestPersonas(BaseCase):

    def test_alfabeto_sin_parejas_confusas(self):
        for confusa in '01ILO':
            self.assertNotIn(confusa, R.ALFABETO_CODIGO)

    def test_codigo_prefijo_y_largo(self):
        codigo = R.nuevo_codigo_socio()
        self.assertTrue(R.es_codigo_valido(codigo))
        self.assertEqual(len(codigo), 9)
        self.assertNotEqual(R.nuevo_codigo_socio(), R.nuevo_codigo_socio())

    def test_codigo_se_lee_como_lo_escribe_una_persona(self):
        self.assertEqual(R.codigo_normal(' dca-7k3 m9q '), 'DCA7K3M9Q')
        self.assertFalse(R.es_codigo_valido('DCA7K3M90'))  # tiene un cero
        self.assertFalse(R.es_codigo_valido('XYZ7K3M9Q'))

    def test_pin(self):
        self.assertIsNone(R.problema_del_pin('482915'))
        self.assertEqual(R.problema_del_pin('12345'), 'largo')
        self.assertEqual(R.problema_del_pin('12a456'), 'no-son-digitos')
        self.assertEqual(R.problema_del_pin('777777'), 'repetidos')
        self.assertEqual(R.problema_del_pin('123456'), 'secuencia')
        self.assertEqual(R.problema_del_pin('654321'), 'secuencia')
        self.assertEqual(R.problema_del_pin('026191', '60261919'), 'es-el-telefono')

    def test_celular_panameno(self):
        self.assertEqual(R.celular_normal('+507 6026-1919'), '60261919')
        self.assertTrue(R.celular_valido('60261919'))
        self.assertFalse(R.celular_valido('10261919'))
        self.assertFalse(R.celular_valido('6026191'))

    def test_de_un_tercero_solo_nombre_e_inicial(self):
        self.assertEqual(R.nombre_publico('Ana', 'pérez'), 'Ana P.')
        self.assertEqual(R.nombre_publico('Ana'), 'Ana')

    def test_cumple(self):
        self.assertTrue(R.cumple_valido(''))
        self.assertTrue(R.cumple_valido('02-29'))
        self.assertFalse(R.cumple_valido('02-30'))
        self.assertFalse(R.cumple_valido('2026-02-10'))

    def test_factura_normal(self):
        self.assertEqual(R.factura_normal('F-001234'), R.factura_normal('f 001234'))
        self.assertEqual(R.factura_normal('F000123'), 'F123')
        self.assertEqual(R.factura_normal('F1000'), 'F1000')
        self.assertNotEqual(R.factura_normal('F-1234'), R.factura_normal('F-1235'))

    def test_candado_en_dos_escalones(self):
        ahora = datetime(2026, 9, 29, 12, 0)
        self.assertIsNone(R.bloqueo_tras(4, ahora))
        self.assertEqual((R.bloqueo_tras(5, ahora) - ahora).total_seconds(), 15 * 60)
        self.assertEqual((R.bloqueo_tras(10, ahora) - ahora).total_seconds(), 24 * 3600)
        self.assertEqual(R.cuanto_queda(R.bloqueo_tras(5, ahora), ahora), '15 minutos')
        self.assertEqual(R.cuanto_queda(R.bloqueo_tras(10, ahora), ahora), '24 horas')
