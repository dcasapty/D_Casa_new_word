"""Lo cobrado por forma de pago en «Por día» y «Estadísticas» (pedido de la dueña, 2026-11-02: «cuando se selecciona un
día, ese día no sale con qué métodos de pago se facturó» y «tampoco hay un dato certero de por mes cuánto se facturó
según cada método de pago»).

* Es la cuenta de la «Caja de hoy» para cualquier día: los cobros a clientes confirmados, por su fecha y su diario, con
  ITBMS. Un abono cuenta el día que se cobró.
* Un pago a un cliente (dinero que sale) o un cobro en borrador no cuentan.
* El mes es la suma de sus días y lo mismo que «Cobrado» del Inicio; no cambia con la base ni con la vendedora.
* Cada forma de pago abre sus cobros.

Fechas fijas de 2025 (``ahora`` se pasa a mano): nada depende del reloj real.
"""
from datetime import date, time

from odoo.tests import tagged

from .test_por_dia import PorDiaCommon, en_panama


@tagged('post_install', '-at_install')
class TestCobrosPorForma(PorDiaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.efectivo = cls.env['account.journal'].create({'name': 'Efectivo cobros por forma', 'type': 'cash',
                                                          'code': 'EFCF'})
        cls.ahora = en_panama(date(2025, 7, 10), time(11, 0))
        cls.hoy = cls.ahora.date()

    def setUp(self):
        super().setUp()
        # Junio de 2025: la primera venta se paga en dos (banco el 3, efectivo el 5); la segunda, en efectivo el 5.
        _o1, f1 = self.vender(date(2025, 6, 3), vendedor=self.vendedora)
        _o2, f2 = self.vender(date(2025, 6, 4), vendedor=self.otra)
        self.p1 = self.pagar(f1, 400.0, date(2025, 6, 3))
        self.p2 = self.pagar(f1, 600.0, date(2025, 6, 5), diario=self.efectivo)
        self.p3 = self.pagar(f2, 1000.0, date(2025, 6, 5), diario=self.efectivo)
        Pago = self.env['account.payment']
        # Ni el dinero que se le devuelve a un cliente ni un cobro en borrador entran a la caja.
        Pago.create({'payment_type': 'outbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
                     'amount': 50.0, 'date': date(2025, 6, 5), 'journal_id': self.efectivo.id}).action_post()
        self.borrador = Pago.create({'payment_type': 'inbound', 'partner_type': 'customer',
                                     'partner_id': self.cliente.id, 'amount': 70.0, 'date': date(2025, 6, 5),
                                     'journal_id': self.efectivo.id})

    def formas(self, cobros):
        return {fila['forma']: (fila['monto'], fila['cuantos']) for fila in cobros['filas']}

    def test_el_dia_dice_con_que_se_cobro(self):
        cinco = self.ger._del_dia(date(2025, 6, 5), 'facturado', None, self.hoy)['cobros']
        self.assertEqual(self.formas(cinco), {self.efectivo.display_name: (1600.0, 2)},
                         'el abono y la segunda venta, en efectivo; ni el pago a un cliente ni el borrador')
        self.assertEqual((cinco['total'], cinco['cuantos']), (1600.0, 2))
        tres = self.ger._del_dia(date(2025, 6, 3), 'facturado', None, self.hoy)['cobros']
        self.assertEqual(self.formas(tres), {self.banco.display_name: (400.0, 1)})
        cuatro = self.ger._del_dia(date(2025, 6, 4), 'facturado', None, self.hoy)['cobros']
        self.assertEqual((cuatro['filas'], cuatro['total']), ([], 0.0), 'el 4 se facturó, pero no se cobró')

    def test_el_mes_es_la_suma_de_sus_dias_y_el_cobrado_del_inicio(self):
        mes = self.ger._por_dia('2025-06', 'facturado', None, self.ahora)['cobros']
        self.assertEqual(self.formas(mes), {self.efectivo.display_name: (1600.0, 2),
                                            self.banco.display_name: (400.0, 1)})
        self.assertEqual([fila['forma'] for fila in mes['filas']],
                         [self.efectivo.display_name, self.banco.display_name], 'de más a menos dinero')
        self.assertEqual(mes['total'], 2000.0)
        self.assertEqual(mes['total'], self.ger._cobrado(date(2025, 6, 1), date(2025, 6, 30)),
                         'lo mismo que «Cobrado» del Inicio para esas fechas')

    def test_no_cambia_con_la_base_ni_con_la_vendedora(self):
        esperado = self.ger._por_dia('2025-06', 'facturado', None, self.ahora)['cobros']
        for base in ('confirmado', 'con_abonos', 'completadas'):
            for vendedor in (None, self.vendedora.id):
                with self.subTest(base=base, vendedor=vendedor):
                    mes = self.ger._por_dia('2025-06', base, vendedor, self.ahora)['cobros']
                    self.assertEqual((self.formas(mes), mes['total']), (self.formas(esperado), esperado['total']))

    def test_estadisticas_trae_lo_cobrado_del_periodo(self):
        datos = self.ger._estadisticas(date(2025, 6, 1), date(2025, 6, 30), 'Junio 2025', 'mes_pasado',
                                       'facturado', self.hoy)
        self.assertEqual(datos['cobros']['total'], 2000.0)
        self.assertEqual(self.formas(datos['cobros'])[self.banco.display_name], (400.0, 1))

    def test_cada_forma_abre_sus_cobros(self):
        mes = self.ger._por_dia('2025-06', 'facturado', None, self.ahora)['cobros']
        Pago = self.env['account.payment']
        efectivo = next(fila for fila in mes['filas'] if fila['forma'] == self.efectivo.display_name)
        self.assertEqual(efectivo['accion']['res_model'], 'account.payment')
        self.assertEqual(Pago.search(efectivo['accion']['domain']), self.p2 | self.p3)
        self.assertEqual(Pago.search(mes['accion']['domain']), self.p1 | self.p2 | self.p3)
        self.assertNotIn(self.borrador, Pago.search(mes['accion']['domain']))

    def test_dos_formas_con_el_mismo_nombre_no_se_juntan(self):
        """Dos diarios con el mismo nombre (p. ej. el «Efectivo» de dos empresas): dos fichas, cada una con su clave."""
        gemelo = self.env['account.journal'].create({'name': self.efectivo.name, 'type': 'cash', 'code': 'EFC2'})
        _o, factura = self.vender(date(2025, 6, 6), vendedor=self.vendedora)
        self.pagar(factura, 1000.0, date(2025, 6, 6), diario=gemelo)
        mes = self.ger._por_dia('2025-06', 'facturado', None, self.ahora)['cobros']
        mismas = [fila for fila in mes['filas'] if fila['forma'] == self.efectivo.display_name]
        self.assertEqual(sorted(fila['monto'] for fila in mismas), [1000.0, 1600.0])
        self.assertEqual(len({fila['clave'] for fila in mes['filas']}), len(mes['filas']))
