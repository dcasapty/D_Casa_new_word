"""Las pantallas de la nómina trabajan como las usa una persona: formularios con sus valores por omisión, campos de
solo lectura y líneas editables (se simulan con el ayudante ``Form`` de Odoo, que respeta cada atributo de la vista)."""
from datetime import date

from odoo.tests import Form, new_test_user, tagged

from .common import NominaCommon


@tagged('post_install', '-at_install')
class TestVistas(NominaCommon):

    def test_planilla_quincenal_desde_el_formulario(self):
        with Form(self.entorno['dcasa.nomina.planilla']) as form:
            self.assertTrue(form.fecha_desde and form.fecha_hasta and form.fecha_pago)  # propone una quincena completa
            form.fecha_desde = '2030-03-01'
            form.fecha_hasta = '2030-03-15'
        planilla = form.record
        self.assertEqual(planilla.estado, 'borrador')
        self.assertEqual(planilla.tipo, 'quincenal')
        planilla.action_calcular()
        self.assertEqual(len(planilla.linea_ids), 2)

    def test_decimo_desde_el_formulario_arma_las_fechas_de_la_partida(self):
        with Form(self.entorno['dcasa.nomina.planilla'].with_context(default_tipo='decimo')) as form:
            form.anio = 2030
            form.partida = '2'
            self.assertEqual(form.fecha_desde, date(2030, 4, 1))
            self.assertEqual(form.fecha_hasta, date(2030, 7, 31))
            self.assertEqual(form.fecha_pago, date(2030, 8, 15))
        self.assertEqual(form.record.tipo, 'decimo')

    def test_las_lineas_se_editan_en_la_planilla_y_recalculan(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        with Form(planilla) as form:
            with form.linea_ids.edit(0) as linea:
                linea.otros_ingresos = 100.0
                linea.otros_descuentos = 10.0
        ana = self._linea(planilla, self.ana)
        beto = self._linea(planilla, self.beto)
        editada = ana if ana.otros_ingresos else beto
        self.assertEqual(editada.otros_ingresos, 100.0)
        self.assertEqual(editada.devengado, editada.salario + 100.0)
        self.assertEqual(editada.otros_descuentos, 10.0)

    def test_una_planilla_confirmada_no_deja_editar_sus_lineas_en_la_pantalla(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        with Form(planilla) as form:
            with self.assertRaises(AssertionError):
                form.fecha_hasta = '2030-03-20'  # solo lectura una vez calculada y confirmada

    def test_tasas_validadas_son_solo_lectura(self):
        with Form(self.vigencia.with_user(self.usuario)) as form:
            with self.assertRaises(AssertionError):
                form.css_patronal = 99.0
            form.notas_contador = 'Revisado'
        self.assertEqual(self.vigencia.notas_contador, 'Revisado')

    def test_tasas_por_validar_se_editan_desde_el_formulario(self):
        vigencia = self._vigencia('2031-01-01')
        with Form(vigencia.with_user(self.usuario)) as form:
            form.riesgo_profesional = 1.5
            with form.tramo_ids.edit(0) as tramo:
                tramo.tasa = 1.0
        self.assertEqual(vigencia.riesgo_profesional, 1.5)
        self.assertEqual(vigencia.tramo_ids.sorted('desde')[0].tasa, 1.0)

    def test_reembolso_desde_el_formulario_del_colaborador(self):
        usuario = new_test_user(self.env, login='ana_form_nomina', name='Ana Formulario', groups='base.group_user')
        self.ana.user_id = usuario
        with Form(self.env(user=usuario)['dcasa.nomina.reembolso']) as form:
            self.assertEqual(form.empleado_id, self.ana)  # su propia ficha, por omisión
            form.concepto = 'Bolsas para la entrega'
            form.monto = 12.5
        reembolso = form.record
        self.assertEqual((reembolso.estado, reembolso.monto), ('borrador', 12.5))
        self.assertEqual(reembolso.cuenta_gasto_id, self.c_reembolso)

    def test_la_ficha_del_empleado_trae_la_seccion_de_nomina(self):
        with Form(self.ana.with_user(self.usuario)) as form:
            form.dcasa_forma_pago = 'efectivo'
            form.dcasa_deduccion_isr_anual = 800.0
        self.assertEqual((self.ana.dcasa_forma_pago, self.ana.dcasa_deduccion_isr_anual), ('efectivo', 800.0))

    def test_vacaciones_y_liquidacion_desde_el_formulario(self):
        with Form(self.entorno['dcasa.nomina.vacacion']) as form:
            form.empleado_id = self.ana
            form.desde = '2030-02-01'
            form.hasta = '2030-02-05'
            self.assertEqual(form.dias, 5.0)
        with Form(self.entorno['dcasa.nomina.liquidacion']) as form:
            form.empleado_id = self.ana
            form.fecha_salida = '2030-03-31'
        self.assertEqual(form.record.estado, 'borrador')

    def test_las_vistas_de_lista_y_busqueda_cargan(self):
        for modelo in ('dcasa.nomina.planilla', 'dcasa.nomina.parametros', 'dcasa.nomina.reembolso',
                       'dcasa.nomina.vacacion', 'dcasa.nomina.liquidacion'):
            with self.subTest(modelo=modelo):
                vistas = self.entorno[modelo].get_views([(False, 'list'), (False, 'form'), (False, 'search')])
                self.assertTrue(vistas['views']['list']['arch'])
                self.assertTrue(vistas['views']['form']['arch'])
