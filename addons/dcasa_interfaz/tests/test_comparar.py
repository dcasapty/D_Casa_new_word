"""«Comparar» del Inicio de Gerencia y el interruptor «Completadas» / «Con abonos» (2026-10-17).

Todo con fechas y horas fijas (``_comparar(..., ahora=...)`` y los ``create_date`` puestos a mano): nada depende del
reloj real. Las ventas de datos son de 2025 y, para no mezclarse con otras, casi todas se miden con el filtro de
vendedora.
"""
import json
from datetime import date, datetime, time

import pytz

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from .test_inicio_por_rol import ESPERAR_JS, VentasCommon, VentasMixin, crear_usuario

PANAMA = pytz.timezone('America/Panama')


@tagged('post_install', '-at_install')
class TestCompararFechas(TransactionCase):
    """Qué es A y qué es B en cada botón, sus etiquetas y las validaciones (sin datos)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tablero = cls.env['dcasa.tablero']

    def rangos(self, clave, hoy, **kw):
        return self.tablero._rangos_de_comparar(clave, hoy, **kw)

    def test_cada_boton_compara_lo_que_dice(self):
        hoy = date(2026, 10, 17)     # sábado
        self.assertEqual(hoy.weekday(), 5)
        esperado = {
            'ayer': ((hoy, hoy), (date(2026, 10, 16),) * 2),
            'dia_mes_pasado': ((hoy, hoy), (date(2026, 9, 17),) * 2),
            'semana_pasada': ((hoy, hoy), (date(2026, 10, 10),) * 2),
            'mes_a_la_fecha': ((date(2026, 10, 1), hoy), (date(2026, 9, 1), date(2026, 9, 17))),
            'mes': ((date(2026, 10, 1), hoy), (date(2026, 9, 1), date(2026, 9, 30))),
        }
        for clave, (a, b) in esperado.items():
            with self.subTest(clave):
                rangos = self.rangos(clave, hoy)
                self.assertEqual((rangos['a'], rangos['b']), (a, b))
        self.assertEqual(self.rangos('mes', hoy)['modo'], 'llevas')
        self.assertEqual(self.rangos('mes_a_la_fecha', hoy)['modo'], 'variacion')
        chips = self.tablero._chips_de_comparar(hoy)
        self.assertEqual([c['etiqueta'] for c in chips], ['Ayer', '17 sep', 'Sáb. 10 oct', '1–17 sep', 'Mes', 'A vs B'])
        self.assertEqual([c['clave'] for c in chips],
                         ['ayer', 'dia_mes_pasado', 'semana_pasada', 'mes_a_la_fecha', 'mes', 'rango'])

    def test_el_31_y_febrero_tambien_en_anio_bisiesto(self):
        # El 31 de octubre contra el último día de septiembre (30); el mes, del 1 al 30 (más corto: por día).
        fin = self.rangos('dia_mes_pasado', date(2026, 10, 31))
        self.assertEqual(fin['b'], (date(2026, 9, 30),) * 2)
        mes = self.rangos('mes_a_la_fecha', date(2026, 10, 31))
        self.assertEqual(mes['b'], (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(mes['modo'], 'por_dia', '31 días contra 30: el porcentaje es por día')
        # El 29, 30 y 31 de marzo contra el último de febrero: 28 en 2027, 29 en 2028 (bisiesto).
        for hoy, ultimo in ((date(2027, 3, 29), date(2027, 2, 28)), (date(2027, 3, 30), date(2027, 2, 28)),
                            (date(2027, 3, 31), date(2027, 2, 28)), (date(2028, 3, 30), date(2028, 2, 29)),
                            (date(2028, 3, 29), date(2028, 2, 29))):
            with self.subTest(hoy=hoy):
                self.assertEqual(self.rangos('dia_mes_pasado', hoy)['b'], (ultimo, ultimo))
                self.assertEqual(self.rangos('mes_a_la_fecha', hoy)['b'], (ultimo.replace(day=1), ultimo))
        self.assertEqual(self.tablero._chips_de_comparar(date(2027, 3, 30))[1]['etiqueta'], '28 feb')
        self.assertEqual(self.tablero._chips_de_comparar(date(2028, 3, 30))[3]['etiqueta'], '1–29 feb')
        # En enero, el mes pasado es de otro año: la etiqueta lo dice.
        self.assertEqual(self.tablero._chips_de_comparar(date(2027, 1, 15))[1]['etiqueta'], '15 dic 2026')

    def test_las_etiquetas_son_solo_fechas(self):
        from odoo.addons.dcasa_interfaz.models.comparar import _hora, _mes_completo, _rango_texto
        hoy = date(2026, 10, 17)
        self.assertEqual(_rango_texto(date(2026, 10, 17), date(2026, 10, 17), hoy), '17 oct')
        self.assertEqual(_rango_texto(date(2026, 10, 3), date(2026, 10, 9), hoy), '3–9 oct')
        self.assertEqual(_rango_texto(date(2026, 9, 26), date(2026, 10, 2), hoy), '26 sep–2 oct')
        self.assertEqual(_rango_texto(date(2025, 12, 29), date(2026, 1, 4), hoy), '29 dic 2025–4 ene 2026')
        self.assertEqual(_rango_texto(date(2025, 10, 1), date(2025, 10, 17), hoy), '1–17 oct 2025')
        self.assertEqual(_mes_completo(date(2026, 9, 1), hoy), 'Sep completo')
        self.assertEqual(_mes_completo(date(2025, 9, 1), hoy), 'Sep 2025 completo')
        self.assertEqual(_hora(datetime(2026, 10, 17, 11, 5)), '11:05 a. m.')
        self.assertEqual(_hora(datetime(2026, 10, 17, 0, 30)), '12:30 a. m.')
        self.assertEqual(_hora(datetime(2026, 10, 17, 15, 0)), '3:00 p. m.')

    def test_mes_elegido_entre_los_ultimos_24(self):
        hoy = date(2026, 10, 17)
        meses = self.tablero._meses_para_elegir(hoy)
        self.assertEqual(len(meses), 24)
        self.assertEqual(meses[0], {'valor': '2026-09', 'nombre': 'Septiembre 2026'})
        self.assertEqual(meses[-1]['valor'], '2024-10')
        self.assertEqual(self.rangos('mes', hoy, mes='2025-02')['b'], (date(2025, 2, 1), date(2025, 2, 28)))
        for malo in ('2026-10', '2024-09', 'septiembre', '2026-9', 202609):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.rangos('mes', hoy, mes=malo)

    def test_a_vs_b_del_mismo_largo_o_libre(self):
        hoy = date(2026, 10, 17)
        mismo = self.rangos('rango', hoy, a_desde='2026-10-03', a_hasta='2026-10-09', b_desde='2026-09-01')
        self.assertEqual(mismo['b'], (date(2026, 9, 1), date(2026, 9, 7)), 'B se propone del mismo largo que A')
        self.assertEqual(mismo['modo'], 'variacion')
        # Sin «Libre», un «B hasta» que mande la pantalla no cuenta: el largo lo pone A.
        self.assertEqual(self.rangos('rango', hoy, a_desde='2026-10-03', a_hasta='2026-10-09', b_desde='2026-09-01',
                                     b_hasta='2026-09-30')['b'][1], date(2026, 9, 7))
        libre = self.rangos('rango', hoy, a_desde='2026-10-03', a_hasta='2026-10-09', b_desde='2026-09-01',
                            b_hasta='2026-09-30', libre=True)
        self.assertEqual(libre['b'], (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(libre['modo'], 'por_dia')
        self.assertEqual((libre['dias_a'], libre['dias_b']), (7, 30))

    def test_a_vs_b_rechaza_fechas_malas(self):
        hoy = date(2026, 10, 17)
        malos = [
            dict(a_desde='2026-10-10', a_hasta='2026-10-01', b_desde='2026-09-01'),               # desde > hasta
            dict(a_desde='2026-10-10', a_hasta='2026-10-18', b_desde='2026-09-01'),               # A futura
            dict(a_desde='2025-01-01', a_hasta='2026-10-01', b_desde='2024-01-01'),               # más de un año
            dict(a_desde='2026-10-01', a_hasta='2026-10-10', b_desde='2026-10-12'),               # B pasa de hoy
            dict(a_desde='2026-10-01', a_hasta='2026-10-10', b_desde='2026-10-18', libre=True,
                 b_hasta='2026-10-18'),                                                            # B futura
            dict(a_desde='2026-10-01', a_hasta='2026-10-10', b_desde='2026-09-20', libre=True,
                 b_hasta='2026-09-10'),                                                            # B al revés
            dict(a_desde='2026-10-01', a_hasta='2026-10-10', b_desde='2024-01-01', libre=True,
                 b_hasta='2026-01-01'),                                                            # B de más de un año
            dict(a_desde='no es fecha', a_hasta='2026-10-10', b_desde='2026-09-01'),
            dict(a_desde=None, a_hasta='2026-10-10', b_desde='2026-09-01'),
            dict(a_desde='2026-10-01', a_hasta='2026-10-10', b_desde=None),
            dict(a_desde='2026-10-01', a_hasta='2026-10-10', b_desde='2026-09-01', libre=True),   # libre sin B hasta
        ]
        for kw in malos:
            with self.subTest(**{k: str(v) for k, v in kw.items()}), self.assertRaises(UserError):
                self.rangos('rango', hoy, **kw)
        with self.assertRaises(UserError):
            self.rangos('siempre', hoy)

    def test_el_cambio_nunca_inventa_un_porcentaje(self):
        cambio = self.tablero._cambio
        self.assertEqual(cambio(127.6, 100.0, 'variacion', 1, 1)['valor'], 27.6)
        self.assertEqual(cambio(127.6, 100.0, 'variacion', 1, 1)['sentido'], 'sube')
        for antes in (0.0, -50.0, None):
            with self.subTest(antes=antes):
                self.assertIsNone(cambio(100.0, antes, 'variacion', 1, 1)['valor'], 'sin base positiva: «—»')
                self.assertIsNone(cambio(100.0, antes, 'llevas', 1, 1)['valor'])
        self.assertEqual(cambio(34.4, 39.8, 'variacion', 1, 1, tipo='pts'),
                         {'tipo': 'pts', 'valor': -5.4, 'sentido': 'baja', 'invertido': False})
        self.assertEqual(cambio(6, 5, 'variacion', 1, 1, tipo='num')['valor'], 1)
        self.assertEqual(cambio(6, 0, 'variacion', 1, 1, tipo='num')['valor'], 6, 'una diferencia no es un %')
        # Con largos distintos, todo es por día (también el número de ventas).
        self.assertEqual(cambio(1000.0, 1000.0, 'por_dia', 10, 20),
                         {'tipo': 'pct', 'valor': 100.0, 'sentido': 'sube', 'invertido': False})
        self.assertEqual(cambio(2, 2, 'por_dia', 10, 20, tipo='num')['tipo'], 'pct')
        self.assertEqual(cambio(58.0, 100.0, 'llevas', 17, 30),
                         {'tipo': 'llevas', 'valor': 58.0, 'sentido': None, 'invertido': False})


class CompararCommon(VentasCommon):
    """Ventas fechadas y registradas a una hora fija, con pagos en las fechas y horas que diga cada prueba."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tablero = cls.env['dcasa.tablero']
        cls.banco = cls.env['account.journal'].create({'name': 'Banco comparar', 'type': 'bank', 'code': 'BCMP'})
        cls.mueble = cls.env['product.product'].create({
            'name': 'Mueble comparar', 'list_price': 1000.0, 'standard_price': 600.0, 'taxes_id': [Command.clear()]})
        cls.mueble_barato = cls.env['product.product'].create({
            'name': 'Mueble comparar margen', 'list_price': 1000.0, 'standard_price': 500.0,
            'taxes_id': [Command.clear()]})

    @staticmethod
    def en_utc(dia, hora):
        return PANAMA.localize(datetime.combine(dia, hora)).astimezone(pytz.utc).replace(tzinfo=None)

    def registrar(self, registros, dia, hora):
        """Pone la hora de registro (``create_date``) como si se hubiera anotado ese día a esa hora."""
        if registros:
            self.env.flush_all()
            self.env.cr.execute(f'UPDATE {registros._table} SET create_date = %s WHERE id IN %s',
                                (self.en_utc(dia, hora), tuple(registros.ids)))
            registros.invalidate_recordset(['create_date'])

    def vender(self, dia, hora=time(9, 0), vendedor=None, producto=None, sin_vendedora=False):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': False if sin_vendedora else (vendedor or self.vendedora).id,
            'order_line': [Command.create({'product_id': (producto or self.mueble).id, 'product_uom_qty': 1})]})
        orden.action_confirm()
        factura = orden._create_invoices()
        factura.invoice_date = dia
        factura.action_post()
        self.registrar(factura, dia, hora)
        return orden, factura

    def pagar(self, factura, monto, dia, hora=time(9, 0), registrado=None, usuario=None):
        """Un pago con fecha ``dia``, anotado ``registrado`` (día, hora) o, si no se dice, ese día a esa hora."""
        Registro = self.env['account.payment.register']
        if usuario:
            Registro = Registro.with_user(usuario)
        pagos = Registro.with_context(active_model='account.move', active_ids=factura.ids).create({
            'payment_date': dia, 'amount': monto, 'journal_id': self.banco.id})._create_payments()
        cuando = registrado or (dia, hora)
        lineas = pagos.move_id.line_ids
        self.registrar(pagos, *cuando)
        self.registrar(lineas.matched_debit_ids | lineas.matched_credit_ids, *cuando)
        return pagos

    def medir(self, d0, d1, base, vendedor=None, corte=None):
        return self.tablero.with_user(self.gerencia)._medir(d0, d1, base, vendedor, corte, con_ganancia=True,
                                                            con_cobrado=True)

    def comparar(self, clave, ahora, **kw):
        return self.tablero.with_user(self.gerencia)._comparar(clave, ahora=ahora, **kw)

    @staticmethod
    def filas(resultado):
        return {fila['clave']: fila for fila in resultado['filas']}


@tagged('post_install', '-at_install')
class TestCompletadasYConAbonos(CompararCommon):

    def test_el_ejemplo_de_la_duena(self):
        """Venta de $1,000 el 5 de octubre, abono de $200 ese día y el resto ($800) el 20 de noviembre."""
        oct0, oct1, nov0, nov1 = date(2025, 10, 1), date(2025, 10, 31), date(2025, 11, 1), date(2025, 11, 30)
        equipo_antes = {mes: self.medir(*mes, 'completadas')['cobrado'] for mes in ((oct0, oct1), (nov0, nov1))}
        orden, factura = self.vender(date(2025, 10, 5))
        self.pagar(factura, 200.0, date(2025, 10, 5), time(10, 0))
        self.pagar(factura, 800.0, date(2025, 11, 20), time(15, 0))
        ana = self.vendedora.id
        # Completadas: octubre $0, noviembre $1,000.
        self.assertEqual(self.medir(oct0, oct1, 'completadas', ana)['sin_itbms'], 0)
        noviembre = self.medir(nov0, nov1, 'completadas', ana)
        self.assertEqual((noviembre['sin_itbms'], noviembre['cuantas']), (1000.0, 1))
        self.assertEqual(noviembre['pedidos'], orden)
        self.assertIsNone(noviembre['falta_por_cobrar'], 'Falta por cobrar es solo de «Con abonos»')
        # Con abonos: octubre $1,000 con $800 por cobrar (al cierre de octubre); noviembre $0.
        octubre = self.medir(oct0, oct1, 'con_abonos', ana)
        self.assertEqual((octubre['sin_itbms'], octubre['falta_por_cobrar']), (1000.0, 800.0))
        self.assertEqual(self.medir(nov0, nov1, 'con_abonos', ana)['sin_itbms'], 0)
        # Cobrado (igual en las dos): octubre $200, noviembre $800; el del equipo también.
        for base in ('completadas', 'con_abonos'):
            self.assertEqual(self.medir(oct0, oct1, base, ana)['cobrado'], 200.0)
            self.assertEqual(self.medir(nov0, nov1, base, ana)['cobrado'], 800.0)
        self.assertAlmostEqual(self.medir(oct0, oct1, 'completadas')['cobrado'] - equipo_antes[(oct0, oct1)], 200.0)
        self.assertAlmostEqual(self.medir(nov0, nov1, 'completadas')['cobrado'] - equipo_antes[(nov0, nov1)], 800.0)
        # La venta sigue siendo del 5 de octubre en lo vendido de siempre (la vendedora no cambia).
        self.assertEqual(self.medir(oct0, oct1, 'vendido', ana)['sin_itbms'], 1000.0)
        # El día de los pagos sale de las mismas conciliaciones que el cuadro de pagos de la factura.
        if hasattr(factura, '_dcasa_pagos'):
            pagos = self.tablero._pagos_de_facturas(factura)[factura.id]
            cuadro = factura._dcasa_pagos()
            self.assertEqual(sorted((p['fecha'], p['monto']) for p in pagos),
                             sorted((p['date'], p['amount']) for p in cuadro))
        # «Mes ▾» en noviembre contra octubre completo: en «Con abonos» llevas 0 %; en «Completadas», «—» (base 0).
        noviembre_25 = datetime(2025, 11, 25, 10, 0)
        llevas = self.comparar('mes', noviembre_25, mes='2025-10', base='con_abonos', vendedor=ana)['llevas']
        self.assertEqual(llevas, {'pct': 0.0, 'mes': 'octubre'})
        completadas = self.comparar('mes', noviembre_25, mes='2025-10', vendedor=ana)
        self.assertIsNone(completadas['llevas']['pct'])
        self.assertEqual(completadas['b']['etiqueta'], 'Oct completo')
        self.assertEqual(self.filas(completadas)['ventas']['cambio']['tipo'], 'llevas')

    def test_una_venta_sin_pago_no_entra_en_ninguna(self):
        dia = date(2025, 10, 6)
        orden, _factura = self.vender(dia)
        for base in ('completadas', 'con_abonos'):
            with self.subTest(base):
                self.assertNotIn(orden, self.medir(dia, dia, base, self.vendedora.id)['pedidos'])
        self.assertIn(orden, self.medir(dia, dia, 'vendido', self.vendedora.id)['pedidos'],
                      'en lo vendido de siempre (la vendedora) sí cuenta')

    def test_una_nota_de_credito_total_la_saca(self):
        dia = date(2025, 10, 7)
        pagada, factura_pagada = self.vender(dia)
        self.pagar(factura_pagada, 1000.0, dia)
        abonada, factura_abonada = self.vender(dia)
        self.pagar(factura_abonada, 100.0, dia)
        antes = self.medir(dia, dia, 'con_abonos', self.vendedora.id)['pedidos']
        self.assertTrue(pagada | abonada <= antes)
        for factura in (factura_pagada, factura_abonada):
            nota = factura._reverse_moves([{'invoice_date': dia, 'ref': 'Devolución total'}])
            nota.action_post()
        for base in ('completadas', 'con_abonos'):
            with self.subTest(base):
                pedidos = self.medir(dia, date(2025, 10, 31), base, self.vendedora.id)['pedidos']
                self.assertFalse(pedidos & (pagada | abonada), 'una venta devuelta entera no cuenta')

    def test_con_abonos_cuenta_el_dia_de_la_venta_y_completadas_el_del_ultimo_pago(self):
        orden, factura = self.vender(date(2025, 10, 8))
        self.pagar(factura, 400.0, date(2025, 10, 9))
        self.pagar(factura, 600.0, date(2025, 10, 12))
        ana = self.vendedora.id
        self.assertIn(orden, self.medir(date(2025, 10, 8), date(2025, 10, 8), 'con_abonos', ana)['pedidos'])
        self.assertNotIn(orden, self.medir(date(2025, 10, 8), date(2025, 10, 11), 'completadas', ana)['pedidos'])
        self.assertIn(orden, self.medir(date(2025, 10, 12), date(2025, 10, 12), 'completadas', ana)['pedidos'])
        # Al cierre del 10 faltaban $600; al del 12, nada.
        self.assertEqual(self.medir(date(2025, 10, 1), date(2025, 10, 10), 'con_abonos', ana)['falta_por_cobrar'],
                         600.0)
        self.assertEqual(self.medir(date(2025, 10, 1), date(2025, 10, 12), 'con_abonos', ana)['falta_por_cobrar'],
                         0.0)

    def test_un_pago_anticipado_no_completa_la_venta_antes_de_que_exista(self):
        """Un pago con fecha anterior a la factura completa la venta el día de la venta, no antes."""
        orden, factura = self.vender(date(2025, 10, 14))
        self.pagar(factura, 1000.0, date(2025, 10, 10))
        ana = self.vendedora.id
        self.assertNotIn(orden, self.medir(date(2025, 10, 10), date(2025, 10, 13), 'completadas', ana)['pedidos'])
        self.assertIn(orden, self.medir(date(2025, 10, 14), date(2025, 10, 14), 'completadas', ana)['pedidos'])


@tagged('post_install', '-at_install')
class TestHastaLaMismaHora(CompararCommon):
    """Viernes 17 de octubre de 2025 a las 11:00 de Panamá: hoy hasta ahora; ayer, hasta las 11:00."""

    AHORA = datetime(2025, 10, 17, 11, 0)

    def setUp(self):
        super().setUp()
        hoy, ayer = date(2025, 10, 17), date(2025, 10, 16)
        self.hoy_, self.ayer = hoy, ayer
        v = self.otra
        _s1, f1 = self.vender(hoy, time(9, 0), v)
        self.pagar(f1, 1000.0, hoy, time(9, 0))
        _s2, f2 = self.vender(ayer, time(10, 0), v)
        self.pagar(f2, 1000.0, ayer, time(10, 0))
        _s3, f3 = self.vender(ayer, time(15, 0), v)                       # después de las 11: no entra en el corte
        self.pagar(f3, 1000.0, ayer, time(15, 0))
        self.s4, f4 = self.vender(ayer, time(9, 0), v)                    # abono antes de las 11, resto después
        self.pagar(f4, 300.0, ayer, time(9, 0))
        self.pagar(f4, 700.0, ayer, time(14, 0))
        self.s5, f5 = self.vender(ayer, time(9, 30), v)                   # pago de ayer anotado hoy
        self.pagar(f5, 1000.0, ayer, registrado=(hoy, time(8, 0)))

    def test_ayer_cuenta_solo_lo_registrado_hasta_la_misma_hora(self):
        resultado = self.comparar('ayer', self.AHORA, vendedor=self.otra.id)
        self.assertEqual(resultado['hora'], '11:00 a. m.')
        self.assertEqual((resultado['a']['etiqueta'], resultado['b']['etiqueta']), ('17 oct', '16 oct'))
        filas = self.filas(resultado)
        self.assertEqual((filas['ventas']['a'], filas['ventas']['b']), (1000.0, 1000.0))
        self.assertEqual(filas['ventas']['cambio'], {'tipo': 'pct', 'valor': 0.0, 'sentido': 'igual',
                                                     'invertido': False})
        self.assertEqual((filas['cuantas']['a'], filas['cuantas']['b']), (1, 1))
        # Cobrado de ayer a las 11: la venta de las 10 y el abono de las 9 (no lo de las 14 y 15, ni lo anotado hoy).
        self.assertEqual(filas['cobrado']['b'], 1300.0)
        self.assertEqual(filas['cobrado']['a'], 1000.0)
        # Con abonos: a las 11 ya tenían abono la de las 10 y la de las 9; faltaban los $700 del resto.
        abonos = self.filas(self.comparar('ayer', self.AHORA, vendedor=self.otra.id, base='con_abonos'))
        self.assertEqual(abonos['ventas']['b'], 2000.0)
        self.assertEqual(abonos['falta']['b'], 700.0)
        self.assertEqual(abonos['falta']['a'], 0.0)

    def test_el_dia_completo_cuenta_todo(self):
        ayer = self.ayer
        completo = self.medir(ayer, ayer, 'completadas', self.otra.id)
        self.assertEqual(completo['cuantas'], 4, 'las de las 10, 15, la del resto de las 14 y la anotada hoy')
        self.assertEqual(completo['cobrado'], 4000.0)
        self.assertEqual(self.medir(ayer, ayer, 'con_abonos', self.otra.id)['falta_por_cobrar'], 0.0)
        corte = self.en_utc(ayer, time(11, 0))
        cortado = self.medir(ayer, ayer, 'completadas', self.otra.id, corte)
        self.assertNotIn(self.s4, cortado['pedidos'], 'a las 11 todavía debía $700')
        self.assertNotIn(self.s5, cortado['pedidos'], 'su pago se anotó hoy: ayer a las 11 no estaba')

    def test_los_dias_anteriores_al_corte_cuentan_completos(self):
        """En «1–17 oct» contra «1–17 sep» solo se corta el último día; el resto del rango va completo."""
        resultado = self.comparar('rango', self.AHORA, vendedor=self.otra.id, a_desde='2025-10-16',
                                  a_hasta='2025-10-17', b_desde='2025-10-15')
        filas = self.filas(resultado)
        self.assertEqual(resultado['hora'], '11:00 a. m.')
        self.assertEqual(filas['ventas']['a'], 5000.0, 'el 16 completo (4) y el 17 hasta las 11 (1)')
        self.assertEqual(filas['ventas']['b'], 1000.0, 'B termina el 16 a las 11: nada el 15 y una sola el 16')

    def test_a_vs_b_que_no_termina_hoy_no_se_corta(self):
        resultado = self.comparar('rango', self.AHORA, vendedor=self.otra.id, a_desde='2025-10-16',
                                  a_hasta='2025-10-16', b_desde='2025-10-16')
        self.assertFalse(resultado['hora'])
        filas = self.filas(resultado)
        self.assertEqual((filas['ventas']['a'], filas['ventas']['b']), (4000.0, 4000.0))

    def test_mes_contra_un_mes_completo_no_corta_b(self):
        resultado = self.comparar('mes', self.AHORA, vendedor=self.otra.id, mes='2025-09')
        self.assertEqual(resultado['hora'], '11:00 a. m.', 'hoy sí va hasta la hora actual')
        self.assertEqual((resultado['a']['etiqueta'], resultado['b']['etiqueta']), ('1–17 oct', 'Sep completo'))
        self.assertEqual(resultado['b']['hasta'], '2025-09-30')


@tagged('post_install', '-at_install')
class TestCompararFilas(CompararCommon):

    def test_base_cero_da_raya_y_el_margen_va_en_puntos(self):
        hoy = date(2025, 10, 17)
        _o, factura = self.vender(hoy, time(8, 0), self.otra)
        self.pagar(factura, 1000.0, hoy, time(8, 0))
        filas = self.filas(self.comparar('dia_mes_pasado', datetime(2025, 10, 17, 11, 0), vendedor=self.otra.id))
        for clave in ('ventas', 'ganancia', 'cobrado'):
            with self.subTest(clave):
                self.assertEqual(filas[clave]['b'], 0.0)
                self.assertIsNone(filas[clave]['cambio']['valor'], 'contra 0 no hay porcentaje: «—»')
        self.assertIsNone(filas['margen']['b'])
        self.assertIsNone(filas['margen']['cambio']['valor'])
        self.assertEqual(filas['cuantas']['cambio'], {'tipo': 'num', 'valor': 1, 'sentido': 'sube', 'invertido': False})
        self.assertEqual([f for f in filas], ['ventas', 'ganancia', 'margen', 'cuantas', 'cobrado'])

    def test_margen_en_puntos(self):
        a, b = date(2025, 10, 17), date(2025, 10, 10)
        _o, fa = self.vender(a, time(8, 0), self.otra, self.mueble)            # 40 %
        self.pagar(fa, 1000.0, a, time(8, 0))
        _o, fb = self.vender(b, time(8, 0), self.otra, self.mueble_barato)     # 50 %
        self.pagar(fb, 1000.0, b, time(8, 0))
        filas = self.filas(self.comparar('semana_pasada', datetime(2025, 10, 17, 11, 0), vendedor=self.otra.id))
        self.assertEqual((filas['margen']['a'], filas['margen']['b']), (40.0, 50.0))
        self.assertEqual(filas['margen']['cambio'], {'tipo': 'pts', 'valor': -10.0, 'sentido': 'baja',
                                                     'invertido': False})
        self.assertEqual((filas['ganancia']['a'], filas['ganancia']['b']), (400.0, 500.0))
        self.assertEqual(filas['ganancia']['cambio']['valor'], -20.0)
        # El margen es el mismo porcentaje de la tarjeta de Ganancia.
        tarjeta = self.tablero.with_user(self.gerencia).ventas_del_periodo(
            'rango', '2025-10-17', '2025-10-17', vendedor=self.otra.id)
        self.assertEqual(tarjeta['actual']['ganancia']['porcentaje'], filas['margen']['a'])

    def test_a_vs_b_libre_de_distinto_largo_es_por_dia(self):
        _o, fa = self.vender(date(2025, 10, 5), time(8, 0), self.otra)
        self.pagar(fa, 1000.0, date(2025, 10, 5))
        _o, fb = self.vender(date(2025, 9, 5), time(8, 0), self.otra)
        self.pagar(fb, 1000.0, date(2025, 9, 5))
        ahora = datetime(2025, 10, 17, 11, 0)
        libre = self.comparar('rango', ahora, vendedor=self.otra.id, a_desde='2025-10-01', a_hasta='2025-10-10',
                              b_desde='2025-09-01', b_hasta='2025-09-20', libre=True)
        self.assertEqual(libre['modo'], 'por_dia')
        self.assertEqual((libre['a']['dias'], libre['b']['dias']), (10, 20))
        filas = self.filas(libre)
        self.assertEqual((filas['ventas']['a'], filas['ventas']['b']), (1000.0, 1000.0))
        self.assertEqual(filas['ventas']['cambio']['valor'], 100.0, '$100 por día contra $50 por día')
        self.assertEqual(filas['cuantas']['cambio']['tipo'], 'pct')
        mismo = self.comparar('rango', ahora, vendedor=self.otra.id, a_desde='2025-10-01', a_hasta='2025-10-10',
                              b_desde='2025-09-01')
        self.assertEqual(mismo['modo'], 'variacion')
        self.assertEqual(mismo['b']['hasta'], '2025-09-10')
        self.assertEqual(self.filas(mismo)['ventas']['cambio']['valor'], 0.0)


@tagged('post_install', '-at_install')
class TestPorVendedora(CompararCommon):

    def test_cobrado_de_una_vendedora_es_el_de_sus_ventas_no_el_que_registro(self):
        dia = date(2025, 10, 20)
        antes_equipo = self.medir(dia, dia, 'completadas')['cobrado']
        _o, suya = self.vender(dia, time(8, 0), self.vendedora)
        self.pagar(suya, 1000.0, dia, usuario=self.gerencia)            # lo registra Caja (Gerencia)
        _o, sin = self.vender(dia, time(8, 0), sin_vendedora=True)
        self.pagar(sin, 400.0, dia)
        suelto = self.env['account.payment'].create({                    # un anticipo sin factura: es del equipo
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 50.0,
            'journal_id': self.banco.id, 'date': dia})
        suelto.action_post()
        self.assertEqual(self.medir(dia, dia, 'completadas', self.vendedora.id)['cobrado'], 1000.0)
        self.assertEqual(self.medir(dia, dia, 'completadas', self.gerencia.id)['cobrado'], 0.0,
                         'quien registró el cobro no se lo lleva')
        self.assertEqual(self.medir(dia, dia, 'completadas', self.otra.id)['cobrado'], 0.0)
        self.assertEqual(self.medir(dia, dia, 'completadas', 'sin')['cobrado'], 400.0)
        self.assertAlmostEqual(self.medir(dia, dia, 'completadas')['cobrado'] - antes_equipo, 1450.0)

    def test_el_filtro_y_la_lista_por_vendedora(self):
        dia = date(2025, 10, 21)
        Tablero = self.tablero.with_user(self.gerencia)
        suyas = self.env['sale.order']
        for _ in range(2):
            orden, factura = self.vender(dia, time(8, 0), self.vendedora)
            self.pagar(factura, 1000.0, dia, time(8, 0))
            suyas |= orden
        de_otra, factura = self.vender(dia, time(8, 0), self.otra)
        self.pagar(factura, 1000.0, dia, time(8, 0))
        sin, factura = self.vender(dia, time(8, 0), sin_vendedora=True)
        self.pagar(factura, 500.0, dia, time(8, 0))
        tarjeta = Tablero.ventas_del_periodo('rango', '2025-10-21', '2025-10-21', vendedor=self.vendedora.id)
        self.assertEqual(tarjeta['actual']['sin_itbms'], 2000.0)
        self.assertEqual(self.env['sale.order'].search(tarjeta['accion']['domain']), suyas,
                         'la lista abre el mismo conjunto de la tarjeta')
        self.assertIsNone(tarjeta['cuadre'], 'con una vendedora no se cuadra contra toda la contabilidad')
        con_abonos = Tablero.ventas_del_periodo('rango', '2025-10-21', '2025-10-21', base='con_abonos',
                                                vendedor='sin')
        self.assertEqual(self.env['sale.order'].search(con_abonos['accion']['domain']), sin)
        self.assertEqual(con_abonos['actual']['falta_por_cobrar'], 500.0)
        # En «Con abonos» entra también la venta sin vendedora (tiene un abono; no está pagada completa).
        resultado = self.comparar('rango', datetime(2025, 10, 25, 10, 0), vendedor=self.otra.id, base='con_abonos',
                                  a_desde='2025-10-21', a_hasta='2025-10-21', b_desde='2025-10-14',
                                  por_vendedora=True)
        self.assertEqual(self.filas(resultado)['ventas']['a'], 1000.0, 'la tabla sigue a la vendedora elegida')
        lista = resultado['por_vendedora']
        mias = [f for f in lista if f['vendedor'] in (self.vendedora.id, self.otra.id, 'sin')]
        self.assertEqual([f['vendedor'] for f in mias], [self.vendedora.id, self.otra.id, 'sin'])
        self.assertEqual([f['a'] for f in lista], sorted((f['a'] for f in lista), reverse=True), 'de mayor a menor')
        self.assertEqual(mias[0]['nombre'], self.vendedora.name)
        self.assertEqual(mias[-1]['nombre'], 'Sin vendedora')
        self.assertEqual((mias[0]['a'], mias[0]['b']), (2000.0, 0.0))
        self.assertIsNone(mias[0]['cambio']['valor'])
        self.assertIn(de_otra, self.medir(dia, dia, 'completadas', self.otra.id)['pedidos'])

    def test_las_vendedoras_del_selector(self):
        ex = crear_usuario(self.env, 'ex_vendedora_comparar', 'base.group_user')
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id, 'user_id': ex.id,
                                               'order_line': [Command.create({'product_id': self.mueble.id})]})
        orden.action_confirm()
        opciones = self.tablero.with_user(self.gerencia)._opciones_de_comparar(date(2026, 10, 17))
        ids = [v['id'] for v in opciones['vendedoras']]
        self.assertIn(self.vendedora.id, ids)
        self.assertIn(self.otra.id, ids)
        self.assertIn(ex.id, ids, 'quien tuvo ventas en el periodo, aunque ya no tenga el rol')
        self.assertNotIn(self.gerencia.id, ids, 'Gerencia incluye el rol Vendedora: no por eso sale')
        self.assertEqual(ids[-1], 'sin')


@tagged('post_install', '-at_install')
class TestCompararPermisosYValidaciones(CompararCommon):

    def test_solo_gerencia_compara(self):
        for usuario in (self.vendedora, self.otra):
            with self.subTest(usuario.login), self.assertRaises(AccessError):
                self.tablero.with_user(usuario).comparar_ventas('ayer')
        contador = crear_usuario(self.env, 'contador_comparar', 'account.group_account_user')
        contador.group_ids = [Command.link(self.env.ref('sales_team.group_sale_salesman').id)]
        with self.assertRaises(AccessError):
            self.tablero.with_user(contador).comparar_ventas('ayer')
        with self.assertRaises(AccessError):
            self.tablero.with_user(contador).ventas_del_periodo('hoy', vendedor=self.vendedora.id)
        resultado = self.tablero.with_user(self.gerencia).comparar_ventas('ayer')
        self.assertEqual(resultado['base'], 'completadas')
        self.assertEqual([f['clave'] for f in resultado['filas']][:4], ['ventas', 'ganancia', 'margen', 'cuantas'])

    def test_la_vendedora_no_ve_el_bloque_ni_lo_de_otras(self):
        Tablero = self.tablero.with_user(self.vendedora)
        datos = Tablero.obtener_datos()
        self.assertIsNone(datos['comparar'])
        self.assertFalse(datos['bases'])
        for ajeno in (self.otra.id, str(self.otra.id), 'sin', self.gerencia.id):
            with self.subTest(ajeno=ajeno), self.assertRaises(AccessError):
                Tablero.ventas_del_periodo('hoy', vendedor=ajeno)
        # Lo suyo sigue igual: lo facturado por completo, el día de la factura (sin interruptor).
        propio = Tablero.ventas_del_periodo('hoy', vendedor=self.vendedora.id, base='con_abonos')
        self.assertEqual(propio['base'], 'vendido')
        self.assertIsNone(propio['vendedor'])
        self.assertIsNone(propio['actual']['ganancia'])

    def test_gerencia_recibe_el_bloque_y_abre_en_completadas(self):
        datos = self.tablero.with_user(self.gerencia).obtener_datos()
        self.assertEqual([b['clave'] for b in datos['bases']], ['completadas', 'con_abonos'])
        self.assertEqual(datos['ventas']['base'], 'completadas')
        self.assertEqual(len(datos['comparar']['chips']), 6)
        self.assertEqual(len(datos['comparar']['meses']), 24)
        self.assertEqual(datos['comparar']['vendedoras'][-1]['id'], 'sin')

    def test_el_servidor_valida_cada_dato(self):
        Tablero = self.tablero.with_user(self.gerencia)
        for kw in (dict(comparacion='siempre'), dict(comparacion='ayer', base='vendido'),
                   dict(comparacion='ayer', base='todo'), dict(comparacion='ayer', vendedor='x'),
                   dict(comparacion='ayer', vendedor=True), dict(comparacion='ayer', vendedor=99999999),
                   dict(comparacion='ayer', vendedor=1.5), dict(comparacion='mes', mes='1999-01'),
                   dict(comparacion='rango', a_desde='2025-10-01')):
            with self.subTest(**{k: str(v) for k, v in kw.items()}), self.assertRaises(UserError):
                Tablero.comparar_ventas(**kw)
        with self.assertRaises(UserError):
            Tablero.ventas_del_periodo('hoy', base='vendido')


@tagged('post_install', '-at_install')
class TestCompararEnElNavegador(VentasMixin, HttpCase):
    """El Inicio de Gerencia en Chrome, a 1440 px y a 390 px (celular): toca cada botón de «Comparar», el interruptor
    y «Por vendedora». Solo números, azul si sube, y nada se sale por el costado."""

    def setUp(self):
        super().setUp()
        self.banco = self.env['account.journal'].create({'name': 'Banco navegador', 'type': 'bank', 'code': 'BNAV'})
        producto = self.env['product.product'].create({
            'name': 'Mueble navegador', 'list_price': 300.0, 'standard_price': 180.0, 'taxes_id': [Command.clear()]})
        for vendedor, pago in ((self.vendedora, 1.0), (self.vendedora, 1.0), (self.otra, 0.5)):
            orden = self.pedido(vendedor=vendedor, producto=producto)
            factura = self.facturar(orden)
            self.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=factura.ids).create({
                    'payment_date': factura.invoice_date, 'amount': factura.amount_total * pago,
                    'journal_id': self.banco.id})._create_payments()

    def test_comparar_a_1440_y_a_390(self):
        codigo = '(async () => {' + ESPERAR_JS + r"""
            const sinScrollDeCostado = (que) => {
                const raiz = document.querySelector('.o_dcasa_inicio');
                if (raiz.scrollWidth > raiz.clientWidth + 1) {
                    throw new Error(`scroll de costado (${que}): ${raiz.scrollWidth} > ${raiz.clientWidth}`);
                }
            };
            const cuerpo = (clave, base) => document.querySelector(
                `.o_dcasa_comparar_cuerpo[data-comparacion="${clave}"][data-base="${base}"]:not(.o_cargando)`);
            await esperar(() => document.querySelector('.o_dcasa_comparar'), 'el bloque Comparar');
            igual(textos('.o_dcasa_interruptor_opcion'), ['Completadas', 'Con abonos'], 'el interruptor');
            const activa = document.querySelector('.o_dcasa_base_completadas.o_activo');
            if (!activa) { throw new Error('abre en «Completadas»'); }
            igual(getComputedStyle(activa).backgroundColor, 'rgb(19, 64, 177)', 'la píldora activa, azul de la marca');
            igual(getComputedStyle(activa).color, 'rgb(255, 255, 255)', 'con texto blanco');
            igual(document.querySelector('.o_dcasa_base_detalle').textContent.trim(),
                  'Pagadas al 100 %, el día del último pago', 'la línea corta');
            igual(document.querySelector('.o_dcasa_vendedora_select').value, '', 'abre en «Todo el equipo»');
            igual(textos('.o_dcasa_chip').length, 6, 'seis botones');
            sinScrollDeCostado('al abrir');
            for (const clave of ['ayer', 'dia_mes_pasado', 'semana_pasada', 'mes_a_la_fecha', 'mes', 'rango']) {
                document.querySelector('.o_dcasa_chip_' + clave).click();
                await esperar(() => cuerpo(clave, 'completadas'), 'la tabla de ' + clave);
                const filas = textos('.o_dcasa_comparar_tabla tbody th');
                for (const fila of ['Ventas', 'Ganancia', 'Margen', 'N.º de ventas', 'Cobrado']) {
                    if (!filas.some((t) => t.startsWith(fila))) { throw new Error(`${clave}: falta la fila ${fila}`); }
                }
                // Las cabeceras son solo fechas («17 oct», «1–17 oct», «Sep completo»): nada de frases.
                const cabeceras = textos('.o_dcasa_comparar_tabla thead .o_dcasa_cmp_a, '
                                         + '.o_dcasa_comparar_tabla thead .o_dcasa_cmp_b');
                for (const cabecera of cabeceras) {
                    if (!/^\d{1,2}(–\d{1,2})? [a-z]{3}/.test(cabecera) && !/ completo$/.test(cabecera)
                            && !/^\d{1,2} [a-z]{3}–\d{1,2} [a-z]{3}/.test(cabecera)) {
                        throw new Error(`${clave}: la cabecera no es una fecha: ${cabecera}`);
                    }
                }
                if (clave === 'mes') {
                    const llevas = document.querySelector('.o_dcasa_llevas').textContent.trim();
                    if (!/^Llevas (\d[\d,]* %|—) de [a-z]+/.test(llevas)) {
                        throw new Error('el número grande: ' + llevas);
                    }
                    const ultima = document.querySelector('.o_dcasa_comparar_tabla thead .o_dcasa_cmp_cambio');
                    igual(ultima.textContent.trim(), 'Llevas', 'la última columna de «Mes»');
                } else if (document.querySelector('.o_dcasa_llevas')) {
                    throw new Error(clave + ': el número grande es solo de «Mes»');
                }
                if (clave === 'ayer') {
                    if (!document.querySelector('.o_dcasa_comparar_hora')) {
                        throw new Error('hoy cuenta hasta la hora');
                    }
                    // Hoy 2 completadas (la tercera está a medias) contra ninguna ayer: sube, en azul.
                    const cambio = document.querySelector('.o_dcasa_cmp_fila_cuantas .o_dcasa_cmp_cambio');
                    igual(cambio.textContent.trim(), '▲ 2', 'el cambio del número de ventas');
                    igual(getComputedStyle(cambio).color, 'rgb(19, 64, 177)', 'sube en azul');
                    const ventas = document.querySelector('.o_dcasa_cmp_fila_ventas .o_dcasa_cmp_cambio');
                    igual(ventas.textContent.trim(), '—', 'contra $0 no hay porcentaje');
                }
                sinScrollDeCostado(clave);
            }
            // «A vs B»: sale el calendario; con «Libre» aparece «B hasta».
            if (!document.querySelector('.o_dcasa_cmp_a_desde') || document.querySelector('.o_dcasa_cmp_b_hasta')) {
                throw new Error('A vs B: A con dos fechas y B solo con su inicio');
            }
            document.querySelector('.o_dcasa_cmp_libre').click();
            await esperar(() => document.querySelector('.o_dcasa_cmp_b_hasta'), 'B hasta con «Libre»');
            // «Con abonos» cambia la tabla: aparece «Falta por cobrar».
            document.querySelector('.o_dcasa_base_con_abonos').click();
            await esperar(() => cuerpo('rango', 'con_abonos'), 'la tabla con abonos');
            if (!document.querySelector('.o_dcasa_cmp_fila_falta')) {
                throw new Error('falta la fila Falta por cobrar');
            }
            igual(document.querySelector('.o_dcasa_base_detalle').textContent.trim(),
                  'Con al menos un abono, por su valor total', 'la línea corta de «Con abonos»');
            // Por vendedora: de mayor a menor; al tocar una fila, el selector queda en ella.
            document.querySelector('.o_dcasa_por_vendedora_boton').click();
            await esperar(() => document.querySelector('.o_dcasa_pv_fila'), 'la lista por vendedora');
            const nombres = textos('.o_dcasa_pv_nombre');
            igual(nombres.slice(0, 2), [__ANA__, __OTRA__], 'las vendedoras, de mayor a menor');
            sinScrollDeCostado('por vendedora');
            document.querySelector('.o_dcasa_pv_fila').click();
            await esperar(() => document.querySelector('.o_dcasa_vendedora_select').value === __ANA_ID__,
                          'el selector en la vendedora');
            await esperar(() => !document.querySelector('.o_dcasa_pv_fila') && cuerpo('rango', 'con_abonos'),
                          'la tabla de la vendedora');
        """.replace('__ANA__', json.dumps(self.vendedora.name)).replace('__OTRA__', json.dumps(self.otra.name)).replace(
            '__ANA_ID__', json.dumps(str(self.vendedora.id))) + "console.log('test successful'); })();"
        for tamano in ('1440x900', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='gerencia_rol',
                                timeout=120)
