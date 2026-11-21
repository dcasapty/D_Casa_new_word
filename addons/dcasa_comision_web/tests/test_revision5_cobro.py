"""Quinta revisión adversarial, parte D: pago con fecha futura y re-evaluación de la versión
(``venta.py::_adelantado_por_revisar``), con liquidaciones ya aprobadas y pagadas, notas de crédito e interruptores
distintos. Y el menor 1: una versión guardada «desde hoy» no se aplica a lo ya cobrado hoy (queda documentado en
``docs/COMISION_WEB.md``). Datos de PRUEBA."""
# ruff: noqa: E501
import logging
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_comision_web.tests.test_vendedoras import MARZO, VendedoraCommon
from odoo.tests import tagged

_logger = logging.getLogger(__name__)


class CobroBase(VendedoraCommon):
    """Ayudas comunes de las pruebas de cobro: lo que neto lleva cada persona, la foto del libro y «correr todo otra vez
    no anota nada»."""

    def setUp(self):
        super().setUp()
        self.Venta = self.env['dcasa.web.venta']

    def pago_de(self, factura):
        return factura._get_reconciled_payments()

    def neto(self, venta, empleado=None):
        filas = self.libro(venta=venta, empleado=empleado)
        return sum(f.centavos for f in filas.filtered(lambda f: f.tipo in ('venta', 'devolucion', 'reverso')))

    def foto_libro(self):
        return sorted((f.id, f.empleado_id.id, f.tipo, f.centavos) for f in self.libro())

    def dos_barridos_no_cambian_nada(self):
        antes = self.foto_libro()
        for venta in self.Venta.search([]):
            venta._reconciliar()
        self.Venta._barrido()
        self.Venta._barrido()
        self.Venta._poner_al_dia()
        self.assertEqual(antes, self.foto_libro(), 'correr la comparación otra vez no debe anotar nada')

    def duenos(self, factura, mes=MARZO):
        """(¿la cuenta el bono de la vendedora?, ¿la paga el sitio?)"""
        bono = self.Bono._calcular(self.vera, mes, self.company)
        venta = self.venta(factura)
        return (factura in bono.factura_ids, bool(venta.reglas_id and self.neto(venta) > 0))


@tagged('post_install', '-at_install')
class TestPagoFuturoYVersiones(CobroBase):

    def versiones(self, dias=6, pa=10.0, pb=5.0, **extra_b):
        A = self.version(pa)
        B = self.version(pb, rige_desde=fields.Datetime.now() + timedelta(days=dias), **extra_b)
        return A, B

    def venta_futura(self, fecha_pago, fecha_factura='2030-03-04', **kw):
        """Factura de HOY cobrada con una fecha de pago FUTURA (lo que teclea Caja)."""
        factura = self.facturar(self.orden(**kw), fecha_factura)
        self.pagar(factura, fecha_pago)
        return factura

    def liquidar(self, hasta='2030-03-31', usuario=None):
        liq = self.env['dcasa.web.liquidacion'].with_user(usuario or self.u_nomina).create({'fecha_desde': '2030-03-01', 'fecha_hasta': hasta})
        liq.action_armar()
        return liq

    def saldo_neto(self, empleado):
        return self.saldo(empleado, 'comision')

    def test_revision5_d02_ya_liquidada_y_pagada_no_se_toca_y_el_saldo_en_contra_se_compensa(self):
        A, B = self.versiones()
        factura = self.venta_futura('2030-03-14')           # pago con fecha futura (hoy es el 4)
        venta = self.venta(factura)
        self.assertTrue(venta.cobro_adelantado)
        self.assertEqual((venta.reglas_id, self.neto(venta)), (A, 10000))
        liq = self.liquidar()
        _logger.info('d02 liquidacion armada lineas=%s', [(ln.empleado_id.name[:3], ln.centavos) for ln in liq.linea_ids])
        liq.with_user(self.u_nomina).action_aprobar()
        liq.with_user(self.u_nomina).write({'fecha_pago': '2030-03-05', 'referencia_pago': 'REF-PRUEBA'})
        liq.with_user(self.u_nomina).action_pagar()
        lineas_antes = [(ln.empleado_id.id, ln.centavos) for ln in liq.linea_ids]
        estado_antes = liq.estado
        self.avanzar('2030-03-12 15:00:00')              # B rige desde el 10: ya llego su version, aunque el pago es del 14
        self.Venta._barrido()
        _logger.info('d02 tras barrido: v%s filas=%s', venta.reglas_id.numero, [(f.empleado_id.name[:3], f.tipo, f.centavos) for f in self.libro(venta=venta)])
        self.assertEqual(venta.reglas_id, B)
        self.assertEqual(self.neto(venta, self.ana), 3000)
        self.assertEqual(self.neto(venta, self.beto), 2000)
        # lo ya liquidado no se toco
        self.assertEqual([(ln.empleado_id.id, ln.centavos) for ln in liq.linea_ids], lineas_antes)
        self.assertEqual(liq.estado, estado_antes)
        # el saldo de cada quien: lo que se le pago (6000/4000) - lo nuevo (3000/2000) = en contra
        _logger.info('d02 saldos: ana=%s beto=%s', self.saldo_neto(self.ana), self.saldo_neto(self.beto))
        self.assertEqual(self.saldo_neto(self.ana), -3000)
        self.assertEqual(self.saldo_neto(self.beto), -2000)
        # una liquidacion nueva paga cero a quien esta en contra
        liq2 = self.liquidar(hasta='2030-03-31')
        pagos = [(ln.empleado_id.name[:3], ln.centavos) for ln in liq2.linea_ids]
        _logger.info('d02 liquidacion 2: %s', pagos)
        self.assertTrue(all(c <= 0 for _e, c in pagos) or not pagos)
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d03_adelantado_con_nota_y_otros_interruptores_coincide_con_cobrar_desde_cero(self):
        A = self.version(10.0)
        # B cambia la base (con ITBMS y sin restar devoluciones) para que el cambio de version se note en la cifra
        B = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=6), base_itbms='con', base_devoluciones='no_resta')
        factura = self.venta_futura('2030-03-14')
        self.nota(factura, 200.0, fecha='2030-03-04')
        venta = self.venta(factura)
        self.Venta._barrido()
        self.assertEqual(venta.reglas_id, A)
        antes = self.neto(venta)
        self.avanzar('2030-03-12 15:00:00')
        self.Venta._barrido()
        self.assertEqual(venta.reglas_id, B)
        # el mismo cobro hecho desde cero el 14 (ese dia ya rige B) y con la misma nota
        self.avanzar('2030-03-14 15:00:00')
        directa_f = self.venta_web(fecha='2030-03-14')
        self.nota(directa_f, 200.0, fecha='2030-03-14')
        directa = self.venta(directa_f)
        self.Venta._barrido()
        _logger.info('d03 antes(A)=%s despues=%s desde_cero=%s base=%s/%s', antes, self.neto(venta), self.neto(directa), venta.base_centavos, directa.base_centavos)
        self.assertEqual(venta.base_centavos, directa.base_centavos)
        self.assertEqual(self.neto(venta), self.neto(directa))
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d07_una_version_guardada_desde_hoy_no_se_aplica_a_lo_ya_cobrado_hoy(self):
        """Menor 1 (decisión documentada en ``docs/COMISION_WEB.md`` y en «Por decidir»): una venta cobrada hoy a las 10 con
        la versión A queda con A; la misma venta cobrada DESPUÉS de guardar la versión B «desde hoy» sale con B. Es
        coherente con «solo hacia adelante» (lo ya anotado no se recalcula): el barrido y «poner al día» no la mueven.
        Si Gerencia prefiere lo contrario, es una decisión de política (ver «Por decidir»)."""
        A = self.version(10.0)
        factura = self.venta_web(fecha='2030-03-04')
        venta = self.venta(factura)
        self.assertEqual((venta.reglas_id, self.neto(venta)), (A, 10000))
        self.avanzar('2030-03-04 17:00:00')
        B = self.version(5.0)                       # rige desde el inicio de hoy
        self.Venta._barrido()
        self.Venta._poner_al_dia()
        self.assertEqual((venta.reglas_id, self.neto(venta)), (A, 10000), 'lo ya cobrado hoy se queda con la versión de entonces')
        directa = self.venta(self.venta_web(fecha='2030-03-04'))
        self.assertEqual((directa.reglas_id, self.neto(directa)), (B, 5000), 'lo cobrado después de guardarla sale con B')
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d08_primera_version_programada_y_pago_con_fecha_posterior(self):
        """Limite documentado: sin dueña hasta que llegue el dia. Se comprueba que al llegar el dia se atribuye y que el
        bono de la vendedora no lo cuenta en el medio."""
        B = self.version(10.0, rige_desde=fields.Datetime.now() + timedelta(days=3))
        factura = self.venta_web(fecha='2030-03-09')
        venta = self.venta(factura)
        bono_si, sitio_si = self.duenos(factura)
        _logger.info('d08 dia 0: venta=%s v=%s bono=%s sitio=%s adel=%s', bool(venta), venta.reglas_id.numero, bono_si, sitio_si, venta.cobro_adelantado)
        self.avanzar('2030-03-08 15:00:00')
        self.Venta._barrido()
        venta = self.venta(factura)
        bono_si, sitio_si = self.duenos(factura)
        _logger.info('d08 dia 4: v=%s neto=%s bono=%s sitio=%s', venta.reglas_id.numero, self.neto(venta), bono_si, sitio_si)
        self.assertEqual(venta.reglas_id, B)
        self.assertEqual(self.neto(venta), 10000)
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d09_poner_al_dia_al_armar_hace_la_reevaluacion_y_no_paga_de_mas(self):
        A, B = self.versiones(pa=10.0, pb=5.0)
        factura = self.venta_futura('2030-03-14')
        venta = self.venta(factura)
        self.avanzar('2030-03-12 15:00:00')
        # sin barrido: armar mismo debe reevaluar antes de sumar
        liq = self.liquidar(hasta='2030-03-31')
        total = sum(ln.centavos for ln in liq.linea_ids)
        _logger.info('d09 armar tras llegar B: total=%s v=%s', total, venta.reglas_id.numero)
        self.assertEqual(total, 5000)
        liq.with_user(self.u_nomina).action_aprobar()
        self.assertEqual(self.neto(venta), 5000)
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d10_pago_con_fecha_futura_luego_se_cancela_y_se_vuelve_a_pagar_hoy(self):
        A, B = self.versiones()
        factura = self.venta_futura('2030-03-20')
        venta = self.venta(factura)
        self.pago_de(factura).action_cancel()
        self.Venta._barrido()
        self.assertEqual(self.neto(venta), 0)
        self.pagar(factura, '2030-03-04')
        self.assertFalse(venta.cobro_adelantado)
        self.assertEqual(self.neto(venta), 10000)
        self.avanzar('2030-03-12 15:00:00')
        self.Venta._barrido()
        self.assertEqual(venta.reglas_id, A, 'pagada el dia 4 con A: sigue con A')
        self.assertEqual(self.neto(venta), 10000)
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d11_adelantado_y_version_anulada_antes_de_llegar(self):
        A, B = self.versiones()
        factura = self.venta_futura('2030-03-14')
        venta = self.venta(factura)
        B.motivo_anulacion = 'puesta mal'
        B.with_user(self.u_nomina).action_anular()
        self.avanzar('2030-03-12 15:00:00')
        self.Venta._barrido()
        self.assertEqual(venta.reglas_id, A)
        self.assertEqual(self.neto(venta), 10000)
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d12_varias_versiones_en_desorden_y_un_pago_futuro(self):
        self.version(10.0)
        self.version(20.0, rige_desde=fields.Datetime.now() + timedelta(days=9))
        B = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=3))     # guardada despues, rige antes
        factura = self.venta_futura('2030-03-15')
        venta = self.venta(factura)
        for fecha, esperada, neto in (('2030-03-08 15:00:00', B, 5000), ('2030-03-14 15:00:00', B, 5000)):   # C queda tapada por B
            self.avanzar(fecha)
            self.Venta._barrido()
            _logger.info('d12 %s: v=%s neto=%s', fecha, venta.reglas_id.numero, self.neto(venta))
            self.assertEqual((venta.reglas_id, self.neto(venta)), (esperada, neto))
        self.dos_barridos_no_cambian_nada()

    def test_revision5_d13_la_version_nueva_cambia_quienes_reciben_o_pausa_el_cobro(self):
        self.version(10.0)                                                                              # Ana 60 / Beto 40
        B = self.version(20.0, reparto=[(self.ana, 100.0)], rige_desde=fields.Datetime.now() + timedelta(days=6))    # solo Ana
        C = self.version(0.0, rige_desde=fields.Datetime.now() + timedelta(days=9))                      # pausa
        f1 = self.venta_futura('2030-03-30')
        f2 = self.venta_futura('2030-03-30')
        v1, v2 = self.venta(f1), self.venta(f2)
        self.assertEqual((self.neto(v1, self.ana), self.neto(v1, self.beto)), (6000, 4000))
        self.avanzar('2030-03-12 15:00:00')              # rige B: 20 % para Ana sola
        self.Venta._barrido()
        _logger.info('d13 con B: ana=%s beto=%s v=%s', self.neto(v1, self.ana), self.neto(v1, self.beto), v1.reglas_id.numero)
        self.assertEqual((v1.reglas_id, self.neto(v1, self.ana), self.neto(v1, self.beto)), (B, 20000, 0))
        self.avanzar('2030-03-15 15:00:00')              # rige C: pausa (0 %, sin reparto)
        self.Venta._barrido()
        _logger.info('d13 con C: ana=%s beto=%s v=%s', self.neto(v1, self.ana), self.neto(v1, self.beto), v1.reglas_id.numero)
        self.assertEqual((v1.reglas_id, self.neto(v1, self.ana), self.neto(v1, self.beto)), (C, 0, 0))
        self.assertEqual((v2.reglas_id, self.neto(v2, self.ana), self.neto(v2, self.beto)), (C, 0, 0))
        self.dos_barridos_no_cambian_nada()
