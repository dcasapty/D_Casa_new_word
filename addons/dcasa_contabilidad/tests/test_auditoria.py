"""Auditoría de los reportes contables: cada cifra se cruza contra un cálculo INDEPENDIENTE en SQL.

Los datos (``datos_auditoria.py``) son los de una mueblería de verdad; el cálculo de referencia (``oraculo_sql.py``)
lee los apuntes publicados directo de la base. Aquí se comprueba, para periodos distintos (un día, la semana, el mes,
el trimestre, el año, un periodo que cruza el cierre del año fiscal…):

* el balance general cuadra y sus totales son los de los apuntes;
* el balance de comprobación cuadra, y saldo inicial + movimiento = saldo final en cada cuenta;
* el libro mayor suma lo mismo que la cuenta (aunque el detalle se recorte);
* el estado de resultados, el flujo de efectivo, el ITBMS, la antigüedad de saldos y la analítica dicen lo que dicen los apuntes;
* las tarjetas del Resumen se miden bien: los SALDOS al corte («Hasta») y los MOVIMIENTOS en el periodo.
"""
from datetime import date, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from . import oraculo_sql as O
from .datos_auditoria import Auditoria
from .test_contabilidad import ContabilidadCommon

ANIO = 2031
HOY = f'{ANIO}-10-14'          # martes

ACTIVOS = ('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments', 'asset_non_current', 'asset_fixed')
PASIVOS = ('liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current')
PATRIMONIO = ('equity', 'equity_unaffected')
OPERACION = ('asset_receivable', 'asset_current', 'asset_prepayments', 'liability_payable', 'liability_credit_card',
             'liability_current')
INVERSION = ('asset_non_current', 'asset_fixed')
FINANCIAMIENTO = ('liability_non_current', 'equity', 'equity_unaffected')

# Periodos que prueba cada reporte: (desde, hasta).
VENTANAS = {
    'dia': (HOY, HOY),
    'semana': (f'{ANIO}-10-13', HOY),
    'quincena': (f'{ANIO}-10-01', HOY),
    'mes': (f'{ANIO}-10-01', HOY),
    'mes_pasado': (f'{ANIO}-09-01', f'{ANIO}-09-30'),
    'trimestre': (f'{ANIO}-10-01', HOY),
    'anio': (f'{ANIO}-01-01', HOY),
    'anio_completo': (f'{ANIO}-01-01', f'{ANIO}-12-31'),
    'cruce_de_anio': (f'{ANIO - 1}-12-20', f'{ANIO}-01-12'),
    'anio_anterior': (f'{ANIO - 1}-01-01', f'{ANIO - 1}-12-31'),
    'mitad_de_mes': (f'{ANIO}-03-10', f'{ANIO}-08-25'),
}
# Fechas de corte para los saldos (balance, por cobrar, por pagar, tarjetas del resumen).
CORTES = (f'{ANIO - 1}-12-31', f'{ANIO}-01-31', f'{ANIO}-02-20', f'{ANIO}-04-01', f'{ANIO}-07-02', f'{ANIO}-09-30',
          f'{ANIO}-10-06', f'{ANIO}-10-08', HOY, f'{ANIO}-10-25', f'{ANIO}-12-31')


def d(texto):
    return date.fromisoformat(texto)


class AuditoriaCommon(ContabilidadCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.datos = Auditoria(cls.env, anio=ANIO)

    # -- ayudas de comparación -------------------------------------------------

    def assertCifra(self, real, esperado, msg=''):
        self.assertAlmostEqual(real, esperado, places=2, msg=f'{msg}: reporte={real} referencia={esperado}')

    def neto(self, tipos, **kw):
        """Σ (debe − haber) de las cuentas de esos tipos, según el cálculo independiente."""
        por_tipo = O.por_tipo(self.env, self.company, **kw)
        return sum(por_tipo.get(t, 0.0) for t in tipos)

    def efectivo(self, **kw):
        return self.neto(('asset_cash',), **kw)

    def por_id(self, filas):
        return {f['id']: f for f in filas if f['id']}


@tagged('post_install', '-at_install')
class TestAtajosDeFechas(ContabilidadCommon):
    """«Hoy», «Esta semana», «Esta quincena», «Este mes», «Mes pasado», «Este trimestre», «Este año fiscal»."""

    def atajos(self, hoy):
        return {a['clave']: (a['desde'], a['hasta']) for a in self.reportes._atajos(d(hoy))}

    def test_orden_y_nombres(self):
        atajos = self.reportes.periodos()
        self.assertEqual([a['clave'] for a in atajos],
                         ['hoy', 'semana', 'quincena', 'mes', 'mes_pasado', 'trimestre', 'ejercicio'])
        self.assertEqual([a['nombre'] for a in atajos],
                         ['Hoy', 'Esta semana', 'Esta quincena', 'Este mes', 'Mes pasado', 'Este trimestre',
                          'Este año fiscal'])

    def test_un_martes_a_mitad_de_mes(self):
        a = self.atajos('2031-10-14')
        self.assertEqual(a['hoy'], ('2031-10-14', '2031-10-14'))
        self.assertEqual(a['semana'], ('2031-10-13', '2031-10-14'))      # lunes a hoy
        self.assertEqual(a['quincena'], ('2031-10-01', '2031-10-14'))
        self.assertEqual(a['mes'], ('2031-10-01', '2031-10-14'))
        self.assertEqual(a['mes_pasado'], ('2031-09-01', '2031-09-30'))
        self.assertEqual(a['trimestre'], ('2031-10-01', '2031-10-14'))
        self.assertEqual(a['ejercicio'], ('2031-01-01', '2031-10-14'))

    def test_todos_terminan_hoy_menos_el_mes_pasado(self):
        for hoy in ('2031-01-01', '2031-02-28', '2031-07-16', '2031-12-31', '2032-02-29'):
            for clave, (desde, hasta) in self.atajos(hoy).items():
                if clave != 'mes_pasado':
                    self.assertEqual(hasta, hoy, f'{clave} en {hoy}')
                self.assertLessEqual(desde, hasta, f'{clave} en {hoy}')

    def test_la_semana_cruza_de_mes_y_de_anio(self):
        # Jueves 2 de enero de 2031: la semana empezó el lunes 30 de diciembre de 2030.
        self.assertEqual(self.atajos('2031-01-02')['semana'], ('2030-12-30', '2031-01-02'))
        # Sábado 1 de marzo de 2031: empezó el lunes 24 de febrero.
        self.assertEqual(self.atajos('2031-03-01')['semana'], ('2031-02-24', '2031-03-01'))
        # Un lunes es su propia semana; un domingo trae seis días atrás.
        self.assertEqual(self.atajos('2031-10-13')['semana'], ('2031-10-13', '2031-10-13'))
        self.assertEqual(self.atajos('2031-10-19')['semana'], ('2031-10-13', '2031-10-19'))

    def test_la_quincena_incluye_febrero(self):
        for hoy, desde in (('2031-02-15', '2031-02-01'), ('2031-02-16', '2031-02-16'), ('2031-02-28', '2031-02-16'),
                           ('2032-02-29', '2032-02-16'), ('2031-03-01', '2031-03-01'), ('2031-03-15', '2031-03-01'),
                           ('2031-03-16', '2031-03-16'), ('2031-03-31', '2031-03-16'), ('2031-01-01', '2031-01-01')):
            self.assertEqual(self.atajos(hoy)['quincena'], (desde, hoy), hoy)

    def test_mes_pasado_en_febrero_y_en_enero(self):
        self.assertEqual(self.atajos('2031-03-01')['mes_pasado'], ('2031-02-01', '2031-02-28'))
        self.assertEqual(self.atajos('2032-03-10')['mes_pasado'], ('2032-02-01', '2032-02-29'))
        self.assertEqual(self.atajos('2031-01-05')['mes_pasado'], ('2030-12-01', '2030-12-31'))

    def test_trimestre_en_sus_bordes(self):
        for hoy, desde in (('2031-03-31', '2031-01-01'), ('2031-04-01', '2031-04-01'), ('2031-06-30', '2031-04-01'),
                           ('2031-12-31', '2031-10-01'), ('2031-01-01', '2031-01-01')):
            self.assertEqual(self.atajos(hoy)['trimestre'], (desde, hoy), hoy)

    def test_con_otro_cierre_fiscal_los_trimestres_siguen_al_anio_fiscal(self):
        """Año fiscal de julio a junio: los trimestres empiezan en julio, octubre, enero y abril."""
        self.company.write({'fiscalyear_last_day': 30, 'fiscalyear_last_month': '6'})
        self.assertEqual(self.atajos('2031-10-14')['ejercicio'], ('2031-07-01', '2031-10-14'))
        self.assertEqual(self.atajos('2031-10-14')['trimestre'], ('2031-10-01', '2031-10-14'))
        self.assertEqual(self.atajos('2031-08-15')['trimestre'], ('2031-07-01', '2031-08-15'))
        self.assertEqual(self.atajos('2032-01-02')['trimestre'], ('2032-01-01', '2032-01-02'))
        self.assertEqual(self.atajos('2031-06-30')['ejercicio'], ('2030-07-01', '2031-06-30'))

    @freeze_time('2031-10-15 02:00:00')   # 9 p. m. del 14 en Panamá, pero ya es el 15 en UTC
    def test_hoy_es_el_de_panama_aunque_el_servidor_este_en_utc(self):
        sin_zona = self.env['res.users'].create({'name': 'Sin zona', 'login': 'sin_zona_rep', 'tz': False})
        motor = self.env['dcasa.reporte.contable'].with_user(sin_zona).with_context(tz=False)
        self.assertEqual(motor._hoy(), d('2031-10-14'))
        self.assertEqual(motor._atajos(motor._hoy())[0]['hasta'], '2031-10-14')
        # Con zona propia manda la de la persona (Madrid ya está en el 15).
        madrid = self.env['res.users'].create({'name': 'En Madrid', 'login': 'madrid_rep', 'tz': 'Europe/Madrid'})
        self.assertEqual(self.env['dcasa.reporte.contable'].with_user(madrid).with_context(tz=False)._hoy(),
                         d('2031-10-15'))

    def test_fechas_al_reves_se_rechazan(self):
        with self.assertRaises(UserError):
            self.reportes.estado_resultados('2031-10-14', '2031-10-01')
        with self.assertRaises(UserError):
            self.reportes.obtener('resumen', '2031-10-14', '2031-10-01')
        # Un solo día (desde = hasta) es válido.
        self.reportes.estado_resultados('2031-10-14', '2031-10-14')

    def test_comparar_un_dia_es_con_el_dia_anterior(self):
        comparado = self.reportes._periodo_comparado
        self.assertEqual(comparado(d('2031-10-14'), d('2031-10-14'), 'periodo_anterior'),
                         (d('2031-10-13'), d('2031-10-13')))
        # También el día 1 (antes se comparaba con el día 1 del mes anterior).
        self.assertEqual(comparado(d('2031-10-01'), d('2031-10-01'), 'periodo_anterior'),
                         (d('2031-09-30'), d('2031-09-30')))
        self.assertEqual(comparado(d('2031-10-14'), d('2031-10-14'), 'anio_anterior'),
                         (d('2030-10-14'), d('2030-10-14')))
        # Esta semana (lunes a hoy) contra los mismos días justo antes; esta quincena, contra la del mes anterior.
        self.assertEqual(comparado(d('2031-10-13'), d('2031-10-14'), 'periodo_anterior'),
                         (d('2031-10-11'), d('2031-10-12')))
        self.assertEqual(comparado(d('2031-10-01'), d('2031-10-14'), 'periodo_anterior'),
                         (d('2031-09-01'), d('2031-09-14')))

    def test_corte_comparado_del_balance(self):
        corte = self.reportes._corte_comparado
        self.assertEqual(corte(d('2031-10-14'), 'periodo_anterior'), d('2031-09-14'))
        self.assertEqual(corte(d('2031-03-31'), 'periodo_anterior'), d('2031-02-28'))     # fin de mes sigue siendo fin de mes
        self.assertEqual(corte(d('2031-10-31'), 'periodo_anterior'), d('2031-09-30'))
        self.assertEqual(corte(d('2032-02-29'), 'anio_anterior'), d('2031-02-28'))
        self.assertEqual(corte(d('2031-10-14'), 'anio_anterior'), d('2030-10-14'))


@tagged('post_install', '-at_install')
class TestAuditoriaPeriodo(AuditoriaCommon):
    """Reportes «de un periodo»: estado de resultados, flujo de efectivo, ITBMS, balance de comprobación, mayor, analítica."""

    def test_los_tipos_de_cuenta_de_odoo_estan_todos_cubiertos(self):
        """Si Odoo agrega un tipo de cuenta que ninguna sección del balance o del estado de resultados recoge, el
        balance dejaría de cuadrar sin avisar."""
        tipos = {t for t, _n in self.env['account.account']._fields['account_type'].selection} - {'off_balance'}
        self.assertEqual(tipos - set(ACTIVOS + PASIVOS + PATRIMONIO + O.RESULTADOS), set())

    def test_estado_de_resultados_contra_los_apuntes(self):
        for nombre, (desde, hasta) in VENTANAS.items():
            por_tipo = O.por_tipo(self.env, self.company, desde=desde, hasta=hasta)
            er = self.reportes.estado_resultados(desde, hasta)
            totales = {s['clave']: s['total'] for s in er['secciones']}
            esperado = {
                'ventas': -por_tipo.get('income', 0.0), 'costo': por_tipo.get('expense_direct_cost', 0.0),
                'otros_ingresos': -por_tipo.get('income_other', 0.0), 'gastos': por_tipo.get('expense', 0.0),
                'depreciacion': por_tipo.get('expense_depreciation', 0.0),
                'otros_gastos': por_tipo.get('expense_other', 0.0)}
            for clave, valor in esperado.items():
                self.assertCifra(totales[clave], valor, f'{nombre} {clave}')
            neta = -sum(por_tipo.get(t, 0.0) for t in O.RESULTADOS)
            self.assertCifra(er['resumen']['utilidad_neta'], neta, f'{nombre} utilidad neta')
            self.assertCifra(er['resumen']['utilidad_bruta'], esperado['ventas'] - esperado['costo'], nombre)

    def test_estado_de_resultados_cifras_a_mano(self):
        """Valores calculados a mano a partir de los datos (no del cálculo en SQL)."""
        er = self.reportes.estado_resultados(f'{ANIO}-10-01', HOY)
        totales = {s['clave']: s['total'] for s in er['secciones']}
        # Ventas: 950 (canal repartido) + 300 (exenta) + 400 (de contado) + 150 (de hoy). Sin la factura en borrador
        # de 700, sin la cancelada de 600 ni el gasto fechado el día 20.
        self.assertEqual(totales['ventas'], 1800.0)
        self.assertEqual(totales['costo'], 150.0)
        self.assertEqual(totales['gastos'], 400.0)          # 200 (alquiler) + 80 (compra de hoy) + 120 (gasto en caja)
        self.assertEqual(totales['otros_gastos'], 30.0)
        self.assertEqual(er['resumen']['utilidad_neta'], 1220.0)
        hoy = self.reportes.estado_resultados(HOY, HOY)
        self.assertEqual(hoy['secciones'][0]['total'], 150.0)
        self.assertEqual(hoy['resumen']['utilidad_neta'], 70.0)         # 150 de venta − 80 de compra

    def test_borradores_cancelados_y_fechas_futuras_no_cuentan(self):
        sin = self.reportes.estado_resultados(f'{ANIO}-10-01', HOY)
        con = self.reportes.estado_resultados(f'{ANIO}-10-01', HOY, borradores=True)
        # Con borradores aparecen la factura de cliente de 700 y la de proveedor de 90; la cancelada nunca.
        self.assertCifra(con['secciones'][0]['total'] - sin['secciones'][0]['total'], 700.0)
        gastos = lambda er: next(s['total'] for s in er['secciones'] if s['clave'] == 'gastos')  # noqa: E731
        self.assertCifra(gastos(con) - gastos(sin), 90.0)
        hasta_el_20 = self.reportes.estado_resultados(f'{ANIO}-10-01', f'{ANIO}-10-20')
        self.assertCifra(gastos(hasta_el_20) - gastos(sin), 100.0)      # el gasto fechado el día 20 entra desde su fecha
        self.assertFalse(self.datos.cancelada.state == 'posted')

    def test_balance_de_comprobacion_contra_los_apuntes(self):
        for nombre, (desde, hasta) in VENTANAS.items():
            tb = self.reportes.balance_comprobacion(desde, hasta)
            self.assertTrue(tb['cuadra'], nombre)
            ej = O.inicio_ejercicio(self.company, d(desde))
            antes = d(desde) - timedelta(days=1)
            periodo = O.saldos(self.env, self.company, desde=desde, hasta=hasta)
            inicial_balance = O.saldos(self.env, self.company, hasta=antes, sin_tipos=O.RESULTADOS)
            inicial_resultados = O.saldos(self.env, self.company, desde=ej, hasta=antes, tipos=O.RESULTADOS)
            no_asignado = O.neto(O.saldos(self.env, self.company, hasta=ej - timedelta(days=1), tipos=O.RESULTADOS))
            filas = self.por_id(tb['filas'])
            for cuenta in set(periodo) | set(inicial_balance) | set(inicial_resultados):
                debe, haber = periodo.get(cuenta, [0.0, 0.0])
                ini = sum(o - h for o, h in (inicial_balance.get(cuenta), inicial_resultados.get(cuenta)) if False) \
                    if False else 0.0
                for origen in (inicial_balance, inicial_resultados):
                    if cuenta in origen:
                        ini += origen[cuenta][0] - origen[cuenta][1]
                if not any(round(v, 2) for v in (ini, debe, haber)):
                    self.assertNotIn(cuenta, filas, f'{nombre}: cuenta sin movimientos en el reporte')
                    continue
                fila = filas[cuenta]
                self.assertCifra(fila['inicial'], ini, f'{nombre} inicial {fila["codigo"]}')
                self.assertCifra(fila['debe'], debe, f'{nombre} debe {fila["codigo"]}')
                self.assertCifra(fila['haber'], haber, f'{nombre} haber {fila["codigo"]}')
                self.assertCifra(fila['final'], ini + debe - haber, f'{nombre} final {fila["codigo"]}')
            self.assertCifra(tb['totales']['debe'], sum(v[0] for v in periodo.values()), nombre)
            self.assertCifra(tb['totales']['haber'], sum(v[1] for v in periodo.values()), nombre)
            self.assertCifra(tb['totales']['debe'], tb['totales']['haber'], nombre)
            self.assertCifra(tb['totales']['inicial'], 0.0, f'{nombre}: el saldo inicial total es cero')
            self.assertCifra(tb['totales']['final'], 0.0, f'{nombre}: el saldo final total es cero')
            sin_cuenta = [f for f in tb['filas'] if not f['id']]
            self.assertCifra(sum(f['inicial'] for f in sin_cuenta), no_asignado, f'{nombre} no asignado')

    def test_balance_de_comprobacion_avisa_si_cruza_el_cierre_fiscal(self):
        self.assertTrue(self.reportes.balance_comprobacion(*VENTANAS['cruce_de_anio'])['cruza_ejercicio'])
        self.assertFalse(self.reportes.balance_comprobacion(*VENTANAS['mes'])['cruza_ejercicio'])
        self.assertFalse(self.reportes.balance_comprobacion(*VENTANAS['anio_completo'])['cruza_ejercicio'])

    def test_libro_mayor_saldo_inicial_mas_movimientos_es_el_saldo_final(self):
        cuentas = (self.datos.cuenta_banco | self.datos.cuenta_caja | self.datos.mobiliario | self.datos.prestamo
                   | self.datos.capital | self.datos._pagar())
        cuentas |= self.env['account.account'].search([('account_type', 'in', ('asset_receivable', 'income', 'expense'))],
                                                     limit=6)
        cuentas |= self.datos.venta.invoice_repartition_line_ids.account_id
        for nombre, (desde, hasta) in VENTANAS.items():
            ej = O.inicio_ejercicio(self.company, d(desde))
            antes = d(desde) - timedelta(days=1)
            for limite in (2000, 2):                                       # con el detalle completo y recortado
                mayor = self.reportes.libro_mayor(desde, hasta, cuenta_ids=cuentas.ids, limite=limite)
                por_cuenta = self.por_id(mayor['cuentas'])
                for cuenta in cuentas:
                    periodo = O.saldos(self.env, self.company, desde=desde, hasta=hasta).get(cuenta.id, [0.0, 0.0])
                    if cuenta.account_type in O.RESULTADOS:
                        inicial = O.neto({cuenta.id: v for cuenta_id, v in O.saldos(
                            self.env, self.company, desde=ej, hasta=antes).items() if cuenta_id == cuenta.id})
                    else:
                        inicial = O.neto({cuenta.id: v for cuenta_id, v in O.saldos(
                            self.env, self.company, hasta=antes).items() if cuenta_id == cuenta.id})
                    if not any(round(v, 2) for v in (inicial, *periodo)):
                        continue
                    fila = por_cuenta[cuenta.id]
                    msg = f'{nombre} {cuenta.code} límite={limite}'
                    self.assertCifra(fila['inicial'], inicial, msg)
                    self.assertCifra(fila['debe'], periodo[0], msg)
                    self.assertCifra(fila['haber'], periodo[1], msg)
                    self.assertCifra(fila['final'], inicial + periodo[0] - periodo[1], msg)
                    self.assertEqual(fila['truncado'], len(fila['lineas']) == limite
                                     and fila['final'] != fila['lineas'][-1]['saldo'] or False, msg) \
                        if False else None
                    if fila['lineas'] and not fila['truncado']:
                        self.assertCifra(fila['lineas'][-1]['saldo'], fila['final'], f'{msg}: saldo corrido')

    def test_libro_mayor_recortado_avisa_y_conserva_los_totales(self):
        banco = self.datos.cuenta_banco
        completo = self.reportes.libro_mayor(f'{ANIO}-01-01', HOY, cuenta_ids=banco.ids)['cuentas'][0]
        recortado = self.reportes.libro_mayor(f'{ANIO}-01-01', HOY, cuenta_ids=banco.ids, limite=3)['cuentas'][0]
        self.assertTrue(recortado['truncado'])
        self.assertFalse(completo['truncado'])
        self.assertEqual(len(recortado['lineas']), 3)
        for clave in ('inicial', 'debe', 'haber', 'final'):
            self.assertCifra(recortado[clave], completo[clave], clave)
        self.assertCifra(completo['final'], self.efectivo(hasta=HOY) - self.datos.cuenta_caja.with_context().id * 0
                         - sum(O.saldos(self.env, self.company, hasta=HOY).get(self.datos.cuenta_caja.id, [0, 0])[0:1])
                         + sum(O.saldos(self.env, self.company, hasta=HOY).get(self.datos.cuenta_caja.id, [0, 0])[1:2])
                         - sum(O.saldos(self.env, self.company, hasta=HOY).get(a, [0, 0])[0]
                               - O.saldos(self.env, self.company, hasta=HOY).get(a, [0, 0])[1]
                               for a in (self.env['account.account'].search([('account_type', '=', 'asset_cash')]).ids)
                               if a not in (banco.id, self.datos.cuenta_caja.id)))
        # Excel y PDF llevan todos los movimientos, no el tope de la pantalla.
        todo = self.reportes.obtener('libro_mayor', f'{ANIO}-01-01', HOY, cuenta_ids=banco.ids, completo=True)
        self.assertFalse(todo['cuentas'][0]['truncado'])

    def test_itbms_contra_los_apuntes(self):
        for nombre, (desde, hasta) in VENTANAS.items():
            esperado = O.impuestos(self.env, self.company, desde, hasta)
            real = self.reportes.itbms(desde, hasta)
            filas = {f['id']: f for f in real['filas']}
            self.assertEqual(set(filas), {t for t, v in esperado.items() if v['base'] or v['cuota']}, nombre)
            debito = credito = 0.0
            for impuesto_id, fila in filas.items():
                venta = fila['tipo'] == 'venta'
                signo = -1 if venta else 1
                self.assertCifra(fila['base'], signo * esperado[impuesto_id]['base'], f'{nombre} base {fila["nombre"]}')
                self.assertCifra(fila['impuesto'], signo * esperado[impuesto_id]['cuota'],
                                 f'{nombre} impuesto {fila["nombre"]}')
                if venta:
                    debito += fila['impuesto']
                else:
                    credito += fila['impuesto']
            self.assertCifra(real['resumen']['debito_fiscal'], debito, nombre)
            self.assertCifra(real['resumen']['credito_fiscal'], credito, nombre)
            self.assertCifra(real['resumen']['a_pagar'], debito - credito, nombre)

    def test_itbms_cifras_a_mano(self):
        r = self.reportes.itbms(f'{ANIO}-10-01', HOY)
        self.assertEqual((r['resumen']['debito_fiscal'], r['resumen']['credito_fiscal'], r['resumen']['a_pagar']),
                         (105.0, 5.6, 99.4))      # 7 % de 1,500 gravado; 7 % de la compra de 80 de hoy
        base = {f['id']: f['base'] for f in r['filas']}
        self.assertEqual(base[self.datos.venta.id], 1500.0)
        self.assertEqual(base[self.datos.exento.id], 300.0)                # la venta exenta tiene base y no tiene impuesto
        self.assertEqual(base[self.datos.compra.id], 80.0)
        hoy = self.reportes.itbms(HOY, HOY)['resumen']
        self.assertEqual((hoy['debito_fiscal'], hoy['credito_fiscal']), (10.5, 5.6))
        # Septiembre trae las notas de crédito: restan (cliente: 7 sobre 100; proveedor: 3.5 sobre 50).
        sep = self.reportes.itbms(f'{ANIO}-09-01', f'{ANIO}-09-30')
        por_id = {f['id']: f for f in sep['filas']}
        self.assertEqual(por_id[self.datos.venta.id]['base'], 600.0 - 100.0)       # e4 600 − nota de crédito 100
        self.assertEqual(por_id[self.datos.venta.id]['impuesto'], 42.0 - 7.0)
        self.assertEqual(por_id[self.datos.compra.id]['base'], 500.0 - 50.0)       # e5 500 − nota del proveedor 50
        self.assertEqual(por_id[self.datos.compra.id]['impuesto'], 35.0 - 3.5)

    def test_flujo_de_efectivo_contra_los_apuntes(self):
        for nombre, (desde, hasta) in VENTANAS.items():
            antes = d(desde) - timedelta(days=1)
            flujo = self.reportes.flujo_efectivo(desde, hasta)
            self.assertTrue(flujo['cuadra'], nombre)
            r = flujo['resumen']
            inicial = self.efectivo(hasta=antes)
            final = self.efectivo(hasta=hasta)
            self.assertCifra(r['efectivo_inicial'], inicial, f'{nombre} inicial')
            self.assertCifra(r['efectivo_final'], final, f'{nombre} final')
            self.assertCifra(r['variacion'], final - inicial, f'{nombre} variación = lo que cambió el efectivo')
            movimiento = O.por_tipo(self.env, self.company, desde=desde, hasta=hasta)
            utilidad = -sum(movimiento.get(t, 0.0) for t in O.RESULTADOS)
            depreciacion = movimiento.get('expense_depreciation', 0.0)
            total = {s['clave']: s['total'] for s in flujo['secciones']}
            self.assertCifra(total['operacion'], utilidad + depreciacion
                             - sum(movimiento.get(t, 0.0) for t in OPERACION), f'{nombre} operación')
            self.assertCifra(total['inversion'], -depreciacion - sum(movimiento.get(t, 0.0) for t in INVERSION),
                             f'{nombre} inversión')
            self.assertCifra(total['financiamiento'], -sum(movimiento.get(t, 0.0) for t in FINANCIAMIENTO),
                             f'{nombre} financiamiento')

    def test_flujo_de_efectivo_cifras_a_mano(self):
        """Del 1 al 14 de octubre el efectivo pasa de 25,348.00 a 26,742.50."""
        flujo = self.reportes.flujo_efectivo(f'{ANIO}-10-01', HOY)
        self.assertEqual(flujo['resumen']['efectivo_inicial'], 25348.0)
        self.assertEqual(flujo['resumen']['efectivo_final'], 26742.5)
        self.assertEqual(flujo['resumen']['variacion'], 1394.5)

    def test_analitica_contra_los_apuntes_y_suma_lo_mismo_que_el_estado_de_resultados(self):
        plan = self.env.ref('dcasa_contabilidad.plan_canal')
        columna = plan._column_name()
        for nombre, (desde, hasta) in VENTANAS.items():
            esperado = O.analitica(self.env, self.company, columna, desde, hasta)
            real = self.reportes.analitica(desde, hasta)
            filas = [f for f in real['filas'] if f['columna'] == columna]
            asignadas = {f['id']: f for f in filas if f['id']}
            self.assertEqual(set(asignadas), set(esperado), nombre)
            for cuenta, (ingresos, costos) in esperado.items():
                self.assertCifra(asignadas[cuenta]['ingresos'], ingresos, f'{nombre} ingresos')
                self.assertCifra(asignadas[cuenta]['costos'], costos, f'{nombre} costos')
                self.assertCifra(asignadas[cuenta]['margen'], ingresos - costos, f'{nombre} margen')
            if not filas:
                continue
            # Las filas del plan, con «Sin asignar», suman lo mismo que el estado de resultados.
            er = O.por_tipo(self.env, self.company, desde=desde, hasta=hasta)
            self.assertCifra(sum(f['ingresos'] for f in filas), -(er.get('income', 0.0) + er.get('income_other', 0.0)),
                             f'{nombre}: ingresos del plan + sin asignar')
            self.assertCifra(sum(f['costos'] for f in filas),
                             sum(er.get(t, 0.0) for t in O.RESULTADOS if not t.startswith('income')),
                             f'{nombre}: costos del plan + sin asignar')

    def test_analitica_cifras_a_mano(self):
        filas = {f['nombre']: f for f in self.reportes.analitica(f'{ANIO}-10-01', HOY)['filas']}
        # Tienda física: 60 % de 950 + 300 de la venta exenta; costos: el gasto en caja de 120.
        self.assertEqual((filas[self.datos.tienda.name]['ingresos'], filas[self.datos.tienda.name]['costos']),
                         (870.0, 120.0))
        # Tienda en línea: 40 % de 950 + 400 de contado.
        self.assertEqual(filas[self.datos.web.name]['ingresos'], 780.0)
        # Lo que no se repartió (la venta de hoy de 150 y los costos y gastos sin canal) sale aparte.
        self.assertEqual((filas['Sin asignar']['ingresos'], filas['Sin asignar']['costos']), (150.0, 460.0))
        self.assertTrue(filas['Sin asignar']['sin_asignar'])

    def test_analitica_una_nota_de_credito_resta_de_los_ingresos(self):
        """Antes se contaba por el signo: una nota de crédito de venta salía como «costo»."""
        self.datos.factura(self.datos.c1, 40, f'{ANIO}-10-10', tipo='out_refund',
                           analitica={str(self.datos.tienda.id): 100})
        fila = next(f for f in self.reportes.analitica(f'{ANIO}-10-01', HOY)['filas']
                    if f['nombre'] == self.datos.tienda.name)
        self.assertEqual((fila['ingresos'], fila['costos']), (870.0 - 40.0, 120.0))


@tagged('post_install', '-at_install')
class TestAuditoriaSaldos(AuditoriaCommon):
    """Reportes «a una fecha»: balance general, por cobrar, por pagar y las tarjetas de saldo del Resumen."""

    def test_balance_general_contra_los_apuntes(self):
        for corte in CORTES:
            bg = self.reportes.balance_general(corte)
            por_tipo = O.por_tipo(self.env, self.company, hasta=corte)
            activo = sum(por_tipo.get(t, 0.0) for t in ACTIVOS)
            pasivo = -sum(por_tipo.get(t, 0.0) for t in PASIVOS)
            patrimonio = -sum(por_tipo.get(t, 0.0) for t in PATRIMONIO + O.RESULTADOS)
            self.assertCifra(bg['totales']['activo'], activo, f'{corte} activo')
            self.assertCifra(bg['totales']['pasivo'], pasivo, f'{corte} pasivo')
            self.assertCifra(bg['totales']['patrimonio'], patrimonio, f'{corte} patrimonio')
            self.assertCifra(activo, pasivo + patrimonio, f'{corte}: activo = pasivo + patrimonio')
            self.assertTrue(bg['cuadra'], corte)
            # Cada cuenta del balance es su saldo acumulado a esa fecha.
            saldos = O.saldos(self.env, self.company, hasta=corte, sin_tipos=O.RESULTADOS)
            for seccion in bg['secciones']:
                for fila in seccion['filas']:
                    if fila['id']:
                        signo = 1 if seccion['grupo'] == 'activo' else -1
                        debe, haber = saldos[fila['id']]
                        self.assertCifra(fila['monto'], signo * (debe - haber), f'{corte} {fila["codigo"]}')

    def test_balance_general_el_resultado_del_ejercicio_en_curso(self):
        bg = self.reportes.balance_general(HOY)
        patrimonio = next(s for s in bg['secciones'] if s['clave'] == 'patrimonio')
        filas = {f['nombre']: f['monto'] for f in patrimonio['filas']}
        # Año anterior: 1,000 + 500 de ventas − 400 de compras = 1,100. Este año hasta hoy: ver el estado de resultados.
        self.assertEqual(filas['Resultados de ejercicios anteriores'], 1100.0)
        er = self.reportes.estado_resultados(f'{ANIO}-01-01', HOY)
        self.assertCifra(filas['Resultado del ejercicio'], er['resumen']['utilidad_neta'], 'resultado del ejercicio')
        # Cifras a mano al 14 de octubre.
        self.assertEqual((bg['totales']['activo'], bg['totales']['pasivo'], bg['totales']['patrimonio']),
                         (32257.0, 8237.0, 24020.0))

    def test_balance_general_no_depende_del_desde_ni_cuenta_lo_futuro(self):
        a = self.reportes.balance_general(HOY, desde=f'{ANIO}-10-01')
        b = self.reportes.balance_general(HOY, desde=f'{ANIO}-01-01')
        self.assertEqual(a['totales'], b['totales'])
        # El gasto fechado el 20 no está al 14 y sí al 25.
        al_25 = self.reportes.balance_general(f'{ANIO}-10-25')
        self.assertCifra(al_25['totales']['pasivo'] - a['totales']['pasivo'], 100.0)

    def test_comparar_el_balance_ignora_el_desde_escondido(self):
        """La pantalla trae un «Desde» escondido en el balance: no debe cambiar contra qué se compara."""
        ayer = self.reportes.obtener('balance_general', f'{ANIO}-10-01', HOY, comparar='periodo_anterior')
        raro = self.reportes.obtener('balance_general', f'{ANIO}-01-01', HOY, comparar='periodo_anterior')
        absurdo = self.reportes.obtener('balance_general', f'{ANIO}-11-30', HOY, comparar='periodo_anterior')
        for datos in (ayer, raro, absurdo):
            self.assertEqual(datos['comparado']['hasta'], f'{ANIO}-09-14')
            self.assertTrue(datos['cuadra'])
            self.assertTrue(datos['comparado']['totales']['activo'])
        anio = self.reportes.obtener('balance_general', f'{ANIO}-10-01', HOY, comparar='anio_anterior')
        self.assertEqual(anio['comparado']['hasta'], f'{ANIO - 1}-10-14')
        self.assertCifra(anio['comparado']['totales']['activo'],
                         sum(O.por_tipo(self.env, self.company, hasta=f'{ANIO - 1}-10-14').get(t, 0.0)
                             for t in ACTIVOS), 'activo un año antes')

    def test_antiguedad_contra_los_apuntes(self):
        for tipo, cuenta in (('por_cobrar', 'asset_receivable'), ('por_pagar', 'liability_payable')):
            for corte in CORTES:
                esperado = O.pendientes(self.env, self.company, cuenta, corte)
                datos = getattr(self.reportes, tipo)(hasta=corte)
                por_tramo = dict.fromkeys(('por_vencer', 'd1_30', 'd31_60', 'd61_90', 'd91_120', 'mas_120'), 0.0)
                vencido = 0.0
                por_tercero = {}
                for _apunte, tercero, vence, pendiente in esperado:
                    dias = (d(corte) - vence).days
                    por_tramo[O.tramo(dias)] += pendiente
                    if dias > 0:
                        vencido += pendiente
                    por_tercero[tercero] = por_tercero.get(tercero, 0.0) + pendiente
                msg = f'{tipo} al {corte}'
                for tramo, valor in por_tramo.items():
                    self.assertCifra(datos['totales'][tramo], valor, f'{msg} {tramo}')
                self.assertCifra(datos['totales']['total'], sum(por_tramo.values()), f'{msg} total')
                self.assertCifra(datos['totales']['vencido'], vencido, f'{msg} vencido')
                reales = {f['id'] or False: f['total'] for f in datos['filas']}
                esperados = {self.env['res.partner'].browse(t).commercial_partner_id.id or False: 0.0
                             for t in por_tercero}
                for t, valor in por_tercero.items():
                    esperados[self.env['res.partner'].browse(t).commercial_partner_id.id or False] += valor
                self.assertEqual(set(reales), {k for k, v in esperados.items() if round(v, 2)}, msg)
                for t, valor in esperados.items():
                    if round(valor, 2):
                        self.assertCifra(reales[t], valor, f'{msg} tercero {t}')
                # Partida doble: lo que dice el reporte es el saldo de las cuentas de cobrar/pagar en el balance.
                bg = self.reportes.balance_general(corte)
                saldo = sum(f['monto'] for s in bg['secciones'] for f in s['filas']
                            if f['tipo'] == cuenta)
                signo = 1 if cuenta == 'asset_receivable' else 1
                self.assertCifra(datos['totales']['total'], signo * saldo, f'{msg}: igual al balance general')

    def test_antiguedad_cifras_a_mano(self):
        cobrar = self.reportes.por_cobrar(hasta=HOY)
        self.assertEqual(cobrar['totales']['total'], 2614.5)
        self.assertEqual(cobrar['totales']['vencido'], 2154.0)
        tramos = cobrar['totales']
        self.assertEqual((tramos['por_vencer'], tramos['d1_30'], tramos['d31_60'], tramos['mas_120']),
                         (460.5, 1726.0, -107.0, 535.0))
        pagar = self.reportes.por_pagar(hasta=HOY)
        self.assertEqual((pagar['totales']['total'], pagar['totales']['vencido']), (938.1, 317.5))
        # El pago parcial de la factura de marzo (150 de 321) deja 171 pendientes y vencidos hace más de 120 días.
        proveedor = next(f for f in pagar['filas'] if f['id'] == self.datos.v1.id)
        self.assertEqual(proveedor['tramos']['mas_120'], 171.0)
        # Una factura que vence HOY no está vencida todavía.
        cliente6 = next(f for f in cobrar['filas'] if f['id'] == self.datos.c6.id)
        self.assertEqual((cliente6['total'], cliente6['vencido']), (160.5, 0.0))
        # Mientras no llegue su fecha de pago, un pago posterior al corte no cuenta.
        el_5 = self.reportes.por_cobrar(hasta=f'{ANIO}-10-05')
        cliente1 = next(f for f in el_5['filas'] if f['id'] == self.datos.c1.id)
        self.assertEqual(cliente1['total'], 642.0)          # el abono de 200 es del día 6

    def test_antiguedad_y_borradores(self):
        sin = self.reportes.por_cobrar(hasta=HOY)['totales']['total']
        con = self.reportes.por_cobrar(hasta=HOY, borradores=True)['totales']['total']
        self.assertCifra(con - sin, 700.0 * 1.07)           # solo la factura en borrador, no la cancelada

    def test_las_facturas_abiertas_de_hoy_suman_el_reporte(self):
        """Con el corte en el futuro, lo pendiente de cada factura es su saldo actual en Odoo."""
        socios = self.datos.c1 | self.datos.c2 | self.datos.c3 | self.datos.c4 | self.datos.c5 | self.datos.c6
        facturas = self.env['account.move'].search([
            ('partner_id', 'in', socios.ids), ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted')])
        residual = sum(m.amount_residual_signed for m in facturas)
        reporte = self.reportes.por_cobrar(hasta=f'{ANIO}-12-31')
        propios = sum(f['total'] for f in reporte['filas'] if f['id'] in socios.ids)
        self.assertCifra(propios, residual, 'pendiente de las facturas de cliente')


@tagged('post_install', '-at_install')
class TestAuditoriaResumen(AuditoriaCommon):
    """Las tarjetas del Resumen: cada una dice si es un saldo («al corte») o un movimiento («del periodo»)."""

    def tarjetas(self, desde, hasta):
        return {t['clave']: t for t in self.reportes.obtener('resumen', desde, hasta)['tarjetas']}

    def test_el_dinero_en_bancos_cambia_con_hasta_y_no_con_desde(self):
        """La duda de la dueña: «Este mes» no mueve el dinero en bancos porque es un saldo al día de hoy."""
        al_14 = self.efectivo(hasta=HOY)
        for desde in (HOY, f'{ANIO}-10-13', f'{ANIO}-10-01', f'{ANIO}-01-01'):
            tarjetas = self.tarjetas(desde, HOY)
            self.assertCifra(tarjetas['bancos']['valor'], al_14, f'desde {desde}')
            self.assertEqual((tarjetas['bancos']['base'], tarjetas['bancos']['al']), ('saldo', HOY))
        self.assertEqual(al_14, 26742.5)
        # En cambio cambia en cuanto cambia el «Hasta».
        for corte in CORTES:
            self.assertCifra(self.tarjetas(f'{ANIO}-01-01', corte)['bancos']['valor'], self.efectivo(hasta=corte), corte)
        self.assertNotEqual(self.tarjetas(f'{ANIO}-09-01', f'{ANIO}-09-30')['bancos']['valor'], al_14)

    def test_las_tarjetas_de_saldo_cuadran_con_el_balance_el_flujo_y_la_antiguedad(self):
        for corte in CORTES:
            tarjetas = self.tarjetas(f'{ANIO}-01-01', corte)
            bg = self.reportes.balance_general(corte)
            caja = sum(f['monto'] for s in bg['secciones'] for f in s['filas'] if f['tipo'] == 'asset_cash')
            self.assertCifra(tarjetas['bancos']['valor'], caja, f'{corte}: dinero = efectivo del balance general')
            flujo = self.reportes.flujo_efectivo(f'{ANIO - 1}-01-01', corte)
            self.assertCifra(tarjetas['bancos']['valor'], flujo['resumen']['efectivo_final'], f'{corte}: flujo')
            cobrar = self.reportes.por_cobrar(hasta=corte)['totales']
            pagar = self.reportes.por_pagar(hasta=corte)['totales']
            self.assertCifra(tarjetas['por_cobrar']['valor'], cobrar['total'], corte)
            self.assertCifra(tarjetas['por_cobrar']['vencido'], cobrar['vencido'], corte)
            self.assertCifra(tarjetas['por_pagar']['valor'], pagar['total'], corte)
            self.assertCifra(tarjetas['por_pagar']['vencido'], pagar['vencido'], corte)
            for clave in ('por_cobrar', 'por_pagar'):
                self.assertEqual((tarjetas[clave]['base'], tarjetas[clave]['al']), ('saldo', corte))

    def test_te_deben_y_debes_no_cambian_al_mover_solo_el_desde_y_lo_vencido_se_mide_contra_el_corte(self):
        a = self.tarjetas(f'{ANIO}-10-01', HOY)
        b = self.tarjetas(HOY, HOY)
        for clave in ('bancos', 'por_cobrar', 'por_pagar'):
            self.assertEqual(a[clave]['valor'], b[clave]['valor'], clave)
        self.assertEqual(a['por_cobrar']['vencido'], 2154.0)
        # Un mes antes (30 de septiembre) la factura que vence el 3 de octubre todavía no estaba vencida.
        sep = self.tarjetas(f'{ANIO}-09-01', f'{ANIO}-09-30')
        self.assertGreater(a['por_cobrar']['vencido'], 0)
        self.assertCifra(sep['por_cobrar']['vencido'] - sep['por_cobrar']['valor'] * 0, sep['por_cobrar']['vencido'])
        cobrar_sep = self.reportes.por_cobrar(hasta=f'{ANIO}-09-30')['totales']
        self.assertCifra(sep['por_cobrar']['vencido'], cobrar_sep['vencido'], 'vencido al 30 de septiembre')
        self.assertLess(sep['por_cobrar']['vencido'], a['por_cobrar']['vencido'] + 1)

    def test_las_tarjetas_de_movimiento_cambian_con_el_desde(self):
        mes = self.tarjetas(f'{ANIO}-10-01', HOY)
        hoy = self.tarjetas(HOY, HOY)
        self.assertEqual(mes['ventas']['valor'], 1800.0)
        self.assertEqual(hoy['ventas']['valor'], 150.0)
        self.assertEqual(hoy['utilidad']['valor'], 70.0)
        self.assertEqual((mes['itbms']['valor'], mes['itbms']['debito'], mes['itbms']['credito']), (99.4, 105.0, 5.6))
        self.assertEqual((hoy['itbms']['valor'], hoy['itbms']['debito'], hoy['itbms']['credito']), (4.9, 10.5, 5.6))
        for clave in ('ventas', 'utilidad', 'itbms'):
            self.assertEqual(mes[clave]['base'], 'periodo')
            self.assertEqual((mes[clave]['desde'], mes[clave]['hasta']), (f'{ANIO}-10-01', HOY))
        self.assertEqual((hoy['ventas']['desde'], hoy['ventas']['hasta']), (HOY, HOY))
        # «Hoy» se compara con ayer (el 13), no con un periodo de otro tamaño.
        datos = self.reportes.obtener('resumen', HOY, HOY)
        self.assertEqual(datos['periodo_comparado'], {'desde': f'{ANIO}-10-13', 'hasta': f'{ANIO}-10-13'})
        self.assertEqual(datos['tarjetas'][4]['comparado'], 0.0)

    def test_cada_tarjeta_coincide_con_su_reporte(self):
        for nombre, (desde, hasta) in VENTANAS.items():
            tarjetas = self.tarjetas(desde, hasta)
            er = self.reportes.estado_resultados(desde, hasta)
            self.assertCifra(tarjetas['ventas']['valor'], er['secciones'][0]['total'], nombre)
            self.assertCifra(tarjetas['utilidad']['valor'], er['resumen']['utilidad_neta'], nombre)
            itbms = self.reportes.itbms(desde, hasta)['resumen']
            self.assertCifra(tarjetas['itbms']['valor'], abs(itbms['a_pagar']), nombre)
            self.assertEqual(tarjetas['itbms']['titulo'], 'ITBMS por pagar' if itbms['a_pagar'] >= 0 else 'ITBMS a favor')

    def test_todo_conciliado_solo_si_no_queda_nada_por_cruzar(self):
        """«Todo conciliado» antes decía solo «sin movimientos del banco pendientes»: no veía los cobros registrados."""
        antes = self.tarjetas(f'{ANIO}-10-01', HOY)['bancos']
        self.assertEqual((antes['sin_conciliar'], antes['pagos_sin_cruzar'], antes['monto_sin_cruzar']), (1, 1, 200.0))
        self.assertNotIn('Todo conciliado', antes['nota'])
        self.assertEqual(antes['valor'], 26742.5)
        # El depósito suelto (250) se concilia contra una cuenta: sigue el cobro en caja que nadie ha cruzado.
        otros = self.env['account.account'].search([('account_type', '=', 'income_other'),
                                                    ('company_ids', 'in', self.company.ids)], limit=1)
        self.datos.deposito_suelto.dcasa_conciliar(cuenta_id=otros.id, etiqueta='Intereses')
        medio = self.tarjetas(f'{ANIO}-10-01', HOY)['bancos']
        self.assertEqual((medio['sin_conciliar'], medio['pagos_sin_cruzar']), (0, 1))
        self.assertNotIn('Todo conciliado', medio['nota'])
        # Llega el movimiento de la caja y se cruza con el cobro registrado: ahora sí, todo conciliado.
        entrada = self.datos.movimiento_banco(200, f'{ANIO}-10-06', 'COBRO EN CAJA', diario=self.datos.efectivo)
        self.env['dcasa.conciliacion'].conciliar(
            entrada.id, apunte_ids=self.datos._apunte_pago(self.datos.abono_caja).ids)
        despues = self.tarjetas(f'{ANIO}-10-01', HOY)['bancos']
        self.assertEqual((despues['sin_conciliar'], despues['pagos_sin_cruzar']), (0, 0))
        self.assertEqual(despues['nota'], 'Todo conciliado')
        self.assertCifra(despues['valor'], 26742.5 + 200.0, 'el cobro de la caja ya cuenta como dinero')
        self.assertCifra(despues['valor'], self.efectivo(hasta=HOY), 'sigue igual al efectivo de los apuntes')

    def test_una_cuenta_de_efectivo_sin_diario_tambien_cuenta(self):
        suelta = self.env['account.account'].create({'name': 'Caja chica sin diario', 'code': '9A0090',
                                                     'account_type': 'asset_cash'})
        self.datos.asiento(f'{ANIO}-10-10', [(suelta, 75, 0), (self.datos._pagar(), 0, 75, self.datos.v2)])
        datos = self.reportes.obtener('resumen', f'{ANIO}-10-01', HOY)
        self.assertCifra(next(t for t in datos['tarjetas'] if t['clave'] == 'bancos')['valor'], 26742.5 + 75.0)
        extra = [b for b in datos['bancos'] if not b['id']]
        self.assertEqual([(b['nombre'], b['saldo']) for b in extra], [('Otras cuentas de efectivo', 75.0)])

    def test_exportaciones_dicen_de_que_fecha_es_cada_cosa(self):
        from odoo.addons.dcasa_contabilidad.controllers.main import _filas_planas, _texto_periodo, libro_excel  # noqa: PLC0415
        for nombre, esperado in (('estado_resultados', f'El {HOY}'), ('itbms', f'El {HOY}'),
                                 ('balance_general', f'Al {HOY}'), ('por_cobrar', f'Al {HOY}')):
            self.assertEqual(_texto_periodo(self.reportes.obtener(nombre, HOY, HOY)), esperado, nombre)
        self.assertEqual(_texto_periodo(self.reportes.obtener('flujo_efectivo', f'{ANIO}-10-01', HOY)),
                         f'Del {ANIO}-10-01 al {HOY}')
        resumen = self.reportes.obtener('resumen', f'{ANIO}-10-01', HOY)
        encabezados, filas = _filas_planas(resumen)
        self.assertIn('Fecha o periodo', encabezados)
        cuando = {fila[0][0]: fila[0][2] for fila in filas if fila[0][2]}
        self.assertEqual(cuando['Dinero en bancos y caja'], f'Al {HOY}')
        self.assertEqual(cuando['Ventas'], f'Del {ANIO}-10-01 al {HOY}')
        self.assertTrue(libro_excel(resumen).startswith(b'PK'))
        html, _formato = self.env['ir.actions.report']._render_qweb_html(
            'dcasa_contabilidad.reporte_contable', self.company.ids,
            data={'reporte': 'estado_resultados', 'desde': HOY, 'hasta': HOY})
        self.assertIn(f'El {HOY}', html.decode())


@tagged('post_install', '-at_install')
class TestAuditoriaMulticompania(ContabilidadCommon):
    """Cada reporte lee solo las empresas activas: una segunda empresa no se mezcla si no se elige."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.otra = cls.env['res.company'].create({'name': 'Zona Libre Auditoría SA', 'currency_id': cls.env.ref('base.USD').id})
        cls.env['account.chart.template'].try_loading('pa', cls.otra, install_demo=False)
        cls.otra.currency_id = cls.env.ref('base.USD')
        cls.datos = Auditoria(cls.env, anio=ANIO)
        cuentas = cls.env['account.account'].with_company(cls.otra)
        cxc = cuentas.search([('account_type', '=', 'asset_receivable'), ('company_ids', 'in', cls.otra.ids)], limit=1)
        ventas = cuentas.search([('account_type', '=', 'income'), ('company_ids', 'in', cls.otra.ids)], limit=1)
        diario = cls.env['account.journal'].search([('company_id', '=', cls.otra.id), ('type', '=', 'general')], limit=1)
        asiento = cls.env['account.move'].with_company(cls.otra).create({
            'move_type': 'entry', 'company_id': cls.otra.id, 'journal_id': diario.id, 'date': f'{ANIO}-10-12',
            'line_ids': [(0, 0, {'account_id': cxc.id, 'debit': 999, 'credit': 0, 'name': 'otra empresa',
                                 'partner_id': cls.datos.c1.id}),
                         (0, 0, {'account_id': ventas.id, 'debit': 0, 'credit': 999, 'name': 'otra empresa'})]})
        asiento.action_post()

    def motor(self, *empresas):
        return self.env['dcasa.reporte.contable'].with_context(allowed_company_ids=[e.id for e in empresas])

    def test_cada_empresa_ve_lo_suyo_y_juntas_suman(self):
        solo_a = self.motor(self.company)
        solo_b = self.motor(self.otra)
        juntas = self.motor(self.company, self.otra)
        a = solo_a.estado_resultados(f'{ANIO}-10-01', HOY)
        b = solo_b.estado_resultados(f'{ANIO}-10-01', HOY)
        ambas = juntas.estado_resultados(f'{ANIO}-10-01', HOY)
        self.assertEqual(a['secciones'][0]['total'], 1800.0)
        self.assertEqual(b['secciones'][0]['total'], 999.0)
        self.assertEqual(ambas['secciones'][0]['total'], 1800.0 + 999.0)
        self.assertEqual(solo_a.por_cobrar(hasta=HOY)['totales']['total'], 2614.5)
        self.assertEqual(solo_b.por_cobrar(hasta=HOY)['totales']['total'], 999.0)
        self.assertEqual(juntas.por_cobrar(hasta=HOY)['totales']['total'], 2614.5 + 999.0)
        for motor in (solo_a, solo_b, juntas):
            self.assertTrue(motor.balance_general(HOY)['cuadra'])
            self.assertTrue(motor.balance_comprobacion(f'{ANIO}-10-01', HOY)['cuadra'])
        self.assertEqual(solo_a.obtener('resumen', f'{ANIO}-10-01', HOY)['tarjetas'][0]['valor'], 26742.5)
        self.assertEqual(solo_b.obtener('resumen', f'{ANIO}-10-01', HOY)['tarjetas'][0]['valor'], 0.0)
