"""La aritmética de la planilla, sin base de datos: redondeo, ISR por tramos, prorrateo, décimo, vacaciones, prima."""
from datetime import date

from odoo.addons.dcasa_nomina.models import calculo as c
from odoo.tests import BaseCase, tagged

# Tramos de PRUEBA con cifras redondas (las de verdad las valida el contador y viven en la base de datos).
TRAMOS = [(0, 10000, 0), (10000, 50000, 10), (50000, None, 20)]


@tagged('post_install', '-at_install')
class TestCalculo(BaseCase):

    def test_redondeo_mitad_hacia_arriba(self):
        self.assertEqual(c.r2(0.125), 0.13)
        self.assertEqual(c.r2(2.675), 2.68)  # con float puro daría 2.67
        self.assertEqual(c.r2(None), 0.0)
        self.assertEqual(c.porcentaje(1000, 9.75), 97.5)
        self.assertEqual(c.porcentaje(333.33, 1.25), 4.17)

    def test_isr_por_tramos_marginales(self):
        self.assertEqual(c.impuesto_anual(9000, TRAMOS), 0.0)
        self.assertEqual(c.impuesto_anual(10000, TRAMOS), 0.0)
        self.assertEqual(c.impuesto_anual(30000, TRAMOS), 2000.0)  # 20,000 × 10 %
        self.assertEqual(c.impuesto_anual(60000, TRAMOS), 4000.0 + 2000.0)  # 40,000 × 10 % + 10,000 × 20 %
        self.assertEqual(c.impuesto_anual(-5, TRAMOS), 0.0)

    def test_dias_y_salario_del_periodo(self):
        desde, hasta = date(2030, 3, 1), date(2030, 3, 15)
        self.assertEqual(c.dias_del_periodo(desde, hasta), 15)
        self.assertEqual(c.dias_pagados(desde, hasta), 15)
        self.assertEqual(c.dias_pagados(desde, hasta, ingreso=date(2030, 3, 9)), 7)
        self.assertEqual(c.dias_pagados(desde, hasta, salida=date(2030, 3, 5)), 5)
        self.assertEqual(c.dias_pagados(desde, hasta, ingreso=date(2030, 3, 20)), 0)
        self.assertEqual(c.salario_del_periodo(1200, 15, 15), 600.0)
        self.assertEqual(c.salario_del_periodo(1200, 7, 15), 280.0)
        self.assertEqual(c.salario_del_periodo(1200, 0, 0), 0.0)

    def test_isr_de_una_quincena_se_proyecta_al_ano(self):
        # 1,200 al mes → quincena de 600 → 14,400 al año → (14,400 − 10,000) × 10 % = 440 → / 24
        self.assertEqual(c.isr_del_periodo(600, 1.0, 0, TRAMOS), c.r2(440 / 24))
        # medio periodo trabajado, mitad del impuesto de la quincena
        self.assertEqual(c.isr_del_periodo(600, 0.5, 0, TRAMOS), c.r2(440 / 24 / 2))
        # los extras no se proyectan: pagan solo el impuesto adicional que causan (100 × 10 %)
        self.assertEqual(c.isr_del_periodo(600, 1.0, 100, TRAMOS), c.r2(440 / 24 + 10))
        # deducciones del colaborador bajan la renta
        self.assertEqual(c.isr_del_periodo(600, 1.0, 0, TRAMOS, deducciones_anuales=1000), c.r2(340 / 24))
        # si el ISR se calcula después de seguro social y educativo (11 %): 14,400 × 0.89 = 12,816
        self.assertEqual(c.isr_del_periodo(600, 1.0, 0, TRAMOS, descuento_css_se_pct=11.0), c.r2(281.6 / 24))
        # por debajo de la exención no hay retención
        self.assertEqual(c.isr_del_periodo(300, 1.0, 0, TRAMOS), 0.0)

    def test_vacaciones_y_prima(self):
        # un día de descanso por cada 11 días de trabajo: 11 meses de 30 días = 330 días → 30 de descanso
        self.assertEqual(c.vacaciones_ganadas(330, 11), 30.0)
        self.assertEqual(c.vacaciones_ganadas(0, 11), 0.0)
        self.assertEqual(c.vacaciones_ganadas(100, 0), 0.0)
        self.assertEqual(c.valor_de_los_dias(3000, 10), 1000.0)
        self.assertAlmostEqual(c.anios_de_servicio(date(2029, 1, 1), date(2029, 12, 31)), 1.0, places=2)
        self.assertEqual(c.anios_de_servicio(None, date(2030, 1, 1)), 0.0)
        # 2 años × 1 semana (salario 4,333.30 / 4.3333 = 1,000 por semana)
        self.assertEqual(c.prima_de_antiguedad(4333.30, 2.0, 1.0, 4.3333), 2000.0)

    def test_decimo_y_partidas(self):
        self.assertEqual(c.decimo(2400), 200.0)
        self.assertEqual(c.fechas_de_la_partida('1', 2030), (date(2029, 12, 1), date(2030, 3, 31), date(2030, 4, 15)))
        self.assertEqual(c.fechas_de_la_partida('2', 2030), (date(2030, 4, 1), date(2030, 7, 31), date(2030, 8, 15)))
        self.assertEqual(c.fechas_de_la_partida('3', 2030), (date(2030, 8, 1), date(2030, 11, 30), date(2030, 12, 15)))
        # cada día del año cae en una partida
        self.assertEqual(c.partida_de(date(2030, 1, 20))[:3], ('1', date(2029, 12, 1), date(2030, 3, 31)))
        self.assertEqual(c.partida_de(date(2030, 12, 31))[:3], ('1', date(2030, 12, 1), date(2031, 3, 31)))
        self.assertEqual(c.partida_de(date(2030, 6, 1))[0], '2')
        self.assertEqual(c.partida_de(date(2030, 11, 30))[0], '3')

    def test_meses_trabajados(self):
        self.assertEqual(c.meses_trabajados(date(2030, 4, 1), date(2030, 7, 31)), 4.0)
        # entró el 16 de mayo: mitad de mayo (16 de 31 días) + junio + julio
        self.assertAlmostEqual(c.meses_trabajados(date(2030, 4, 1), date(2030, 7, 31), ingreso=date(2030, 5, 16)),
                               16 / 31 + 2, places=3)
