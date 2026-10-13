"""Los sueldos son datos delicados: quién los ve, qué métodos se pueden llamar por RPC y que los PDF salen."""
from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import NominaCommon

MODELOS = ('dcasa.nomina.parametros', 'dcasa.nomina.config', 'dcasa.nomina.planilla', 'dcasa.nomina.linea',
           'dcasa.nomina.vacacion', 'dcasa.nomina.liquidacion')


@tagged('post_install', '-at_install')
class TestSeguridadNomina(NominaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vend_nomina', name='Vendedora Nómina',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.gerencia = new_test_user(cls.env, login='ger_nomina', name='Gerencia Nómina',
                                     groups='base.group_user,dcasa_base.group_gerencia')

    def rpc(self, usuario, modelo, metodo, ids=None, args=(), kwargs=None):
        registros = self.env(user=usuario)[modelo].browse(ids or [])
        return call_kw(registros, metodo, [ids or [], *args] if ids else list(args), kwargs or {})

    def test_la_vendedora_no_ve_nada_de_nomina(self):
        planilla = self._planilla()
        planilla.action_calcular()
        for modelo in MODELOS:
            with self.subTest(modelo=modelo), self.assertRaises(AccessError):
                self.env(user=self.vendedora)[modelo].search([])
        with self.assertRaises(AccessError):
            planilla.with_user(self.vendedora).read(['total_neto'])

    def test_la_vendedora_no_ve_el_salario_de_la_ficha(self):
        ana = self.ana.with_user(self.vendedora)
        with self.assertRaises(AccessError):
            ana.read(['wage'])
        with self.assertRaises(AccessError):
            ana.read(['dcasa_vac_valor'])

    def test_la_vendedora_no_llama_a_los_botones_por_rpc(self):
        planilla = self._planilla()
        for metodo in ('action_calcular', 'action_confirmar', 'action_pagar', 'action_cancelar', 'action_borrador'):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                self.rpc(self.vendedora, 'dcasa.nomina.planilla', metodo, planilla.ids)
        with self.assertRaises(AccessError):
            self.rpc(self.vendedora, 'dcasa.nomina.parametros', 'action_validar', self.vigencia.ids)

    def test_gerencia_administra_la_nomina_sin_darle_nada_a_la_vendedora(self):
        self.assertTrue(self.gerencia.has_group('dcasa_nomina.group_nomina'))
        self.assertFalse(self.vendedora.has_group('dcasa_nomina.group_nomina'))
        planilla = self._planilla(entorno=self.env(user=self.gerencia))
        planilla.action_calcular()
        self.assertTrue(planilla.linea_ids)

    def test_la_configuracion_la_abre_quien_administra_la_nomina(self):
        accion = self.env['dcasa.nomina.config'].with_user(self.gerencia).action_abrir()
        self.assertEqual(accion['res_model'], 'dcasa.nomina.config')
        with self.assertRaises(AccessError):
            self.env['dcasa.nomina.config'].with_user(self.vendedora).action_abrir()

    def test_la_configuracion_propone_las_cuentas_del_plan_de_panama_y_un_diario(self):
        Config = self.env['dcasa.nomina.config']
        otra = self.env['res.company'].create({'name': 'Otra empresa de prueba nómina'})
        config = Config._de(otra)
        self.assertEqual(config.company_id, otra)
        self.assertTrue(config.diario_id)
        self.assertEqual(config.diario_id.code, 'NOM')
        self.assertEqual(Config._de(otra), config)  # no crea otra
        self.assertEqual(Config.search_count([('company_id', '=', otra.id)]), 1)

    def test_los_pdf_se_generan(self):
        planilla = self._planilla()
        planilla.action_calcular()
        self._linea(planilla, self.ana).otros_descuentos = 10.0
        liquidacion = self.env['dcasa.nomina.liquidacion'].create({
            'empleado_id': self.ana.id, 'fecha_salida': '2030-03-31'})
        liquidacion.action_calcular()
        for accion, registros, texto in (
            ('dcasa_nomina.accion_comprobante_pago', planilla.linea_ids, 'Comprobante de pago'),
            ('dcasa_nomina.accion_resumen_planilla', planilla, 'Total'),
            ('dcasa_nomina.accion_liquidacion', liquidacion, 'Total a pagar'),
        ):
            with self.subTest(accion=accion):
                html, _tipo = self.env['ir.actions.report']._render_qweb_html(accion, registros.ids)
                self.assertIn(texto, html.decode())
        # el comprobante muestra a cada colaborador y su neto
        html, _tipo = self.env['ir.actions.report']._render_qweb_html(
            'dcasa_nomina.accion_comprobante_pago', planilla.linea_ids.ids)
        cuerpo = html.decode()
        self.assertIn('Ana Prueba Nómina', cuerpo)
        self.assertIn('Beto Prueba Nómina', cuerpo)
