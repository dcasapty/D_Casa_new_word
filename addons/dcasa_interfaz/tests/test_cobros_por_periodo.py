"""Lo cobrado por forma de pago del día, la semana, la quincena o el mes (pedido de la dueña, 2026-11-19: una sola
tarjeta «Cobrado por forma de pago» arriba del detalle del día, con un selector Día · Semana · Quincena · Mes).

* El periodo es el que contiene el día elegido: la semana va de lunes a domingo (si cruza de mes o de año, se cuenta
  completa); la quincena, del 1 al 15 o del 16 al fin del mes (febrero bisiesto y meses de 30 y 31 días incluidos); el
  mes es el del día.
* Los días que todavía no llegan no suman: el periodo en curso cuenta hasta hoy (hora de Panamá), aunque haya un cobro
  fechado después.
* Es la cuenta de la «Caja de hoy» (``_dominio_de_cobros``): el día, igual que ``ventas_del_dia``; el mes, igual que
  ``por_dia``.
* Solo Gerencia y administradores, y la entrada se valida antes de leer: periodo desconocido, fecha mal escrita, día
  futuro o de hace más de 24 meses.

Fechas fijas de 2024 a 2026 (``hoy`` se pasa a mano): nada depende del reloj real.
"""
from datetime import date, time
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_por_dia import PorDiaCommon, en_panama


@tagged('post_install', '-at_install')
class TestCobrosPorPeriodo(PorDiaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.efectivo = cls.env['account.journal'].create({'name': 'Efectivo por periodo', 'type': 'cash',
                                                          'code': 'EFPP'})

    def cobro(self, monto, dia, diario=None):
        """Un cobro a un cliente (sin factura: un anticipo cuenta igual en la caja), confirmado, con su fecha."""
        pago = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': monto,
            'date': dia, 'journal_id': (diario or self.banco).id})
        pago.action_post()
        return pago

    def periodo(self, dia, periodo, hoy):
        return self.ger._cobros_del_periodo(dia, periodo, hoy)

    @staticmethod
    def formas(cobros):
        return {fila['forma']: (fila['monto'], fila['cuantos']) for fila in cobros['filas']}

    # ------------------------------------------------------------------
    # Las fechas de cada periodo (sin base de datos de cobros)
    # ------------------------------------------------------------------

    def test_el_rango_de_cada_periodo(self):
        rango = self.ger._rango_de_cobros
        casos = [
            # (día, periodo, desde, hasta)
            (date(2025, 7, 10), 'dia', date(2025, 7, 10), date(2025, 7, 10)),
            # Semana: lunes a domingo. Un jueves, un lunes (empieza ese día) y un domingo (termina ese día).
            (date(2025, 7, 10), 'semana', date(2025, 7, 7), date(2025, 7, 13)),
            (date(2025, 7, 7), 'semana', date(2025, 7, 7), date(2025, 7, 13)),
            (date(2025, 7, 13), 'semana', date(2025, 7, 7), date(2025, 7, 13)),
            # La semana que cruza de mes se cuenta completa desde cualquiera de sus dos lados.
            (date(2025, 6, 30), 'semana', date(2025, 6, 30), date(2025, 7, 6)),
            (date(2025, 7, 3), 'semana', date(2025, 6, 30), date(2025, 7, 6)),
            # ...y la que cruza de año.
            (date(2025, 12, 31), 'semana', date(2025, 12, 29), date(2026, 1, 4)),
            (date(2026, 1, 1), 'semana', date(2025, 12, 29), date(2026, 1, 4)),
            (date(2026, 11, 19), 'semana', date(2026, 11, 16), date(2026, 11, 22)),
            # Quincena: del 1 al 15 y del 16 al fin del mes (el día 15 es de la primera y el 16, de la segunda).
            (date(2025, 7, 1), 'quincena', date(2025, 7, 1), date(2025, 7, 15)),
            (date(2025, 7, 15), 'quincena', date(2025, 7, 1), date(2025, 7, 15)),
            (date(2025, 7, 16), 'quincena', date(2025, 7, 16), date(2025, 7, 31)),   # mes de 31 días
            (date(2025, 12, 31), 'quincena', date(2025, 12, 16), date(2025, 12, 31)),
            (date(2025, 4, 16), 'quincena', date(2025, 4, 16), date(2025, 4, 30)),   # mes de 30 días
            (date(2025, 4, 30), 'quincena', date(2025, 4, 16), date(2025, 4, 30)),
            (date(2025, 2, 20), 'quincena', date(2025, 2, 16), date(2025, 2, 28)),   # febrero de 28 días
            (date(2024, 2, 15), 'quincena', date(2024, 2, 1), date(2024, 2, 15)),    # febrero bisiesto
            (date(2024, 2, 16), 'quincena', date(2024, 2, 16), date(2024, 2, 29)),
            (date(2024, 2, 29), 'quincena', date(2024, 2, 16), date(2024, 2, 29)),
            # Mes: el del día.
            (date(2025, 7, 10), 'mes', date(2025, 7, 1), date(2025, 7, 31)),
            (date(2024, 2, 29), 'mes', date(2024, 2, 1), date(2024, 2, 29)),
            (date(2025, 2, 1), 'mes', date(2025, 2, 1), date(2025, 2, 28)),
            (date(2025, 12, 31), 'mes', date(2025, 12, 1), date(2025, 12, 31)),
        ]
        for dia, periodo, desde, hasta in casos:
            with self.subTest(dia=str(dia), periodo=periodo):
                self.assertEqual(rango(dia, periodo), (desde, hasta))

    def test_el_titulo_dice_que_periodo_es(self):
        """«Cobrado · semana del 16 al 22 de noviembre»: con claridad, y con el año si no es el de hoy."""
        hoy = date(2026, 11, 19)
        titulo = lambda dia, periodo, hoy=hoy: self.periodo(dia, periodo, hoy)['titulo']  # noqa: E731
        self.assertEqual(titulo(hoy, 'dia'), 'Cobrado · hoy, jueves 19 de noviembre')
        self.assertEqual(titulo(date(2026, 11, 18), 'dia'), 'Cobrado · miércoles 18 de noviembre')
        self.assertEqual(titulo(hoy, 'semana'), 'Cobrado · semana del 16 al 22 de noviembre')
        self.assertEqual(titulo(date(2026, 11, 2), 'semana'), 'Cobrado · semana del 2 al 8 de noviembre')
        self.assertEqual(titulo(date(2026, 11, 1), 'semana'),
                         'Cobrado · semana del 26 de octubre al 1 de noviembre', 'la semana que cruza de mes')
        self.assertEqual(titulo(hoy, 'quincena'), 'Cobrado · quincena del 16 al 30 de noviembre')
        self.assertEqual(titulo(date(2026, 11, 15), 'quincena'), 'Cobrado · quincena del 1 al 15 de noviembre')
        self.assertEqual(titulo(hoy, 'mes'), 'Cobrado · mes de noviembre')
        # Otro año: el año va, y la semana que cruza de año los dice los dos.
        self.assertEqual(titulo(date(2025, 11, 19), 'mes'), 'Cobrado · mes de noviembre de 2025')
        self.assertEqual(titulo(date(2025, 11, 19), 'dia'), 'Cobrado · miércoles 19 de noviembre de 2025')
        self.assertEqual(titulo(date(2025, 11, 19), 'semana'),
                         'Cobrado · semana del 17 al 23 de noviembre de 2025')
        self.assertEqual(titulo(date(2025, 12, 31), 'semana', date(2026, 1, 20)),
                         'Cobrado · semana del 29 de diciembre de 2025 al 4 de enero de 2026')

    # ------------------------------------------------------------------
    # Lo cobrado
    # ------------------------------------------------------------------

    def datos_de_julio(self):
        """Junio y julio de 2025, con hoy = jueves 10 de julio. El 12 (sábado) hay un cobro fechado en el futuro."""
        self.hoy = date(2025, 7, 10)
        cobros = {
            (6, 15): self.cobro(100.0, date(2025, 6, 15)),                        # domingo: 1.ª quincena de junio
            (6, 16): self.cobro(200.0, date(2025, 6, 16), self.efectivo),         # lunes: 2.ª quincena de junio
            (6, 29): self.cobro(300.0, date(2025, 6, 29)),                        # domingo
            (6, 30): self.cobro(400.0, date(2025, 6, 30), self.efectivo),         # lunes: semana que cruza de mes
            (7, 1): self.cobro(500.0, date(2025, 7, 1)),
            (7, 6): self.cobro(600.0, date(2025, 7, 6), self.efectivo),           # domingo: cierra esa semana
            (7, 7): self.cobro(700.0, date(2025, 7, 7)),                          # lunes
            (7, 10): self.cobro(800.0, date(2025, 7, 10), self.efectivo),         # hoy
            (7, 12): self.cobro(900.0, date(2025, 7, 12)),                        # sábado, todavía no llega
        }
        return cobros

    def test_cada_periodo_suma_lo_suyo(self):
        self.datos_de_julio()
        hoy = self.hoy

        dia = self.periodo(hoy, 'dia', hoy)
        self.assertEqual((dia['desde'], dia['hasta'], dia['contado_hasta']), ('2025-07-10',) * 3)
        self.assertEqual(self.formas(dia['cobros']), {self.efectivo.display_name: (800.0, 1)})
        self.assertEqual(dia['cobros']['total'], 800.0)
        self.assertFalse(dia['en_curso'], 'el día de hoy no tiene días que falten')
        self.assertEqual(dia['nota'], '')

        # La semana que cruza de mes: del lunes 30 de junio al domingo 6 de julio, completa y cerrada.
        cruza = self.periodo(date(2025, 7, 3), 'semana', hoy)
        self.assertEqual((cruza['desde'], cruza['hasta'], cruza['contado_hasta']), ('2025-06-30', '2025-07-06',
                                                                                     '2025-07-06'))
        self.assertEqual(cruza['cobros']['total'], 400.0 + 500.0 + 600.0)
        self.assertEqual(self.formas(cruza['cobros']), {self.efectivo.display_name: (1000.0, 2),
                                                        self.banco.display_name: (500.0, 1)})
        self.assertFalse(cruza['en_curso'])
        # Desde el otro lado del mes, la misma semana.
        self.assertEqual(self.periodo(date(2025, 6, 30), 'semana', hoy)['cobros']['total'], 1500.0)

        # La semana en curso cuenta hasta hoy: el cobro del sábado 12 no suma.
        en_curso = self.periodo(hoy, 'semana', hoy)
        self.assertEqual((en_curso['desde'], en_curso['hasta'], en_curso['contado_hasta']),
                         ('2025-07-07', '2025-07-13', '2025-07-10'))
        self.assertEqual(en_curso['cobros']['total'], 700.0 + 800.0)
        self.assertTrue(en_curso['en_curso'])
        self.assertIn('hoy', en_curso['nota'])
        self.assertIn('jueves 10 de julio', en_curso['nota'])

        # Quincenas.
        primera = self.periodo(hoy, 'quincena', hoy)
        self.assertEqual((primera['desde'], primera['hasta'], primera['contado_hasta']),
                         ('2025-07-01', '2025-07-15', '2025-07-10'))
        self.assertEqual(primera['cobros']['total'], 500.0 + 600.0 + 700.0 + 800.0)
        self.assertEqual(self.periodo(date(2025, 6, 15), 'quincena', hoy)['cobros']['total'], 100.0,
                         'el 15 es de la primera quincena')
        self.assertEqual(self.periodo(date(2025, 6, 16), 'quincena', hoy)['cobros']['total'], 200.0 + 300.0 + 400.0,
                         'el 16 abre la segunda')

        # El mes en curso cuenta hasta hoy; el mes cerrado, completo.
        julio = self.periodo(hoy, 'mes', hoy)
        self.assertEqual(julio['cobros']['total'], 500.0 + 600.0 + 700.0 + 800.0)
        self.assertEqual(self.formas(julio['cobros']), {self.efectivo.display_name: (1400.0, 2),
                                                        self.banco.display_name: (1200.0, 2)})
        self.assertEqual([fila['forma'] for fila in julio['cobros']['filas']],
                         [self.efectivo.display_name, self.banco.display_name], 'de más a menos dinero')
        junio = self.periodo(date(2025, 6, 20), 'mes', hoy)
        self.assertEqual(junio['cobros']['total'], 100.0 + 200.0 + 300.0 + 400.0)
        self.assertFalse(junio['en_curso'])
        # Las dos quincenas de un mes cerrado suman el mes.
        self.assertEqual(self.periodo(date(2025, 6, 15), 'quincena', hoy)['cobros']['total']
                         + self.periodo(date(2025, 6, 16), 'quincena', hoy)['cobros']['total'],
                         junio['cobros']['total'])

    def test_es_la_cuenta_de_la_caja_de_hoy_y_la_de_las_pantallas_de_siempre(self):
        self.datos_de_julio()
        hoy = self.hoy
        self.cobro(55.0, date(2025, 7, 10))
        # Un pago a un cliente (dinero que sale) y un cobro en borrador no entran a la caja.
        self.env['account.payment'].create({
            'payment_type': 'outbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 50.0,
            'date': date(2025, 7, 10), 'journal_id': self.efectivo.id}).action_post()
        self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 70.0,
            'date': date(2025, 7, 10), 'journal_id': self.efectivo.id})
        dia = self.periodo(hoy, 'dia', hoy)['cobros']
        self.assertEqual(dia['total'], 855.0)
        self.assertEqual(dia['total'], self.ger._cobrado(hoy, hoy), 'lo mismo que «Cobrado hoy» del Inicio')
        self.assertEqual(self.formas(dia), self.formas(self.ger._del_dia(hoy, 'facturado', None, hoy)['cobros']))
        semana = self.periodo(hoy, 'semana', hoy)['cobros']
        self.assertEqual(semana['total'], self.ger._cobrado(date(2025, 7, 7), hoy))
        junio = self.periodo(date(2025, 6, 20), 'mes', hoy)['cobros']
        esperado = self.ger._por_dia('2025-06', 'facturado', None, en_panama(hoy, time(11, 0)))['cobros']
        self.assertEqual((self.formas(junio), junio['total'], junio['cuantos']),
                         (self.formas(esperado), esperado['total'], esperado['cuantos']))

    def test_cada_ficha_abre_los_cobros_de_ese_periodo_y_ese_diario(self):
        cobros = self.datos_de_julio()
        hoy = self.hoy
        semana = self.periodo(hoy, 'semana', hoy)
        Pago = self.env['account.payment']
        self.assertEqual(Pago.search(semana['cobros']['accion']['domain']), cobros[(7, 7)] | cobros[(7, 10)],
                         'el total abre los cobros contados, no el del sábado 12')
        efectivo = next(f for f in semana['cobros']['filas'] if f['forma'] == self.efectivo.display_name)
        self.assertEqual(efectivo['accion']['res_model'], 'account.payment')
        self.assertEqual(Pago.search(efectivo['accion']['domain']), cobros[(7, 10)])
        self.assertIn('semana del 7 al 13 de julio', efectivo['accion']['name'])
        self.assertIn(self.efectivo.display_name, efectivo['accion']['name'])

    def test_un_dia_que_no_llego_no_suma_y_el_dia_de_hoy_cuenta(self):
        """Hoy es lunes: la semana es solo de hoy hacia atrás (nada hacia adelante). Hoy es domingo: cierra hoy."""
        lunes, domingo = date(2025, 7, 7), date(2025, 7, 13)
        self.cobro(10.0, lunes)
        self.cobro(20.0, date(2025, 7, 8))
        semana = self.periodo(lunes, 'semana', lunes)
        self.assertEqual((semana['contado_hasta'], semana['en_curso']), ('2025-07-07', True))
        self.assertEqual(semana['cobros']['total'], 10.0, 'lo cobrado el martes todavía no cuenta')
        cierre = self.periodo(domingo, 'semana', domingo)
        self.assertEqual((cierre['contado_hasta'], cierre['en_curso'], cierre['nota']), ('2025-07-13', False, ''))
        self.assertEqual(cierre['cobros']['total'], 30.0)

    def test_un_mes_sin_cobros(self):
        datos = self.periodo(date(2025, 3, 14), 'mes', date(2025, 7, 10))
        self.assertEqual(datos['cobros']['filas'], [])
        self.assertEqual((datos['cobros']['total'], datos['cobros']['cuantos']), (0.0, 0))
        self.assertEqual(datos['cobros']['accion']['res_model'], 'account.payment')
        self.assertEqual(datos['titulo'], 'Cobrado · mes de marzo')

    def test_los_cruces_de_anio_y_el_febrero_bisiesto(self):
        # Diciembre de 2025 y enero de 2026, con hoy = 20 de enero.
        hoy = date(2026, 1, 20)
        self.cobro(10.0, date(2025, 12, 30))
        self.cobro(20.0, date(2026, 1, 2), self.efectivo)
        self.cobro(5.0, date(2025, 12, 28))                                    # domingo: la semana anterior
        self.cobro(7.0, date(2026, 1, 5))                                      # lunes: la semana siguiente
        self.cobro(3.0, date(2025, 12, 10))                                    # 1.ª quincena de diciembre
        for dia in (date(2025, 12, 31), date(2026, 1, 1), date(2025, 12, 29), date(2026, 1, 4)):
            with self.subTest(dia=str(dia)):
                semana = self.periodo(dia, 'semana', hoy)
                self.assertEqual((semana['desde'], semana['hasta']), ('2025-12-29', '2026-01-04'))
                self.assertEqual(semana['cobros']['total'], 30.0)
        self.assertEqual(self.periodo(date(2025, 12, 31), 'mes', hoy)['cobros']['total'], 18.0)
        self.assertEqual(self.periodo(date(2025, 12, 31), 'quincena', hoy)['cobros']['total'], 15.0)
        self.assertEqual(self.periodo(date(2025, 12, 15), 'quincena', hoy)['cobros']['total'], 3.0)
        self.assertEqual(self.periodo(date(2026, 1, 2), 'mes', hoy)['cobros']['total'], 27.0)
        # Febrero de 2024 (bisiesto), con hoy = 10 de marzo.
        hoy = date(2024, 3, 10)
        self.cobro(1.0, date(2024, 2, 15))
        self.cobro(2.0, date(2024, 2, 16))
        self.cobro(4.0, date(2024, 2, 29))
        self.cobro(8.0, date(2024, 3, 1))
        self.assertEqual(self.periodo(date(2024, 2, 15), 'quincena', hoy)['cobros']['total'], 1.0)
        self.assertEqual(self.periodo(date(2024, 2, 16), 'quincena', hoy)['cobros']['total'], 6.0)
        self.assertEqual(self.periodo(date(2024, 2, 29), 'quincena', hoy)['cobros']['total'], 6.0)
        self.assertEqual(self.periodo(date(2024, 2, 29), 'mes', hoy)['cobros']['total'], 7.0,
                         'el 1 de marzo es de marzo')
        self.assertEqual(self.periodo(date(2024, 3, 1), 'mes', hoy)['cobros']['total'], 8.0)

    # ------------------------------------------------------------------
    # La conexión pública: permiso y entrada
    # ------------------------------------------------------------------

    def con_reloj(self, hoy=date(2025, 7, 10)):
        """El reloj de Panamá congelado en ``hoy`` (las 11:00), para la conexión pública."""
        ahora = en_panama(hoy, time(11, 0))
        return patch.object(self.env.registry['dcasa.tablero'], '_ahora_en_panama', lambda _self: ahora)

    def test_la_conexion_publica_usa_el_reloj_de_panama(self):
        self.datos_de_julio()
        with self.con_reloj():
            datos = self.ger.cobros_del_periodo('2025-07-10', 'semana')
            self.assertEqual((datos['periodo'], datos['dia'], datos['desde'], datos['contado_hasta']),
                             ('semana', '2025-07-10', '2025-07-07', '2025-07-10'))
            self.assertEqual(datos['cobros']['total'], 1500.0)
            self.assertEqual(self.ger.cobros_del_periodo('2025-07-10')['periodo'], 'dia', 'sin periodo, el día')
            self.assertEqual(self.ger.cobros_del_periodo('2025-07-10', '')['periodo'], 'dia')
            # El día 10 de julio de 2025 es hoy: pasa; el 11 todavía no llega.
            with self.assertRaises(UserError) as error:
                self.ger.cobros_del_periodo('2025-07-11', 'mes')
            self.assertIn('todavía no llega', str(error.exception))

    def test_valida_la_entrada_antes_de_leer(self):
        with self.con_reloj():
            for periodo in ('siglo', 'Semana', 'dia ', 'DIA', 7, ['mes'], {'mes': 1}):
                with self.subTest(periodo=periodo), self.assertRaises(UserError) as error:
                    self.ger.cobros_del_periodo('2025-07-10', periodo)
                if isinstance(periodo, str):
                    self.assertIn('Semana', str(error.exception), 'el error dice cuáles hay')
            for dia in (None, False, '', 'no es fecha', '2025-13-40', '2025-02-30', '10/07/2025', 20250710, [], {}):
                with self.subTest(dia=dia), self.assertRaises(UserError):
                    self.ger.cobros_del_periodo(dia, 'dia')
            for dia in ('2025-07-11', '3000-01-01'):                           # no llegó
                with self.subTest(dia=dia), self.assertRaises(UserError):
                    self.ger.cobros_del_periodo(dia, 'dia')
            # Hasta hace 24 meses: el primer día de julio de 2023 pasa, el último de junio de 2023 no.
            self.assertEqual(self.ger.cobros_del_periodo('2023-07-01', 'mes')['desde'], '2023-07-01')
            with self.assertRaises(UserError):
                self.ger.cobros_del_periodo('2023-06-30', 'mes')
            with self.assertRaises(UserError):
                self.ger.cobros_del_periodo('2000-01-01', 'dia')

    def test_solo_gerencia_y_administradores(self):
        self.datos_de_julio()
        with self.con_reloj():
            for usuario in (self.vendedora, self.otra):
                Tablero = self.env['dcasa.tablero'].with_user(usuario)
                with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                    Tablero.cobros_del_periodo('2025-07-10', 'dia')
                # El permiso se exige antes que la entrada: con datos malos tampoco se enteran de nada.
                with self.subTest(usuario=usuario.login, entrada='mala'), self.assertRaises(AccessError):
                    Tablero.cobros_del_periodo('no es fecha', 'siglo')
            self.assertEqual(self.ger.cobros_del_periodo('2025-07-10', 'dia')['cobros']['total'], 800.0)
            admin = self.env.ref('base.user_admin')
            self.assertEqual(
                self.env['dcasa.tablero'].with_user(admin).cobros_del_periodo('2025-07-10', 'dia')['periodo'], 'dia')

    def test_no_depende_de_la_hora_del_dia_ni_de_la_zona(self):
        """Pasadas las 7 p. m. de Panamá ya es el día siguiente en UTC: el día de hoy sigue siendo el de Panamá."""
        noche = en_panama(date(2025, 7, 10), time(23, 30))
        self.datos_de_julio()
        with patch.object(self.env.registry['dcasa.tablero'], '_ahora_en_panama', lambda _self: noche):
            datos = self.ger.cobros_del_periodo('2025-07-10', 'dia')
            self.assertEqual(datos['cobros']['total'], 800.0)
            self.assertIn('hoy, jueves 10 de julio', datos['titulo'])
            with self.assertRaises(UserError):
                self.ger.cobros_del_periodo('2025-07-11', 'dia')
