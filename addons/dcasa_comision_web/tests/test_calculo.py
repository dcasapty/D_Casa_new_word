"""Las cuentas puras de la comisión web: la base con cada interruptor, el porcentaje, el reparto y los atajos.

Todas las cifras son de PRUEBA, en centavos."""
from datetime import date

from odoo.tests import TransactionCase, tagged

from ..models import calculo as C
from ..models.liquidacion import rango_del_atajo
from ..models.movimiento import empieza_periodo
from ..models.reglas import EJEMPLO

RECOMENDADO = {'base_itbms': 'sin', 'base_envio': 'sin', 'base_descuentos': 'despues', 'base_devoluciones': 'resta',
               'base_pasarela': 'no_resta'}
# Un mueble de 1,000, un premio de 100, un descuento de línea de 50, envío de 50, ITBMS de 90, devolución de 200 (con
# 18 de ITBMS) y 30 de pasarela.
VENTA = {'productos': 100000, 'descuento_lineas': 5000, 'descuento_negativas': 10000, 'envio': 5000, 'itbms': 9000,
         'devuelto': 20000, 'devuelto_itbms': 1800, 'pasarela': 3000}


def base(**cambios):
    return C.base_de_la_venta(VENTA, {**RECOMENDADO, **cambios})


@tagged('post_install', '-at_install')
class TestCalculo(TransactionCase):

    def test_la_base_recomendada_es_sin_itbms_sin_envio_con_descuentos_y_menos_devoluciones(self):
        self.assertEqual(base(), 100000 - 10000 - 20000)

    def test_cada_interruptor_cambia_la_base_en_lo_que_dice(self):
        self.assertEqual(base(base_itbms='con'), 70000 + 9000 - 1800, 'con ITBMS: suma el suyo, resta el devuelto')
        self.assertEqual(base(base_envio='con'), 70000 + 5000)
        self.assertEqual(base(base_descuentos='antes'), 105000 - 23333,
                         'lista, y lo devuelto también a precio de lista')
        self.assertEqual(base(base_devoluciones='no_resta'), 90000)
        self.assertEqual(base(base_pasarela='resta'), 70000 - 3000)

    def test_todos_los_interruptores_juntos(self):
        self.assertEqual(base(base_itbms='con', base_envio='con', base_descuentos='antes', base_devoluciones='no_resta',
                              base_pasarela='resta'), 100000 + 5000 + 5000 + 10500 - 3000,
                         'el ITBMS del precio de lista: 9,000 × 105,000 / 90,000')

    def test_antes_de_descuentos_devolver_todo_deja_la_base_en_cero_y_la_mitad_en_la_mitad(self):
        venta = {'productos': 90000, 'descuento_lineas': 10000, 'descuento_negativas': 0, 'envio': 0, 'itbms': 0,
                 'devuelto': 90000, 'devuelto_itbms': 0, 'pasarela': 0}
        antes = {**RECOMENDADO, 'base_descuentos': 'antes'}
        self.assertEqual(C.base_de_la_venta(venta, antes), 0, 'se devolvió todo lo cobrado')
        self.assertEqual(C.base_de_la_venta({**venta, 'devuelto': 45000}, antes), 50000,
                         'la mitad: la mitad de la lista')
        con_premio = {**venta, 'descuento_lineas': 0, 'productos': 100000, 'descuento_negativas': 10000,
                      'devuelto': 90000}
        self.assertEqual(C.base_de_la_venta(con_premio, antes), 0)
        self.assertEqual(C.devuelto_en_la_base({**con_premio, 'devuelto': 0}, antes), 0)

    def test_la_base_nunca_es_negativa(self):
        self.assertEqual(C.base_de_la_venta({**VENTA, 'devuelto': 500000}, RECOMENDADO), 0)

    def test_cada_interruptor_tiene_dos_posiciones_y_la_primera_es_la_recomendada(self):
        self.assertEqual({clave: pos[0] for clave, pos in C.OPCIONES.items()}, RECOMENDADO)

    def test_el_porcentaje_redondea_a_centavo_mitad_hacia_arriba(self):
        self.assertEqual(C.porcentaje_de(70000, 10), 7000)
        self.assertEqual(C.porcentaje_de(1, 50), 1, '0.5 centavos sube a 1')
        self.assertEqual(C.porcentaje_de(3, 50), 2, '1.5 centavos sube a 2')
        self.assertEqual(C.porcentaje_de(999, 3.333), 33, '33.29667 baja a 33')
        self.assertEqual(C.porcentaje_de(12345, 0), 0)

    def test_el_reparto_siempre_suma_el_total_exacto(self):
        for total in (0, 1, 2, 3, 7, 100, 9999, 123457):
            for partes in ([('a', 60.0), ('b', 40.0)], [('a', 33.33), ('b', 33.33), ('c', 33.34)],
                           [('a', 50.0), ('b', 25.0), ('c', 25.0)], [('a', 100.0)]):
                with self.subTest(total=total, partes=partes):
                    reparto = C.repartir(total, partes)
                    self.assertEqual(sum(reparto.values()), total)
                    self.assertTrue(all(v >= 0 for v in reparto.values()))

    def test_los_centavos_que_sobran_van_a_las_primeras_personas_siempre_en_el_mismo_orden(self):
        self.assertEqual(C.repartir(100, [('a', 33.33), ('b', 33.33), ('c', 33.34)]), {'a': 34, 'b': 33, 'c': 33})
        self.assertEqual(C.repartir(2, [('a', 50.0), ('b', 50.0)]), {'a': 1, 'b': 1})
        self.assertEqual(C.repartir(1, [('a', 50.0), ('b', 50.0)]), {'a': 1, 'b': 0})
        self.assertEqual(C.repartir(5, []), {})

    def test_el_reparto_tiene_que_sumar_cien_a_dos_decimales(self):
        self.assertTrue(C.suma_cien([60, 40]))
        self.assertTrue(C.suma_cien([33.33, 33.33, 33.34]))
        self.assertFalse(C.suma_cien([60, 39.99]))
        self.assertFalse(C.suma_cien([50, 50, 0.01]))
        self.assertFalse(C.suma_cien([]))

    def test_a_centavos_sin_error_de_coma_flotante(self):
        self.assertEqual(C.a_centavos(0.1 + 0.2), 30)
        self.assertEqual(C.a_centavos(19.99), 1999)
        self.assertEqual(C.a_centavos(-12.34), -1234)
        self.assertEqual(C.a_centavos(None), 0)

    def test_el_ejemplo_de_la_pantalla_es_de_mentira_y_da_lo_que_dice(self):
        self.assertEqual(C.base_de_la_venta(EJEMPLO, RECOMENDADO), 100000 - 10000 - 20000)

    # ------------------------------------------------------------------ atajos del periodo

    def test_atajos_de_periodo(self):
        hoy = date(2030, 3, 14)       # jueves
        self.assertEqual(rango_del_atajo('este_mes', hoy), (date(2030, 3, 1), date(2030, 3, 31)))
        self.assertEqual(rango_del_atajo('mes_pasado', hoy), (date(2030, 2, 1), date(2030, 2, 28)))
        self.assertEqual(rango_del_atajo('quincena_1', hoy), (date(2030, 3, 1), date(2030, 3, 15)))
        self.assertEqual(rango_del_atajo('quincena_2_pasada', hoy), (date(2030, 2, 16), date(2030, 2, 28)))
        self.assertEqual(rango_del_atajo('quincena_1_pasada', hoy), (date(2030, 2, 1), date(2030, 2, 15)))
        self.assertEqual(rango_del_atajo('esta_semana', hoy), (date(2030, 3, 11), date(2030, 3, 17)))
        self.assertEqual(rango_del_atajo('semana_pasada', hoy), (date(2030, 3, 4), date(2030, 3, 10)))
        self.assertIsNone(rango_del_atajo('inventado', hoy))

    def test_atajos_en_enero_y_en_ano_bisiesto(self):
        self.assertEqual(rango_del_atajo('mes_pasado', date(2030, 1, 10)), (date(2029, 12, 1), date(2029, 12, 31)))
        self.assertEqual(rango_del_atajo('mes_pasado', date(2032, 3, 1)), (date(2032, 2, 1), date(2032, 2, 29)))

    def test_el_primer_dia_de_cada_periodo_de_la_tarifa(self):
        self.assertTrue(empieza_periodo('mensual', date(2030, 4, 1)))
        self.assertFalse(empieza_periodo('mensual', date(2030, 4, 16)))
        self.assertTrue(empieza_periodo('quincenal', date(2030, 4, 16)))
        self.assertTrue(empieza_periodo('quincenal', date(2030, 4, 1)))
        self.assertFalse(empieza_periodo('quincenal', date(2030, 4, 15)))
        self.assertTrue(empieza_periodo('semanal', date(2030, 3, 4)), 'el 4 de marzo de 2030 es lunes')
        self.assertFalse(empieza_periodo('semanal', date(2030, 3, 5)))
