"""Cuarta revisión adversarial, menor 1: un pago con fecha futura se calcula con la versión de HOY y esa versión puede
cambiar (llegó el día, o empezó a regir otra). El barrido de cada noche y «armar» una liquidación lo vuelven a mirar: la
venta queda igual que si se cobrara «desde cero» con la misma fecha.

Cifras y personas de PRUEBA."""
# ruff: noqa: E501
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_comision_web.tests.test_vendedoras import VendedoraCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestPagoConFechaFutura(VendedoraCommon):

    def setUp(self):
        super().setUp()
        self.Venta = self.env['dcasa.web.venta']
        # A (10 %) rige desde el 4 de marzo; B (5 %) desde el 14. Hoy es el 4 (lunes).
        self.A = self.version(10.0)
        self.B = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=10))

    def neto(self, venta, empleado=None):
        filas = self.libro(venta=venta, empleado=empleado)
        return sum(f.centavos for f in filas.filtered(lambda f: f.tipo in ('venta', 'devolucion', 'reverso')))

    def foto_libro(self):
        return sorted((f.id, f.empleado_id.id, f.tipo, f.centavos) for f in self.libro())

    def pago_a_futuro(self, dia='2030-03-20'):
        """Hoy (el 4) se registra un pago con fecha del 20: se calcula con la versión de HOY (A, 10 %)."""
        factura = self.venta_web(fecha=dia)
        venta = self.venta(factura)
        self.assertEqual((venta.reglas_id, self.neto(venta), venta.cobro_adelantado), (self.A, 10000, True))
        return factura, venta

    def assertSinCambios(self, que):
        antes = self.foto_libro()
        for venta in self.Venta.search([]):
            venta._reconciliar()
        self.Venta._barrido()
        self.Venta._poner_al_dia()
        self.assertEqual(antes, self.foto_libro(), 'correr la comparación otra vez no debe anotar nada: ' + que)

    def test_al_llegar_el_dia_el_barrido_la_calcula_con_la_version_que_rige_ese_dia(self):
        factura, venta = self.pago_a_futuro()
        self.avanzar('2030-03-21 15:00:00')
        self.Venta._barrido()
        self.assertEqual(venta.reglas_id, self.B)
        self.assertEqual(venta.porcentaje, 5.0)
        self.assertEqual(self.neto(venta), 5000)
        self.assertEqual((self.neto(venta, self.ana), self.neto(venta, self.beto)), (3000, 2000))
        directa = self.venta(self.venta_web(fecha='2030-03-20'))         # cobrarla «desde cero» hoy, con esa fecha
        self.assertEqual((directa.reglas_id, self.neto(directa)), (self.B, 5000))
        self.assertTrue(venta.cobro_adelantado, 'la señal de quien tecleó una fecha futura se queda para Gerencia')
        self.assertEqual(venta.fecha_cobro.isoformat(), '2030-03-20')
        self.assertSinCambios('al llegar el día')

    def test_el_libro_cuenta_lo_que_paso_con_un_reverso_y_su_motivo(self):
        factura, venta = self.pago_a_futuro()
        self.avanzar('2030-03-21 15:00:00')
        self.Venta._barrido()
        self.assertEqual(self.libro(venta=venta).mapped('tipo'), ['venta', 'venta', 'reverso', 'reverso', 'venta', 'venta'])
        reversos = self.libro(venta=venta, tipo='reverso')
        self.assertTrue(all('20/03/2030' in (fila.motivo or '') for fila in reversos), reversos.mapped('motivo'))
        nuevas = self.libro(venta=venta, tipo='venta').filtered(lambda f: f.reglas_id == self.B)
        self.assertEqual(len(nuevas), 2)
        self.assertTrue(all(f'versión {self.B.numero}' in (fila.motivo or '') for fila in nuevas), nuevas.mapped('motivo'))

    def test_armar_una_liquidacion_la_pone_al_dia_sin_esperar_al_barrido(self):
        factura, venta = self.pago_a_futuro()
        self.avanzar('2030-03-21 15:00:00')
        self.Venta._poner_al_dia()                 # lo que hacen armar y aprobar antes de sumar un centavo
        self.assertEqual((venta.reglas_id, self.neto(venta)), (self.B, 5000))
        self.assertSinCambios('armar')

    def test_antes_de_que_cambie_la_version_de_hoy_no_se_mueve_nada(self):
        factura, venta = self.pago_a_futuro()
        self.avanzar('2030-03-10 15:00:00')        # B todavía no rige: la de hoy sigue siendo A
        antes = self.foto_libro()
        self.Venta._barrido()
        self.Venta._poner_al_dia()
        self.assertEqual((venta.reglas_id, self.foto_libro()), (self.A, antes))

    def test_si_cambia_la_version_de_hoy_antes_del_dia_del_pago_tambien_se_vuelve_a_calcular(self):
        """Igual que cobrarla «desde cero» ese día: se calcula con la versión de HOY mientras el día no llegue."""
        factura, venta = self.pago_a_futuro('2030-03-25')
        self.avanzar('2030-03-16 15:00:00')        # B rige desde el 14; el pago es del 25
        self.Venta._barrido()
        directa = self.venta(self.venta_web(fecha='2030-03-25'))
        self.assertEqual((venta.reglas_id, directa.reglas_id), (self.B, self.B))
        self.assertEqual(self.neto(venta), self.neto(directa))
        self.assertTrue(venta.cobro_adelantado)
        self.assertSinCambios('antes del día')

    def test_si_la_version_es_la_misma_cuando_llega_el_dia_no_se_anota_nada(self):
        factura, venta = self.pago_a_futuro('2030-03-10')    # el 10 sigue rigiendo A
        antes = self.foto_libro()
        self.avanzar('2030-03-11 15:00:00')
        self.Venta._barrido()
        self.Venta._poner_al_dia()
        self.assertEqual(self.foto_libro(), antes)
        self.assertEqual(venta.reglas_id, self.A)
        self.assertTrue(venta.cobro_adelantado)

    def test_un_pago_normal_no_se_vuelve_a_evaluar_cuando_llega_otra_version(self):
        """Lo ya anotado no se recalcula: solo los pagos con fecha futura vuelven a escoger versión."""
        factura = self.venta_web(fecha='2030-03-04')
        venta = self.venta(factura)
        self.assertFalse(venta.cobro_adelantado)
        antes = self.foto_libro()
        self.avanzar('2030-03-21 15:00:00')
        self.Venta._barrido()
        self.Venta._poner_al_dia()
        self.assertEqual((venta.reglas_id, self.foto_libro()), (self.A, antes))

    def test_si_el_pago_se_cancelo_antes_de_llegar_el_dia_no_se_vuelve_a_pagar(self):
        factura, venta = self.pago_a_futuro()
        factura._get_reconciled_payments().action_cancel()
        self.avanzar('2030-03-21 15:00:00')
        self.Venta._barrido()
        self.assertEqual(self.neto(venta), 0, 'sin pago no hay comisión, llegue o no el día')
        self.assertFalse(venta.cobrada)
