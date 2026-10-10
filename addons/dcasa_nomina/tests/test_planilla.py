"""Planilla quincenal: cálculo, prorrateo, extras, asiento, validación, pago, reverso y periodos."""
from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import DESDE, HASTA, NominaCommon


@tagged('post_install', '-at_install')
class TestPlanilla(NominaCommon):

    def test_calculo_de_una_quincena(self):
        planilla = self._planilla()
        planilla.action_calcular()
        self.assertEqual(planilla.estado, 'calculada')
        self.assertEqual(planilla.parametros_id, self.vigencia)
        ana = self._linea(planilla, self.ana)
        self.assertEqual((ana.dias_periodo, ana.dias_pagados), (15, 15))
        self.assertEqual(ana.salario, 600.0)
        self.assertEqual(ana.devengado, 600.0)
        self.assertEqual(ana.css_trabajador, 58.5)       # 9.75 %
        self.assertEqual(ana.se_trabajador, 7.5)         # 1.25 %
        self.assertEqual(ana.isr, 21.25)                 # (600 × 24 − 11,000) × 15 % / 24
        self.assertEqual(ana.neto, 512.75)
        self.assertEqual(ana.css_patronal, 79.5)         # 13.25 %
        self.assertEqual(ana.se_patronal, 9.0)           # 1.5 %
        self.assertEqual(ana.riesgo_profesional, 5.88)   # 0.98 %
        self.assertEqual(ana.costo_patronal, 94.38)

    def test_quien_entra_a_mitad_de_periodo_cobra_solo_sus_dias(self):
        planilla = self._planilla()
        planilla.action_calcular()
        beto = self._linea(planilla, self.beto)
        self.assertEqual(beto.dias_pagados, 7)  # del 9 al 15 de marzo
        self.assertEqual(beto.salario, 280.0)
        self.assertEqual(beto.css_trabajador, 27.3)
        self.assertEqual(beto.isr, 9.92)  # el impuesto de una quincena completa (21.25) × 7/15
        self.assertEqual(beto.neto, 239.28)

    def test_quien_ya_salio_o_no_ha_entrado_no_aparece(self):
        futuro = self._empleado('Futuro Prueba', 1000, '2030-04-01')
        salio = self._empleado('Salio Prueba', 1000, '2029-01-01', contract_date_end='2030-02-20')
        planilla = self._planilla()
        planilla.action_calcular()
        self.assertFalse(self._linea(planilla, futuro))
        self.assertFalse(self._linea(planilla, salio))

    def test_sin_fecha_de_ingreso_o_sin_salario_avisa(self):
        sin_ingreso = self.env['hr.employee'].create({'name': 'Sin Ingreso Prueba', 'company_id': self.company.id,
                                                      'wage': 900})
        planilla = self._planilla()
        planilla.action_calcular()
        self.assertFalse(self._linea(planilla, sin_ingreso))
        self.assertIn('Sin Ingreso Prueba', planilla.avisos)

    def test_otros_ingresos_pagan_aportes_y_su_isr_adicional(self):
        planilla = self._planilla()
        planilla.action_calcular()
        ana = self._linea(planilla, self.ana)
        ana.otros_ingresos = 100.0
        self.assertEqual(ana.devengado, 700.0)
        self.assertEqual(ana.css_trabajador, 68.25)
        self.assertEqual(ana.se_trabajador, 8.75)
        self.assertEqual(ana.isr, 36.25)  # 21.25 de la quincena + 15 (15 % de los 100 extra)
        self.assertEqual(ana.neto, 586.75)

    def test_recalcular_conserva_lo_escrito_a_mano_y_revierte_el_salario(self):
        planilla = self._planilla()
        planilla.action_calcular()
        ana = self._linea(planilla, self.ana)
        ana.write({'otros_ingresos': 50.0, 'otros_descuentos': 20.0, 'salario': 999.0})
        planilla.action_calcular()
        ana = self._linea(planilla, self.ana)
        self.assertEqual((ana.otros_ingresos, ana.otros_descuentos), (50.0, 20.0))
        self.assertEqual(ana.salario, 600.0)  # el salario vuelve al del cálculo
        self.assertEqual(len(planilla.linea_ids), 2)  # sin duplicar a nadie

    def test_isr_deducciones_del_colaborador(self):
        self.ana.dcasa_deduccion_isr_anual = 1200.0
        planilla = self._planilla()
        planilla.action_calcular()
        self.assertEqual(self._linea(planilla, self.ana).isr, 13.75)  # (14,400 − 1,200 − 11,000) × 15 % / 24

    def test_isr_despues_de_seguro_social_y_educativo_si_los_parametros_lo_dicen(self):
        vigencia = self._vigencia('2030-06-01', isr_descuenta_css_se=True)
        planilla = self._planilla('2030-06-01', '2030-06-15')
        planilla.action_calcular()
        self.assertEqual(planilla.parametros_id, vigencia)
        # 14,400 × (1 − 11 %) = 12,816 → (12,816 − 11,000) × 15 % / 24
        self.assertEqual(self._linea(planilla, self.ana).isr, 11.35)

    def test_la_planilla_usa_la_vigencia_de_su_fecha(self):
        nueva = self._vigencia('2030-04-01', validar=True, css_patronal=14.25)
        antes = self._planilla('2030-03-16', '2030-03-31')
        antes.action_calcular()
        self.assertEqual(antes.parametros_id, self.vigencia)
        despues = self._planilla('2030-04-01', '2030-04-15')
        despues.action_calcular()
        self.assertEqual(despues.parametros_id, nueva)
        self.assertEqual(self._linea(despues, self.ana).css_patronal, 85.5)  # 14.25 % de 600

    # ------------------------------------------------------------------
    # Asiento contable
    # ------------------------------------------------------------------

    def test_confirmar_publica_un_asiento_que_cuadra(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        self.assertEqual(planilla.estado, 'confirmada')
        asiento = planilla.move_id
        self.assertEqual(asiento.state, 'posted')
        self.assertEqual(asiento.date, HASTA)
        self.assertEqual(asiento.journal_id, self.config.diario_id)
        self.assertAlmostEqual(sum(asiento.line_ids.mapped('debit')), sum(asiento.line_ids.mapped('credit')))
        sumas = self._sumas(asiento)
        self.assertEqual(sumas[self.c_sueldos], (880.0, 0.0))
        self.assertEqual(sumas[self.c_cargas], (138.42, 0.0))      # 116.60 + 13.20 + 8.62
        self.assertEqual(sumas[self.c_por_pagar], (0.0, 752.03))   # 512.75 + 239.28
        self.assertEqual(sumas[self.c_css], (0.0, 202.4))          # 85.80 del trabajador + 116.60 del patrono
        self.assertEqual(sumas[self.c_se], (0.0, 24.2))
        self.assertEqual(sumas[self.c_rp], (0.0, 8.62))
        self.assertEqual(sumas[self.c_isr], (0.0, 31.17))
        # lo que se le debe a cada persona queda a nombre de su contacto
        por_pagar = asiento.line_ids.filtered(lambda ln: ln.account_id == self.c_por_pagar)
        self.assertEqual(set(por_pagar.partner_id), {self.ana.work_contact_id, self.beto.work_contact_id})

    def test_otros_descuentos_van_a_su_cuenta(self):
        planilla = self._planilla()
        planilla.action_calcular()
        self._linea(planilla, self.ana).otros_descuentos = 30.0
        planilla.action_confirmar()
        self.assertEqual(self._sumas(planilla.move_id)[self.c_otros], (0.0, 30.0))
        self.assertAlmostEqual(sum(planilla.move_id.line_ids.mapped('debit')),
                               sum(planilla.move_id.line_ids.mapped('credit')))

    def test_no_confirma_con_tasas_sin_validar(self):
        self._vigencia('2031-01-01')  # por validar
        planilla = self._planilla('2031-03-01', '2031-03-15')
        planilla.action_calcular()  # como borrador sí se puede
        self.assertFalse(planilla.parametros_validados)
        with self.assertRaisesTexto(UserError, 'no las valida el contador'):
            planilla.action_confirmar()
        self.assertEqual(planilla.estado, 'calculada')
        self.assertFalse(planilla.move_id)

    def test_no_confirma_si_cambiaron_las_tasas_despues_de_calcular(self):
        planilla = self._planilla()
        planilla.action_calcular()
        self._vigencia('2030-03-10', validar=True, css_patronal=20.0)
        with self.assertRaisesTexto(UserError, 'vuelve a calcular'):
            planilla.action_confirmar()

    def test_no_confirma_si_falta_una_cuenta(self):
        self.config.cuenta_isr_pagar_id = False
        planilla = self._planilla()
        planilla.action_calcular()
        with self.assertRaisesTexto(UserError, 'ISR retenido por pagar'):
            planilla.action_confirmar()

    def test_no_se_confirma_dos_veces_ni_sin_calcular(self):
        planilla = self._planilla()
        with self.assertRaisesTexto(UserError, 'Calcula la planilla'):
            planilla.action_confirmar()
        planilla.action_calcular()
        planilla.action_confirmar()
        with self.assertRaisesTexto(UserError, 'Calcula la planilla'):
            planilla.action_confirmar()

    def test_descuentos_mayores_que_el_pago_impiden_confirmar(self):
        planilla = self._planilla()
        planilla.action_calcular()
        self._linea(planilla, self.beto).otros_descuentos = 900.0
        with self.assertRaisesTexto(UserError, 'superan lo que se le paga'):
            planilla.action_confirmar()

    def test_una_planilla_confirmada_no_se_edita(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        ana = self._linea(planilla, self.ana)
        with self.assertRaises(UserError):
            ana.write({'otros_ingresos': 500.0})
        with self.assertRaises(UserError):
            planilla.write({'fecha_hasta': '2030-03-31'})
        with self.assertRaises(UserError):
            ana.unlink()
        with self.assertRaises(UserError):
            planilla.unlink()
        with self.assertRaises(UserError):
            planilla.action_calcular()
        with self.assertRaises(AccessError):  # el estado no se escribe a mano
            planilla.write({'estado': 'borrador'})

    # ------------------------------------------------------------------
    # Periodos, pago y reverso
    # ------------------------------------------------------------------

    def test_no_se_paga_dos_veces_el_mismo_periodo(self):
        self._planilla()
        with self.assertRaisesTexto(ValidationError, 'no se paga dos veces'):
            self._planilla('2030-03-10', '2030-03-20')
        # otra quincena distinta sí
        self._planilla('2030-03-16', '2030-03-31')

    def test_una_planilla_cancelada_libera_el_periodo(self):
        planilla = self._planilla()
        planilla.action_calcular()
        planilla.action_cancelar()
        self.assertEqual(planilla.estado, 'cancelada')
        self._planilla()  # no falla

    def test_pagar_crea_un_pago_por_colaborador_y_concilia_con_lo_que_se_debe(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        with self.assertRaisesTexto(UserError, 'Pagar desde'):
            planilla.action_pagar()
        planilla.diario_pago_id = self.banco
        planilla.action_pagar()
        self.assertEqual(planilla.estado, 'pagada')
        pagos = planilla.linea_ids.payment_id
        self.assertEqual(len(pagos), 2)
        self.assertEqual(sorted(pagos.mapped('amount')), [239.28, 512.75])
        self.assertTrue(all(p.state in ('paid', 'in_process', 'posted') for p in pagos))
        self.assertEqual(set(pagos.mapped('partner_id')), {self.ana.work_contact_id, self.beto.work_contact_id})
        # la cuenta de sueldos por pagar es conciliable: lo que se debía queda saldado
        deuda = planilla.move_id.line_ids.filtered(lambda ln: ln.account_id == self.c_por_pagar)
        self.assertTrue(all(deuda.mapped('reconciled')))
        with self.assertRaisesTexto(UserError, 'confirmada'):
            planilla.action_pagar()

    def test_cancelar_una_confirmada_reversa_el_asiento(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        asiento = planilla.move_id
        planilla.action_cancelar()
        self.assertEqual(planilla.estado, 'cancelada')
        reverso = planilla.move_reverso_id
        self.assertTrue(reverso)
        self.assertEqual(reverso.state, 'posted')
        self.assertEqual(reverso.reversed_entry_id, asiento)
        self.assertAlmostEqual(sum(asiento.line_ids.mapped('balance')) + sum(reverso.line_ids.mapped('balance')), 0.0)

    def test_no_se_cancela_una_planilla_con_pagos(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        planilla.diario_pago_id = self.banco
        planilla.action_pagar()
        with self.assertRaisesTexto(UserError, 'ya tiene pagos'):
            planilla.action_cancelar()

    def test_volver_a_borrador_solo_si_no_tuvo_asiento(self):
        planilla = self._planilla()
        planilla.action_calcular()
        planilla.action_borrador()
        self.assertEqual(planilla.estado, 'borrador')
        planilla.action_calcular()
        planilla.action_confirmar()
        with self.assertRaises(UserError):
            planilla.action_borrador()

    def test_sin_calcular_nada_las_fechas_por_omision_son_una_quincena_completa(self):
        planilla = self.env['dcasa.nomina.planilla'].create({'tipo': 'quincenal'})
        self.assertIn(planilla.fecha_desde.day, (1, 16))
        self.assertIn(planilla.fecha_hasta.day, (15, 28, 29, 30, 31))
        self.assertEqual(planilla.fecha_pago, planilla.fecha_hasta)
        self.assertEqual(date(2030, 3, 1), DESDE)  # las fechas de las pruebas no cambian sin avisar
