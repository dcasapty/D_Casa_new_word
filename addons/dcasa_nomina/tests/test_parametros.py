"""Tasas con vigencia: validación del contador, congelamiento y selección por fecha."""
from datetime import date

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import TASAS, NominaCommon


@tagged('post_install', '-at_install')
class TestParametros(NominaCommon):

    def test_no_se_valida_con_tasas_faltantes(self):
        vigencia = self._vigencia('2031-01-01', riesgo_profesional=0.0)
        self.assertIn('Riesgo profesional', vigencia.pendientes)
        with self.assertRaisesTexto(UserError, 'Riesgo profesional'):
            vigencia.action_validar()
        self.assertEqual(vigencia.estado, 'borrador')

    def test_los_tramos_tienen_que_ser_seguidos(self):
        vigencia = self._vigencia('2031-01-01')
        vigencia.tramo_ids[1].hasta = 40000  # el siguiente empieza en 50,000: queda un hueco
        self.assertIn('seguidos', vigencia.pendientes)
        with self.assertRaises(UserError):
            vigencia.action_validar()
        vigencia.tramo_ids[1].hasta = 50000
        vigencia.tramo_ids.filtered(lambda t: not t.hasta).hasta = 90000  # el último no puede tener tope
        self.assertIn('último tramo', vigencia.pendientes)
        vigencia.tramo_ids.filtered(lambda t: t.hasta == 90000).hasta = 0
        vigencia.tramo_ids.filtered(lambda t: t.desde == 0).desde = 1  # el primero tiene que empezar en 0
        self.assertIn('empezar en 0', vigencia.pendientes)
        vigencia.tramo_ids.filtered(lambda t: t.desde == 1).desde = 0
        self.assertFalse(vigencia.pendientes)

    def test_sin_tramos_no_se_valida(self):
        vigencia = self.env['dcasa.nomina.parametros'].create({
            'company_id': self.company.id, 'fecha_desde': '2031-02-01', **TASAS})
        with self.assertRaisesTexto(UserError, 'faltan los tramos'):
            vigencia.action_validar()

    def test_tramo_con_valores_imposibles(self):
        vigencia = self._vigencia('2031-01-01')
        with self.assertRaises(ValidationError):
            vigencia.tramo_ids[0].tasa = 150.0
        with self.assertRaises(ValidationError):
            vigencia.tramo_ids[0].hasta = -5.0

    def test_validar_deja_constancia_y_congela(self):
        vigencia = self._vigencia('2031-01-01')
        vigencia.with_user(self.usuario).action_validar()
        self.assertEqual(vigencia.estado, 'validado')
        self.assertEqual(vigencia.validado_por, self.usuario)
        self.assertTrue(vigencia.validado_el)
        vigencia = vigencia.with_user(self.usuario)
        with self.assertRaisesTexto(UserError, 'validadas'):
            vigencia.write({'css_patronal': 1.0})
        with self.assertRaisesTexto(UserError, 'validadas'):
            vigencia.tramo_ids[0].write({'tasa': 5.0})
        with self.assertRaisesTexto(UserError, 'validadas'):
            vigencia.write({'tramo_ids': [(0, 0, {'desde': 90000, 'hasta': 0, 'tasa': 30})]})
        with self.assertRaisesTexto(UserError, 'validada'):
            vigencia.unlink()
        # lo que no cambia el resultado sí se puede anotar
        vigencia.notas_contador = 'Revisado contra la Gaceta Oficial'
        self.assertEqual(vigencia.notas_contador, 'Revisado contra la Gaceta Oficial')

    def test_el_estado_solo_cambia_con_los_botones(self):
        vigencia = self._vigencia('2031-01-01')
        with self.assertRaisesTexto(UserError, 'botones'):
            vigencia.with_user(self.usuario).write({'estado': 'validado'})
        self.assertEqual(vigencia.estado, 'borrador')

    def test_reabrir_y_cambiar_mientras_no_la_use_una_planilla(self):
        vigencia = self._vigencia('2031-01-01', validar=True)
        vigencia.with_user(self.usuario).action_reabrir()
        self.assertEqual((vigencia.estado, vigencia.validado_por), ('borrador', self.env['res.users']))
        vigencia.with_user(self.usuario).write({'css_patronal': 14.0})
        self.assertEqual(vigencia.css_patronal, 14.0)

    def test_una_vigencia_usada_por_una_planilla_confirmada_no_se_reabre_ni_se_cambia(self):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        self.assertEqual(self.vigencia.planillas_usadas, 1)
        with self.assertRaisesTexto(UserError, 'ya se usaron'):
            self.vigencia.with_user(self.usuario).action_reabrir()
        with self.assertRaises(UserError):
            self.vigencia.with_user(self.usuario).write({'css_patronal': 1.0})
        with self.assertRaises(UserError):
            self.vigencia.with_user(self.usuario).unlink()

    def test_una_copia_nace_por_validar(self):
        copia = self.vigencia.copy({'fecha_desde': '2032-01-01'})
        self.assertEqual(copia.estado, 'borrador')
        self.assertFalse(copia.validado_por)
        self.assertEqual(len(copia.tramo_ids), 3)

    def test_vigente_es_la_mas_reciente_por_fecha_aunque_este_por_validar(self):
        Parametros = self.env['dcasa.nomina.parametros']
        self.assertEqual(Parametros._vigente(date(2030, 3, 1), self.company), self.vigencia)
        por_validar = self._vigencia('2030-05-01')
        # la que rige desde mayo es la nueva aunque el contador no la haya validado: nunca se aplican por omisión
        # las tasas validadas de antes (la ley pudo haber cambiado)
        self.assertEqual(Parametros._vigente(date(2030, 5, 20), self.company), por_validar)
        self.assertEqual(Parametros._vigente(date(2030, 4, 30), self.company), self.vigencia)
        planilla = self._planilla('2030-05-01', '2030-05-15')
        planilla.action_calcular()
        self.assertEqual(planilla.parametros_id, por_validar)
        with self.assertRaisesTexto(UserError, 'no las valida el contador'):
            planilla.action_confirmar()
        por_validar.action_validar()
        planilla.action_calcular()
        planilla.action_confirmar()
        self.assertEqual(planilla.estado, 'confirmada')
        # antes de la primera vigencia validada rige la de fábrica (abril de 2029), por validar
        self.assertEqual(Parametros._vigente(date(2029, 6, 1), self.company).estado, 'borrador')
        self.assertFalse(Parametros._vigente(date(2020, 1, 1), self.company))

    def test_una_sola_vigencia_por_fecha(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._vigencia('2030-01-01')

    def test_las_tasas_de_fabrica_quedan_por_validar_y_sin_inventar(self):
        base = self.env.ref('dcasa_nomina.parametros_2025_04')
        self.assertEqual(base.estado, 'borrador')
        self.assertEqual(base.riesgo_profesional, 0.0)  # lo fija el contador
        self.assertFalse(base.decimo_listo)
        self.assertEqual(base.css_trabajador_decimo, 0.0)
        self.assertIn('NO verificado', base.fuente)
        self.assertTrue(base.pendientes)  # no se puede validar tal cual
        with self.assertRaises(UserError):
            base.action_validar()

    def test_solo_nomina_toca_las_tasas(self):
        ventas = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Vendedora Prueba Nómina', 'login': 'vend_nom', 'email': 'vend_nom@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('dcasa_base.group_vendedora').id])]})
        with self.assertRaises(AccessError):
            self.env['dcasa.nomina.parametros'].with_user(ventas).search([])
