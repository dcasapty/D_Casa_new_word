"""«Por día» y «Estadísticas» (pedido del jefe, 2026-10-22): lo vendido o facturado de cada día del mes, lo que se hizo
un día y gráficas simples, con las mismas cuentas del Inicio de Gerencia.

* Los días suman el mes al centavo y el mes es la tarjeta del Inicio para esas fechas (en las tres bases de facturas).
* Las notas de crédito restan el día de su fecha; una factura anulada o en borrador no cuenta.
* «Vendido» son los pedidos confirmados, el día de Panamá en que se confirmaron (las 11:30 p. m. siguen siendo ese
  día aunque en UTC ya sea el siguiente).
* «Mes anterior» es lo mismo que «Comparar › del 1 a hoy» (hasta la misma hora) o el mes anterior completo.
* La vendedora no entra (ni por la pantalla ni por la conexión de datos).

Fechas fijas de 2025 (``ahora`` se pasa a mano): nada depende del reloj real.
"""
from datetime import date, datetime, time

from odoo import Command
from odoo.addons.dcasa_interfaz.models.por_dia import BASES_POR_DIA
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_comparar import PANAMA
from .test_facturado import FacturadoCommon


def en_panama(dia, hora):
    return PANAMA.localize(datetime.combine(dia, hora))


class PorDiaCommon(FacturadoCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ger = cls.env['dcasa.tablero'].with_user(cls.gerencia)

    def confirmar_a_las(self, dia, hora, vendedor=None, producto=None, cantidad=1, confirmar=True):
        """Un pedido confirmado ese día de Panamá a esa hora (Odoo pone la hora de confirmación en ``date_order``)."""
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': (vendedor or self.vendedora).id,
            'order_line': [Command.create({'product_id': (producto or self.mueble).id, 'product_uom_qty': cantidad})]})
        if confirmar:
            orden.action_confirm()
        orden.date_order = self.en_utc(dia, hora)
        return orden

    def anular(self, factura):
        factura.button_draft()
        factura.button_cancel()
        return factura


@tagged('post_install', '-at_install')
class TestPorDia(PorDiaCommon):

    def test_los_dias_suman_el_mes_y_el_mes_es_el_del_inicio(self):
        """Junio de 2025: dos ventas el 3, una factura sin pedido el 5, una nota de crédito el 10, una factura anulada
        el 7 y otra en borrador el 8. Cada día dice lo suyo; los días suman el mes y el mes es la tarjeta del Inicio
        (y ``_medir``) para esas fechas, en las tres bases de facturas."""
        ana = self.vendedora.id
        _o1, f1 = self.vender(date(2025, 6, 3), vendedor=self.vendedora)
        _o2, f2 = self.vender(date(2025, 6, 3), vendedor=self.vendedora, producto=self.cama)
        self.suelta(date(2025, 6, 5), self.mueble, 450.0, vendedor=self.vendedora)
        self.nota(f1, date(2025, 6, 10), precio=100.0)
        self.anular(self.suelta(date(2025, 6, 7), self.mueble, 999.0, vendedor=self.vendedora))
        borrador = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': date(2025, 6, 8),
            'invoice_user_id': ana,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 777.0})]})
        self.assertEqual(borrador.state, 'draft')
        self.pagar(f2, f2.amount_total, date(2025, 6, 12))
        ahora = en_panama(date(2025, 7, 10), time(11, 0))
        d0, d1 = date(2025, 6, 1), date(2025, 6, 30)
        for base in ('facturado', 'con_abonos', 'completadas'):
            for vendedor in (None, ana):
                with self.subTest(base=base, vendedor=vendedor):
                    mes = self.ger._por_dia('2025-06', base, vendedor, ahora)
                    medida = self.medir(d0, d1, base, vendedor)
                    self.assertFalse(mes['en_curso'])
                    self.assertEqual(len(mes['dias']), 30)
                    self.assertAlmostEqual(sum(d['sin_itbms'] for d in mes['dias']), mes['total']['sin_itbms'],
                                           places=2, msg='los días suman el mes al centavo')
                    self.assertAlmostEqual(sum(d['total'] for d in mes['dias']), mes['total']['total'], places=2)
                    self.assertEqual(sum(d['cuantas'] for d in mes['dias']), mes['total']['cuantas'])
                    self.assertEqual(mes['total']['sin_itbms'], medida['sin_itbms'])
                    self.assertEqual((mes['total']['cuantas'], mes['total']['notas']),
                                     (medida['cuantas'], medida['notas']))
                    tarjeta = self.ger.ventas_del_periodo('rango', str(d0), str(d1), base=base, vendedor=vendedor)
                    self.assertEqual(mes['total']['sin_itbms'], tarjeta['actual']['sin_itbms'],
                                     'el mismo número de la tarjeta del Inicio')
                    lista = self.env['account.move'].with_user(self.gerencia).search(mes['accion']['domain'])
                    self.assertEqual(sorted(lista.ids), self.ids(medida), 'la lista abre lo mismo que se contó')
        dias = {d['numero']: d for d in self.ger._por_dia('2025-06', 'facturado', ana, ahora)['dias']}
        self.assertEqual((dias[3]['cuantas'], dias[3]['sin_itbms']), (2, 1500.0))
        self.assertEqual((dias[5]['cuantas'], dias[5]['sin_itbms']), (1, 450.0))
        self.assertEqual((dias[7]['cuantas'], dias[7]['sin_itbms']), (0, 0.0), 'la factura anulada no cuenta')
        self.assertEqual((dias[8]['cuantas'], dias[8]['sin_itbms']), (0, 0.0), 'el borrador no cuenta')
        self.assertEqual((dias[10]['cuantas'], dias[10]['notas'], dias[10]['sin_itbms']), (0, 1, -100.0),
                         'la nota de crédito resta el día de su fecha')
        mes = self.ger._por_dia('2025-06', 'facturado', ana, ahora)
        self.assertEqual(mes['total']['sin_itbms'], 1850.0)
        self.assertEqual(mes['mejor']['fecha'], '2025-06-03')
        self.assertEqual(mes['primer_dia_semana'], 6, 'el 1 de junio de 2025 fue domingo')
        completadas = {d['numero']: d for d in self.ger._por_dia('2025-06', 'completadas', ana, ahora)['dias']}
        self.assertEqual(completadas[12]['sin_itbms'], 500.0, 'completadas: la cama, el día del último pago')

    def test_lo_que_se_hizo_un_dia(self):
        ana = self.vendedora.id
        _orden, factura = self.vender(date(2025, 6, 3), vendedor=self.vendedora)
        nota = self.nota(factura, date(2025, 6, 3), precio=100.0)
        self.pagar(factura, 300.0, date(2025, 6, 3))
        dia = self.ger._del_dia(date(2025, 6, 3), 'facturado', ana, date(2025, 7, 10))
        self.assertEqual(dia['nombre'], 'Martes 3 de junio')
        filas = {fila['id']: fila for fila in dia['filas']}
        self.assertEqual(set(filas), {factura.id, nota.id})
        self.assertEqual(filas[factura.id]['numero'], factura.name)
        self.assertEqual(filas[factura.id]['cliente'], self.cliente.display_name)
        self.assertEqual(filas[factura.id]['vendedora'], self.vendedora.name)
        self.assertEqual(filas[factura.id]['estado'], 'Con abono')
        self.assertEqual(filas[factura.id]['modelo'], 'account.move')
        self.assertEqual((filas[nota.id]['estado'], filas[nota.id]['sin_itbms']), ('Nota de crédito', -100.0))
        self.assertTrue(filas[nota.id]['es_nota'])
        self.assertEqual((dia['total']['sin_itbms'], dia['total']['cuantas'], dia['total']['notas']), (900.0, 1, 1))
        con_abonos = self.ger._del_dia(date(2025, 6, 3), 'con_abonos', ana, date(2025, 7, 10))
        self.assertIsNotNone(con_abonos['total']['falta_por_cobrar'], 'con abonos dice cuánto falta por cobrar')

    def test_vendido_son_los_pedidos_confirmados_el_dia_de_panama(self):
        """Confirmado a las 11:30 p. m. del 5 (ya es el 6 en UTC): cuenta el 5. Una cotización y un pedido cancelado
        no cuentan."""
        ana = self.vendedora.id
        tarde = self.confirmar_a_las(date(2025, 6, 5), time(23, 30))
        self.assertEqual(tarde.date_order.date(), date(2025, 6, 6), 'en UTC ya es el 6')
        temprano = self.confirmar_a_las(date(2025, 6, 6), time(0, 10), producto=self.cama)
        self.confirmar_a_las(date(2025, 6, 6), time(10, 0), confirmar=False)          # cotización
        cancelado = self.confirmar_a_las(date(2025, 6, 6), time(11, 0))
        cancelado._action_cancel()
        self.assertEqual(cancelado.state, 'cancel')
        ahora = en_panama(date(2025, 7, 10), time(11, 0))
        dias = {d['numero']: d for d in self.ger._por_dia('2025-06', 'confirmado', ana, ahora)['dias']}
        self.assertEqual((dias[5]['cuantas'], dias[5]['sin_itbms']), (1, tarde.amount_untaxed))
        self.assertEqual((dias[6]['cuantas'], dias[6]['sin_itbms']), (1, temprano.amount_untaxed))
        dia = self.ger._del_dia(date(2025, 6, 5), 'confirmado', ana, date(2025, 7, 10))
        self.assertEqual([fila['numero'] for fila in dia['filas']], [tarde.name])
        self.assertEqual(dia['filas'][0]['detalle'], '11:30 p. m.', 'la hora de Panamá en que se confirmó')
        self.assertEqual(dia['filas'][0]['modelo'], 'sale.order')
        self.assertEqual(dia['filas'][0]['estado'], 'Por facturar')
        mes = self.ger._por_dia('2025-06', 'confirmado', ana, ahora)
        lista = self.env['sale.order'].with_user(self.gerencia).search(mes['accion']['domain'])
        self.assertEqual(lista, tarde | temprano)

    def test_mes_anterior_hasta_la_misma_hora_o_completo(self):
        """10 de julio a las 11:00: julio se compara con el 1–10 de junio, el 10 hasta las 11:00 (lo mismo que
        «Comparar › del 1 a hoy»). Junio, que ya terminó, se compara con mayo completo."""
        ana = self.vendedora.id
        self.vender(date(2025, 6, 10), time(9, 0), vendedor=self.vendedora)
        self.vender(date(2025, 6, 10), time(15, 0), vendedor=self.vendedora)
        self.vender(date(2025, 5, 20), vendedor=self.vendedora)
        self.vender(date(2025, 7, 2), vendedor=self.vendedora)
        ahora = en_panama(date(2025, 7, 10), time(11, 0))
        julio = self.ger._por_dia('2025-07', 'facturado', ana, ahora)
        self.assertTrue(julio['en_curso'])
        self.assertEqual(julio['anterior']['etiqueta'], '1–10 jun')
        self.assertEqual(julio['anterior']['sin_itbms'], 1000.0, 'el de las 3:00 p. m. todavía no')
        self.assertEqual(julio['anterior']['hora'], '11:00 a. m.')
        self.assertEqual(julio['anterior']['cambio'], 0.0)
        comparar = self.comparar('mes_a_la_fecha', ahora, vendedor=ana)
        self.assertEqual(julio['anterior']['sin_itbms'], self.filas(comparar)['ventas']['b'],
                         'lo mismo que Comparar › del 1 a hoy')
        self.assertTrue(all(d['futuro'] for d in julio['dias'] if d['numero'] > 10))
        self.assertTrue(julio['dias'][9]['hoy'])
        junio = self.ger._por_dia('2025-06', 'facturado', ana, ahora)
        self.assertEqual((junio['anterior']['etiqueta'], junio['anterior']['sin_itbms']), ('Mayo completo', 1000.0))
        self.assertEqual((junio['anterior']['cambio'], junio['anterior']['sentido']), (100.0, 'sube'))
        self.assertFalse(junio['anterior']['hora'])
        # El último día del mes, el mes sigue en curso: se compara como «Comparar › del 1 a hoy».
        fin = en_panama(date(2025, 6, 30), time(11, 0))
        junio = self.ger._por_dia('2025-06', 'facturado', ana, fin)
        self.assertTrue(junio['en_curso'])
        self.assertEqual((junio['anterior']['etiqueta'], junio['anterior']['hora']), ('1–30 may', '11:00 a. m.'))
        self.assertEqual(junio['anterior']['sin_itbms'],
                         self.filas(self.comparar('mes_a_la_fecha', fin, vendedor=ana))['ventas']['b'])

    def test_completadas_el_dia_que_se_termino_de_pagar(self):
        """Decisión de la dueña (2026-10-22): lo completado cuenta el día del pago que dejó la factura en cero. Venta
        del 3 de junio pagada en dos partes: $400 el 5 y $600 el 12 a las 11:30 p. m. de Panamá (en UTC ya es el 13).
        Cuenta el 12, no el 3 ni el 5, y el mes es el mismo de la tarjeta del Inicio en «Completadas»."""
        ana = self.vendedora.id
        _orden, factura = self.vender(date(2025, 6, 3), vendedor=self.vendedora)
        self.pagar(factura, 400.0, date(2025, 6, 5), time(10, 0))
        ultimo = self.pagar(factura, 600.0, date(2025, 6, 12), time(23, 30))
        self.assertEqual(ultimo.create_date.date(), date(2025, 6, 13), 'en UTC el pago quedó registrado el 13')
        ahora = en_panama(date(2025, 7, 10), time(11, 0))
        mes = self.ger._por_dia('2025-06', 'completadas', ana, ahora)
        dias = {d['numero']: d for d in mes['dias']}
        self.assertEqual((dias[12]['cuantas'], dias[12]['sin_itbms']), (1, 1000.0))
        self.assertEqual(sum(d['cuantas'] for d in mes['dias'] if d['numero'] != 12), 0, 'ni el 3 ni el 5 ni el 13')
        tarjeta = self.ger.ventas_del_periodo('rango', '2025-06-01', '2025-06-30', base='completadas', vendedor=ana)
        self.assertEqual(mes['total']['sin_itbms'], tarjeta['actual']['sin_itbms'], 'cuadra con el Inicio')
        facturado = {d['numero']: d for d in self.ger._por_dia('2025-06', 'facturado', ana, ahora)['dias']}
        self.assertEqual(facturado[3]['sin_itbms'], 1000.0, 'en «Facturado» sigue el día de la factura')
        dia = self.ger._del_dia(date(2025, 6, 12), 'completadas', ana, date(2025, 7, 10))
        self.assertEqual([f['id'] for f in dia['filas']], factura.ids)
        self.assertTrue(dia['filas'][0]['detalle'].startswith('Factura del 3 jun'), dia['filas'][0]['detalle'])
        self.assertEqual(dia['filas'][0]['estado'], 'Pagada')
        base = next(b for b in self.ger._bases_por_dia() if b['clave'] == 'completadas')
        self.assertEqual(base['detalle'], 'Pagadas por completo, el día que se terminó de pagar')
        self.assertEqual(next(b for b in self.ger._bases_de_ventas() if b['clave'] == 'completadas')['detalle'],
                         'Pagadas al 100 %, el día del último pago', 'el Inicio no cambia')

    def test_completadas_un_pago_revertido_deja_de_contar(self):
        """Pagada entera el 4 y ese pago se anula: ya no está completada (vuelve a deber). Se paga otra vez el 20:
        cuenta el 20. Una nota de crédito de una factura completada resta el día de la nota."""
        ana = self.vendedora.id
        ahora = en_panama(date(2025, 7, 10), time(11, 0))
        _orden, factura = self.vender(date(2025, 6, 3), vendedor=self.vendedora)
        pago = self.pagar(factura, 1000.0, date(2025, 6, 4))
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        pago.action_draft()
        pago.action_cancel()
        self.assertEqual(factura.payment_state, 'not_paid')
        mes = self.ger._por_dia('2025-06', 'completadas', ana, ahora)
        self.assertEqual(mes['total']['cuantas'], 0, 'un pago anulado no completa la venta')
        self.pagar(factura, 1000.0, date(2025, 6, 20))
        _otra, devuelta = self.vender(date(2025, 6, 3), vendedor=self.vendedora)
        self.pagar(devuelta, 1000.0, date(2025, 6, 6))
        self.nota(devuelta, date(2025, 6, 8), precio=100.0)
        dias = {d['numero']: d for d in self.ger._por_dia('2025-06', 'completadas', ana, ahora)['dias']}
        self.assertEqual((dias[4]['cuantas'], dias[20]['cuantas'], dias[20]['sin_itbms']), (0, 1, 1000.0),
                         'cuenta el día del pago nuevo')
        self.assertEqual((dias[6]['sin_itbms'], dias[8]['sin_itbms'], dias[8]['notas']), (1000.0, -100.0, 1))
        self.assertEqual(self.ger._por_dia('2025-06', 'completadas', ana, ahora)['total']['sin_itbms'],
                         self.medir(date(2025, 6, 1), date(2025, 6, 30), 'completadas', ana)['sin_itbms'])

    def test_estadisticas_cuadran_con_el_mes(self):
        """Las gráficas dicen lo mismo que el mes: las barras y las vendedoras suman el total; los tipos y lo más
        vendido salen de las mismas facturas (solo mercancía)."""
        self.vender(date(2025, 6, 3), vendedor=self.vendedora, producto=self.cama)
        self.vender(date(2025, 6, 4), vendedor=self.otra, producto=self.cama)
        _o, mueble = self.vender(date(2025, 6, 4), vendedor=self.otra)
        self.nota(mueble, date(2025, 6, 9), precio=100.0)          # devuelve el mueble: su unidad resta
        d0, d1 = date(2025, 6, 1), date(2025, 6, 30)
        for base in BASES_POR_DIA:
            with self.subTest(base=base):
                datos = self.ger._estadisticas(d0, d1, 'Junio 2025', 'rango', base, date(2025, 7, 10))
                medida = self.ger._medir_por_dia(d0, d1, base)
                self.assertEqual(datos['resumen']['sin_itbms'], medida['sin_itbms'])
                self.assertEqual(datos['barras']['por'], 'dia')
                self.assertEqual(len(datos['barras']['filas']), 30)
                self.assertAlmostEqual(sum(f['sin_itbms'] for f in datos['barras']['filas']),
                                       medida['sin_itbms'], places=2)
                self.assertAlmostEqual(sum(f['sin_itbms'] for f in datos['vendedoras']), medida['sin_itbms'],
                                       places=2, msg='las vendedoras suman el total')
                self.assertAlmostEqual(sum(f['unidades'] for f in datos['tipos']), datos['resumen']['unidades'],
                                       places=2)
        datos = self.ger._estadisticas(d0, d1, 'Junio 2025', 'rango', 'facturado', date(2025, 7, 10))
        cama = next(p for p in datos['productos'] if p['id'] == self.cama.product_tmpl_id.id)
        self.assertEqual((cama['unidades'], cama['sin_itbms']), (2.0, 1000.0))
        self.assertNotIn(self.mueble.product_tmpl_id.id, [p['id'] for p in datos['productos']],
                         'vendido y devuelto: no está entre lo más vendido')
        nombres = [v['nombre'] for v in datos['vendedoras']]
        self.assertLess(nombres.index(self.otra.name), nombres.index(self.vendedora.name), 'de más a menos')
        anio = self.ger._estadisticas(date(2025, 1, 1), date(2025, 7, 10), 'Este año', 'anio', 'facturado',
                                      date(2025, 7, 10))
        self.assertEqual(anio['barras']['por'], 'mes', 'periodos largos: una barra por mes')
        self.assertEqual([f['clave'] for f in anio['barras']['filas']][-2:], ['2025-06', '2025-07'])
        junio = next(f for f in anio['barras']['filas'] if f['clave'] == '2025-06')
        self.assertAlmostEqual(junio['sin_itbms'], self.medir(d0, d1, 'facturado')['sin_itbms'], places=2)

    def test_los_periodos_de_estadisticas(self):
        hoy = date(2026, 10, 22)
        rango = self.ger._rango_estadisticas
        self.assertEqual(rango('semana', None, None, hoy)[:2], (date(2026, 10, 19), hoy))
        self.assertEqual(rango('mes', None, None, hoy)[:2], (date(2026, 10, 1), hoy))
        self.assertEqual(rango('mes_pasado', None, None, hoy), (date(2026, 9, 1), date(2026, 9, 30), 'Septiembre 2026'))
        self.assertEqual(rango('tres_meses', None, None, hoy)[:2], (date(2026, 8, 1), hoy))
        self.assertEqual(rango('anio', None, None, hoy)[:2], (date(2026, 1, 1), hoy))
        with self.assertRaises(UserError):
            rango('siempre', None, None, hoy)

    def test_solo_gerencia_y_administradores(self):
        for usuario in (self.vendedora, self.otra):
            Tablero = self.env['dcasa.tablero'].with_user(usuario)
            for metodo, argumentos in (('por_dia', ()), ('ventas_del_dia', ('2025-06-03',)),
                                       ('estadisticas', ('mes',)), ('opciones_por_dia', ())):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    getattr(Tablero, metodo)(*argumentos)
        self.assertTrue(self.ger.opciones_por_dia()['bases'])
        admin = self.env.ref('base.user_admin')
        self.assertEqual(self.env['dcasa.tablero'].with_user(admin).por_dia(base='confirmado')['base'], 'confirmado')

    def test_los_menus_son_de_gerencia(self):
        propios = {'dcasa_interfaz.menu_dcasa_ventas_por_dia', 'dcasa_interfaz.menu_dcasa_facturado_por_dia',
                   'dcasa_interfaz.menu_estadisticas_resumen', 'dcasa_interfaz.menu_estadisticas_por_dia'}

        def menus(usuario):
            datos = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
            return {m['xmlid'] for m in datos.values() if isinstance(m, dict) and m.get('xmlid')}

        self.assertTrue(propios <= menus(self.gerencia))
        self.assertFalse(propios & menus(self.vendedora))

    def test_el_servidor_valida_cada_dato(self):
        with self.assertRaises(UserError):
            self.ger.por_dia(base='todo')
        with self.assertRaises(UserError):
            self.ger.por_dia(mes='1999-01')
        with self.assertRaises(UserError):
            self.ger.por_dia(mes='2026-13')
        with self.assertRaises(UserError):
            self.ger.ventas_del_dia('3000-01-01')
        with self.assertRaises(UserError):
            self.ger.ventas_del_dia('no es fecha')
        with self.assertRaises(UserError):
            self.ger.ventas_del_dia('2000-01-01')
        with self.assertRaises(UserError):
            self.ger.estadisticas('rango', '2026-10-05', '2026-10-01')
        with self.assertRaises(UserError):
            self.ger.por_dia(vendedor='nadie')
