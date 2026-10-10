"""Décimo tercer mes, vacaciones, prima y liquidación."""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import NominaCommon


@tagged('post_install', '-at_install')
class TestDecimo(NominaCommon):

    def _confirmar(self, desde, hasta):
        planilla = self._planilla(desde, hasta, entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        return planilla

    def _decimo(self, partida='2', anio=2030, **extra):
        return self.entorno['dcasa.nomina.planilla'].create({
            'tipo': 'decimo', 'anio': anio, 'partida': partida, **extra})

    def test_las_fechas_de_la_partida_salen_solas(self):
        decimo = self._decimo('2')
        self.assertEqual((decimo.fecha_desde, decimo.fecha_hasta, decimo.fecha_pago),
                         (date(2030, 4, 1), date(2030, 7, 31), date(2030, 8, 15)))
        primera = self._decimo('1')
        self.assertEqual((primera.fecha_desde, primera.fecha_pago), (date(2029, 12, 1), date(2030, 4, 15)))
        self.assertEqual(primera.name, 'Décimo tercer mes 2030 · partida 1')

    def test_una_partida_no_se_paga_dos_veces(self):
        self._decimo('2')
        with self.assertRaisesTexto(Exception, 'no se paga dos veces'):
            self._decimo('2')
        self._decimo('3')

    def test_no_se_calcula_sin_confirmar_las_tasas_del_decimo(self):
        self._vigencia('2030-04-01', validar=True, decimo_listo=False)
        decimo = self._decimo('2')
        with self.assertRaisesTexto(UserError, 'tasas del décimo'):
            decimo.action_calcular()

    def test_el_decimo_suma_lo_devengado_de_la_partida_entre_12(self):
        self._confirmar('2030-04-01', '2030-04-15')
        self._confirmar('2030-04-16', '2030-04-30')
        decimo = self._decimo('2')
        decimo.action_calcular()
        ana = self._linea(decimo, self.ana)
        # 1,200 de las dos quincenas confirmadas + 92 días sin planilla estimados a 1,200 / 30 = 40 el día
        self.assertEqual(ana.base_decimo, 4880.0)
        self.assertEqual(ana.salario, 406.67)
        self.assertEqual(ana.css_trabajador, 29.48)   # 7.25 % del décimo
        self.assertEqual(ana.se_trabajador, 0.0)
        self.assertEqual(ana.isr, 0.0)                # el décimo no retiene ISR
        self.assertEqual(ana.neto, 377.19)
        self.assertEqual(ana.css_patronal, 43.72)     # 10.75 %
        self.assertIn('Ana Prueba Nómina', decimo.avisos)  # avisa que parte del periodo se estimó
        # recalcular conserva lo escrito a mano en la base y no duplica
        ana.base_decimo = 5000.0
        self.assertEqual(ana.salario, 416.67)

    def test_el_decimo_completo_con_planillas_de_todo_el_periodo_no_estima_nada(self):
        # Cuatro meses de planillas confirmadas de Ana (abril a julio de 2030)
        for mes, fin in ((4, 30), (5, 31), (6, 30), (7, 31)):
            self._confirmar(f'2030-{mes:02d}-01', f'2030-{mes:02d}-15')
            self._confirmar(f'2030-{mes:02d}-16', f'2030-{mes:02d}-{fin}')
        decimo = self._decimo('2')
        decimo.action_calcular()
        ana = self._linea(decimo, self.ana)
        self.assertEqual(ana.base_decimo, 4800.0)  # 8 quincenas de 600
        self.assertEqual(ana.salario, 400.0)
        self.assertNotIn('Ana Prueba', decimo.avisos or '')

    def test_asiento_del_decimo_sin_provision(self):
        self._confirmar('2030-04-01', '2030-04-15')
        decimo = self._decimo('2')
        decimo.action_calcular()
        decimo.action_confirmar()
        sumas = self._sumas(decimo.move_id)
        total = decimo.total_devengado
        self.assertGreater(total, 0)
        self.assertEqual(sumas[self.c_sueldos][0], total)  # el gasto se reconoce al pagar la partida
        self.assertNotIn(self.c_decimo, sumas)
        self.assertAlmostEqual(sum(decimo.move_id.line_ids.mapped('debit')),
                               sum(decimo.move_id.line_ids.mapped('credit')))
        self.assertEqual(sumas[self.c_por_pagar][1], decimo.total_neto)

    def test_con_provision_cada_quincena_guarda_su_parte_y_la_partida_la_usa(self):
        self.config.provisionar_decimo = True
        quincena = self._confirmar('2030-04-01', '2030-04-15')
        sumas = self._sumas(quincena.move_id)
        self.assertEqual(sumas[self.c_decimo], (0.0, 100.0))   # 1,200 devengados / 12
        self.assertEqual(sumas[self.c_sueldos][0], 1300.0)      # 1,200 de sueldos + 100 de provisión
        self.assertAlmostEqual(sum(quincena.move_id.line_ids.mapped('debit')),
                               sum(quincena.move_id.line_ids.mapped('credit')))
        decimo = self._decimo('2')
        decimo.action_calcular()
        decimo.action_confirmar()
        sumas = self._sumas(decimo.move_id)
        self.assertEqual(sumas[self.c_decimo][0], decimo.total_devengado)  # se paga lo provisionado
        self.assertNotIn(self.c_sueldos, sumas)

    def test_falta_la_cuenta_de_provision(self):
        self.config.provisionar_decimo = True
        self.config.cuenta_decimo_id = False
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        with self.assertRaisesTexto(UserError, 'Provisión del décimo'):
            planilla.action_confirmar()


@tagged('post_install', '-at_install')
class TestVacacionesPrimaLiquidacion(NominaCommon):

    def test_vacaciones_ganadas_tomadas_y_saldo(self):
        # Ana entró el 1 de enero de 2029: al 31 de marzo de 2030 van 455 días de servicio → 455 / 11 días de descanso
        ganadas, tomadas, saldo = self.ana._dcasa_vacaciones(date(2030, 3, 31))
        self.assertEqual((ganadas, tomadas, saldo), (41.36, 0.0, 41.36))
        vacacion = self.env['dcasa.nomina.vacacion'].create({
            'empleado_id': self.ana.id, 'desde': '2030-02-01', 'hasta': '2030-02-10'})
        self.assertEqual(vacacion.dias, 10.0)
        vacacion.action_confirmar()
        self.assertEqual(self.ana._dcasa_vacaciones(date(2030, 3, 31)), (41.36, 10.0, 31.36))
        # una cancelada no cuenta
        vacacion.action_cancelar()
        self.assertEqual(self.ana._dcasa_vacaciones(date(2030, 3, 31))[1], 0.0)

    def test_no_se_confirman_mas_dias_de_los_ganados_ni_fechas_cruzadas(self):
        Vacacion = self.env['dcasa.nomina.vacacion']
        demasiadas = Vacacion.create({'empleado_id': self.beto.id, 'desde': '2030-03-20', 'hasta': '2030-04-30'})
        with self.assertRaisesTexto(UserError, 'Solo tiene'):
            demasiadas.action_confirmar()
        primera = Vacacion.create({'empleado_id': self.ana.id, 'desde': '2030-02-01', 'hasta': '2030-02-10'})
        primera.action_confirmar()
        cruzada = Vacacion.create({'empleado_id': self.ana.id, 'desde': '2030-02-05', 'hasta': '2030-02-12'})
        with self.assertRaisesTexto(UserError, 'se cruzan'):
            cruzada.action_confirmar()

    def test_vacaciones_con_fechas_al_reves_o_sin_dias(self):
        with self.assertRaises(Exception):  # noqa: B017, PT011
            self.env['dcasa.nomina.vacacion'].create({
                'empleado_id': self.ana.id, 'desde': '2030-02-10', 'hasta': '2030-02-01'})

    def test_prima_de_antiguedad_acumulada(self):
        # 1,200 / 4.3333 por semana × (455 / 365) años × 1 semana por año
        self.assertAlmostEqual(self.ana._dcasa_prima(date(2030, 3, 31)), 345.22, delta=0.05)
        self.assertEqual(self.ana._dcasa_prima(date(2028, 12, 31)), 0.0)  # antes de entrar

    def test_el_salario_cambia_con_el_historial_de_la_ficha(self):
        self.ana.create_version({'date_version': '2030-02-01', 'wage': 1500})
        self.assertEqual(self.ana._dcasa_salario_mensual(date(2030, 1, 15)), 1200.0)
        self.assertEqual(self.ana._dcasa_salario_mensual(date(2030, 3, 15)), 1500.0)
        planilla = self._planilla()
        planilla.action_calcular()
        self.assertEqual(self._linea(planilla, self.ana).salario, 750.0)

    def test_liquidacion(self):
        planilla = self._planilla(entorno=self.entorno)  # confirmada hasta el 15 de marzo
        planilla.action_calcular()
        planilla.action_confirmar()
        liquidacion = self.env['dcasa.nomina.liquidacion'].create({
            'empleado_id': self.ana.id, 'fecha_salida': '2030-03-31', 'motivo': 'renuncia'})
        liquidacion.action_calcular()
        self.assertEqual(liquidacion.estado, 'calculada')
        self.assertEqual(liquidacion.parametros_id, self.vigencia)
        self.assertEqual(liquidacion.dias_pendientes, 16)             # del 16 al 31 de marzo
        self.assertEqual(liquidacion.salario_pendiente, 640.0)         # 1,200 / 30 × 16
        self.assertEqual(liquidacion.decimo_proporcional, 403.33)      # (600 + 106 días × 40) / 12
        self.assertEqual(liquidacion.vacaciones_dias, 41.36)
        self.assertEqual(liquidacion.vacaciones_valor, 1654.4)
        self.assertAlmostEqual(liquidacion.prima, 345.22, delta=0.05)
        # seguro social y educativo (11 %) sobre salario + vacaciones y 7.25 % sobre el décimo
        self.assertAlmostEqual(liquidacion.seguro_social, 281.62, delta=0.05)
        self.assertAlmostEqual(liquidacion.total, 640 + 403.33 + 1654.4 + liquidacion.prima - 281.62, delta=0.05)
        liquidacion.indemnizacion = 500.0
        liquidacion.isr = 50.0
        self.assertAlmostEqual(liquidacion.total, 640 + 403.33 + 1654.4 + liquidacion.prima + 500 - 281.62 - 50,
                               delta=0.05)
        liquidacion.action_revisar()
        self.assertEqual(liquidacion.estado, 'revisada')

    def test_liquidacion_sin_prima_si_no_corresponde(self):
        liquidacion = self.env['dcasa.nomina.liquidacion'].create({
            'empleado_id': self.ana.id, 'fecha_salida': '2030-03-31', 'incluir_prima': False})
        liquidacion.action_calcular()
        self.assertEqual(liquidacion.prima, 0.0)

    def test_liquidacion_exige_ingreso_y_no_se_revisa_con_tasas_sin_validar(self):
        sin_ingreso = self.env['hr.employee'].create({'name': 'Sin Ingreso Liquidación', 'company_id': self.company.id})
        with self.assertRaisesTexto(UserError, 'fecha de ingreso'):
            self.env['dcasa.nomina.liquidacion'].create(
                {'empleado_id': sin_ingreso.id, 'fecha_salida': '2030-03-31'}).action_calcular()
        self._vigencia('2031-01-01')
        liquidacion = self.env['dcasa.nomina.liquidacion'].create({
            'empleado_id': self.ana.id, 'fecha_salida': '2031-02-01'})
        liquidacion.action_calcular()
        self.assertFalse(liquidacion.parametros_validados)
        with self.assertRaisesTexto(UserError, 'no las valida'):
            liquidacion.action_revisar()
