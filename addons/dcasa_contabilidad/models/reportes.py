"""Motor de los reportes contables de D'CASA.

Todo sale de los apuntes contables (account.move.line) de asientos publicados: nada
se guarda aparte ni se calcula a mano. Reglas de presentación (NIIF, práctica local):

* Cuentas de balance: el saldo inicial es todo lo anterior al periodo.
* Cuentas de resultados: el saldo inicial es solo lo del ejercicio en curso; lo de
  ejercicios anteriores pasa al patrimonio como «resultados no asignados».
* Ingresos, pasivos y patrimonio se presentan en positivo (haber − debe).
"""
from collections import defaultdict
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

TIPOS_RESULTADOS = (
    'income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost',
)

# Estado de resultados: (clave, título, tipos de cuenta, signo con el que se presenta)
SECCIONES_RESULTADOS = [
    ('ventas', 'Ingresos por ventas', ('income',), -1),
    ('costo', 'Costo de ventas', ('expense_direct_cost',), 1),
    ('otros_ingresos', 'Otros ingresos', ('income_other',), -1),
    ('gastos', 'Gastos de operación', ('expense',), 1),
    ('depreciacion', 'Depreciación y amortización', ('expense_depreciation',), 1),
    ('otros_gastos', 'Otros gastos', ('expense_other',), 1),
]

# Balance general: (clave, título, grupo, tipos de cuenta)
SECCIONES_BALANCE = [
    ('activo_corriente', 'Activo corriente', 'activo',
     ('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments')),
    ('activo_no_corriente', 'Activo no corriente', 'activo', ('asset_non_current', 'asset_fixed')),
    ('pasivo_corriente', 'Pasivo corriente', 'pasivo',
     ('liability_payable', 'liability_credit_card', 'liability_current')),
    ('pasivo_no_corriente', 'Pasivo no corriente', 'pasivo', ('liability_non_current',)),
    ('patrimonio', 'Patrimonio', 'patrimonio', ('equity', 'equity_unaffected')),
]


# Flujo de efectivo: (clave, título, tipos de cuenta de balance que aportan a la actividad)
SECCIONES_FLUJO = [
    ('operacion', 'Actividades de operación',
     ('asset_receivable', 'asset_current', 'asset_prepayments', 'liability_payable', 'liability_credit_card',
      'liability_current')),
    ('inversion', 'Actividades de inversión', ('asset_non_current', 'asset_fixed')),
    ('financiamiento', 'Actividades de financiamiento', ('liability_non_current', 'equity', 'equity_unaffected')),
]

# Antigüedad de saldos: (clave, nombre, hasta cuántos días vencido; None = sin tope)
TRAMOS = [
    ('por_vencer', 'Por vencer', 0),
    ('d1_30', '1 a 30 días', 30),
    ('d31_60', '31 a 60 días', 60),
    ('d61_90', '61 a 90 días', 90),
    ('d91_120', '91 a 120 días', 120),
    ('mas_120', 'Más de 120 días', None),
]


class ReporteContable(models.AbstractModel):
    """Motores de los reportes. Los motores (``balance_general``…) son ``@api.private``: leen
    ``account.move.line``, que el ACL de ventas deja leer a la vendedora, así que por RPC
    entregarían el balance completo. El único punto de entrada remoto es ``obtener()``, que
    exige ``account.group_account_readonly`` (el grupo del menú «Reportes contables»).
    """
    _name = 'dcasa.reporte.contable'
    _description = "Reportes contables de D'CASA"

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @api.model
    def _fecha(self, valor, defecto=None):
        return fields.Date.to_date(valor) if valor else defecto

    @api.model
    def _periodo(self, desde, hasta):
        hoy = fields.Date.context_today(self)
        hasta = self._fecha(hasta, hoy)
        desde = self._fecha(desde, hasta.replace(day=1))
        return desde, hasta

    @api.model
    def _inicio_ejercicio(self, fecha):
        return self.env.company.compute_fiscalyear_dates(fecha)['date_from']

    @api.model
    def _dominio(self, borradores=False):
        estados = ('posted', 'draft') if borradores else ('posted',)
        return Domain([
            ('parent_state', 'in', estados),
            ('company_id', 'in', self.env.companies.ids),
            ('account_id.account_type', '!=', 'off_balance'),
        ])

    @api.model
    def _sumas_por_cuenta(self, dominio):
        """{cuenta: (debe, haber, saldo)} en una sola consulta agrupada."""
        grupos = self.env['account.move.line']._read_group(
            dominio, ['account_id'], ['debit:sum', 'credit:sum', 'balance:sum'])
        return {cuenta: (debe, haber, saldo) for cuenta, debe, haber, saldo in grupos}

    @api.model
    def _moneda(self):
        moneda = self.env.company.currency_id
        return {'simbolo': moneda.symbol, 'antes': moneda.position == 'before', 'decimales': moneda.decimal_places}

    @api.model
    def _r(self, valor):
        return self.env.company.currency_id.round(valor or 0.0)

    @api.model
    def _cuenta(self, cuenta):
        return {'id': cuenta.id, 'codigo': cuenta.code or '', 'nombre': cuenta.name, 'tipo': cuenta.account_type}

    # ------------------------------------------------------------------
    # Saldos iniciales
    # ------------------------------------------------------------------

    @api.model
    def _saldos_iniciales(self, desde, borradores=False):
        """Saldo de cada cuenta al comenzar el periodo, y lo no asignado de ejercicios anteriores."""
        inicio_ej = self._inicio_ejercicio(desde)
        base = self._dominio(borradores)
        balance = self._sumas_por_cuenta(Domain.AND([base, [
            ('date', '<', desde), ('account_id.account_type', 'not in', TIPOS_RESULTADOS)]]))
        resultados = self._sumas_por_cuenta(Domain.AND([base, [
            ('date', '>=', inicio_ej), ('date', '<', desde), ('account_id.account_type', 'in', TIPOS_RESULTADOS)]]))
        anteriores = self._sumas_por_cuenta(Domain.AND([base, [
            ('date', '<', inicio_ej), ('account_id.account_type', 'in', TIPOS_RESULTADOS)]]))
        iniciales = {c: v[2] for c, v in {**balance, **resultados}.items()}
        no_asignado = sum(v[2] for v in anteriores.values())
        return iniciales, no_asignado

    # ------------------------------------------------------------------
    # Balance de comprobación
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def balance_comprobacion(self, desde=None, hasta=None, borradores=False):
        desde, hasta = self._periodo(desde, hasta)
        iniciales, no_asignado = self._saldos_iniciales(desde, borradores)
        periodo = self._sumas_por_cuenta(Domain.AND([
            self._dominio(borradores), [('date', '>=', desde), ('date', '<=', hasta)]]))
        filas = []
        for cuenta in sorted(set(iniciales) | set(periodo), key=lambda c: c.code or ''):
            inicial = iniciales.get(cuenta, 0.0)
            debe, haber, _saldo = periodo.get(cuenta, (0.0, 0.0, 0.0))
            if not any(self._r(v) for v in (inicial, debe, haber)):
                continue
            filas.append({**self._cuenta(cuenta), 'inicial': self._r(inicial), 'debe': self._r(debe),
                          'haber': self._r(haber), 'final': self._r(inicial + debe - haber)})
        if self._r(no_asignado):
            filas.append({'id': False, 'codigo': '', 'nombre': 'Resultados no asignados de ejercicios anteriores',
                          'tipo': 'equity_unaffected', 'inicial': self._r(no_asignado), 'debe': 0.0, 'haber': 0.0,
                          'final': self._r(no_asignado)})
        totales = {k: self._r(sum(f[k] for f in filas)) for k in ('inicial', 'debe', 'haber', 'final')}
        return {'reporte': 'balance_comprobacion', 'titulo': 'Balance de comprobación', 'desde': str(desde),
                'hasta': str(hasta), 'moneda': self._moneda(), 'filas': filas, 'totales': totales,
                'cuadra': not self._r(totales['debe'] - totales['haber'])}

    # ------------------------------------------------------------------
    # Libro mayor
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def libro_mayor(self, desde=None, hasta=None, cuenta_ids=None, borradores=False, limite=2000):
        desde, hasta = self._periodo(desde, hasta)
        iniciales, _no_asignado = self._saldos_iniciales(desde, borradores)
        dominio = Domain.AND([self._dominio(borradores), [('date', '>=', desde), ('date', '<=', hasta)]])
        if cuenta_ids:
            dominio = Domain.AND([dominio, [('account_id', 'in', cuenta_ids)]])
        Linea = self.env['account.move.line']
        movidas = {c for c, *_ in Linea._read_group(dominio, ['account_id'], ['__count'])}
        cuentas = movidas | {c for c, v in iniciales.items() if self._r(v)}
        if cuenta_ids:
            cuentas = {c for c in cuentas if c.id in cuenta_ids}
        resultado = []
        for cuenta in sorted(cuentas, key=lambda c: c.code or ''):
            saldo = iniciales.get(cuenta, 0.0)
            inicial = saldo
            lineas = Linea.search(Domain.AND([dominio, [('account_id', '=', cuenta.id)]]),
                                  order='date, move_name, id', limit=limite + 1)
            detalle = []
            for linea in lineas[:limite]:
                saldo += linea.debit - linea.credit
                detalle.append({
                    'id': linea.id, 'fecha': str(linea.date), 'asiento': linea.move_id.name,
                    'asiento_id': linea.move_id.id, 'diario': linea.journal_id.code,
                    'tercero': linea.partner_id.display_name or '', 'concepto': linea.name or linea.ref or '',
                    'debe': self._r(linea.debit), 'haber': self._r(linea.credit), 'saldo': self._r(saldo),
                })
            debe = sum(d['debe'] for d in detalle)
            haber = sum(d['haber'] for d in detalle)
            resultado.append({**self._cuenta(cuenta), 'inicial': self._r(inicial), 'debe': self._r(debe),
                              'haber': self._r(haber), 'final': self._r(inicial + debe - haber),
                              'lineas': detalle, 'truncado': len(lineas) > limite})
        return {'reporte': 'libro_mayor', 'titulo': 'Libro mayor', 'desde': str(desde), 'hasta': str(hasta),
                'moneda': self._moneda(), 'cuentas': resultado}

    # ------------------------------------------------------------------
    # Estado de resultados
    # ------------------------------------------------------------------

    @api.model
    def _resultado(self, desde, hasta, borradores=False):
        sumas = self._sumas_por_cuenta(Domain.AND([self._dominio(borradores), [
            ('date', '>=', desde), ('date', '<=', hasta), ('account_id.account_type', 'in', TIPOS_RESULTADOS)]]))
        secciones = []
        for clave, titulo, tipos, signo in SECCIONES_RESULTADOS:
            filas = [{**self._cuenta(c), 'monto': self._r(signo * v[2])}
                     for c, v in sorted(sumas.items(), key=lambda cv: cv[0].code or '')
                     if c.account_type in tipos and self._r(v[2])]
            secciones.append({'clave': clave, 'titulo': titulo, 'filas': filas,
                              'total': self._r(sum(f['monto'] for f in filas))})
        t = {s['clave']: s['total'] for s in secciones}
        utilidad_bruta = self._r(t['ventas'] - t['costo'])
        utilidad_operativa = self._r(utilidad_bruta - t['gastos'] - t['depreciacion'])
        utilidad_neta = self._r(utilidad_operativa + t['otros_ingresos'] - t['otros_gastos'])
        return secciones, {'utilidad_bruta': utilidad_bruta, 'utilidad_operativa': utilidad_operativa,
                           'utilidad_neta': utilidad_neta}

    @api.private
    @api.model
    def estado_resultados(self, desde=None, hasta=None, borradores=False):
        desde, hasta = self._periodo(desde, hasta)
        secciones, resumen = self._resultado(desde, hasta, borradores)
        ventas = next(s['total'] for s in secciones if s['clave'] == 'ventas')
        margen = round(resumen['utilidad_bruta'] / ventas * 100, 1) if ventas else None
        return {'reporte': 'estado_resultados', 'titulo': 'Estado de resultados', 'desde': str(desde),
                'hasta': str(hasta), 'moneda': self._moneda(), 'secciones': secciones,
                'resumen': {**resumen, 'margen_bruto': margen}}

    # ------------------------------------------------------------------
    # Balance general
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def balance_general(self, hasta=None, borradores=False, desde=None):
        _desde, hasta = self._periodo(None, hasta)
        base = Domain.AND([self._dominio(borradores), [('date', '<=', hasta)]])
        sumas = self._sumas_por_cuenta(Domain.AND([base, [('account_id.account_type', 'not in', TIPOS_RESULTADOS)]]))
        inicio_ej = self._inicio_ejercicio(hasta)
        anteriores = self._sumas_por_cuenta(Domain.AND([base, [
            ('date', '<', inicio_ej), ('account_id.account_type', 'in', TIPOS_RESULTADOS)]]))
        del_ejercicio = self._sumas_por_cuenta(Domain.AND([base, [
            ('date', '>=', inicio_ej), ('account_id.account_type', 'in', TIPOS_RESULTADOS)]]))
        secciones = []
        for clave, titulo, grupo, tipos in SECCIONES_BALANCE:
            signo = 1 if grupo == 'activo' else -1
            filas = [{**self._cuenta(c), 'monto': self._r(signo * v[2])}
                     for c, v in sorted(sumas.items(), key=lambda cv: cv[0].code or '')
                     if c.account_type in tipos and self._r(v[2])]
            if clave == 'patrimonio':
                for nombre, grupo_sumas in (('Resultados de ejercicios anteriores', anteriores),
                                            ('Resultado del ejercicio', del_ejercicio)):
                    monto = self._r(-sum(v[2] for v in grupo_sumas.values()))
                    if monto:
                        filas.append({'id': False, 'codigo': '', 'nombre': nombre, 'tipo': 'equity_unaffected',
                                      'monto': monto})
            secciones.append({'clave': clave, 'titulo': titulo, 'grupo': grupo, 'filas': filas,
                              'total': self._r(sum(f['monto'] for f in filas))})
        totales = {g: self._r(sum(s['total'] for s in secciones if s['grupo'] == g))
                   for g in ('activo', 'pasivo', 'patrimonio')}
        totales['pasivo_y_patrimonio'] = self._r(totales['pasivo'] + totales['patrimonio'])
        return {'reporte': 'balance_general', 'titulo': 'Balance general', 'desde': str(inicio_ej),
                'hasta': str(hasta), 'moneda': self._moneda(), 'secciones': secciones, 'totales': totales,
                'cuadra': not self._r(totales['activo'] - totales['pasivo_y_patrimonio'])}

    # ------------------------------------------------------------------
    # ITBMS
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def itbms(self, desde=None, hasta=None, borradores=False):
        """Resumen para la declaración de ITBMS: débito fiscal (ventas) y crédito fiscal (compras)."""
        desde, hasta = self._periodo(desde, hasta)
        base = Domain.AND([self._dominio(borradores), [('date', '>=', desde), ('date', '<=', hasta)]])
        Linea = self.env['account.move.line']
        cuotas = dict(Linea._read_group(Domain.AND([base, [('tax_line_id', '!=', False)]]),
                                        ['tax_line_id'], ['balance:sum']))
        # Base imponible por impuesto, también de los que no generan cuota (ITBMS 0 % / exento).
        bases = dict(Linea._read_group(Domain.AND([base, [('tax_ids', '!=', False)]]),
                                       ['tax_ids'], ['balance:sum']))
        filas = []
        for impuesto in sorted(set(cuotas) | set(bases), key=lambda t: (t.type_tax_use, t.sequence, t.name)):
            venta = impuesto.type_tax_use == 'sale'
            signo = -1 if venta else 1
            filas.append({
                'id': impuesto.id, 'nombre': impuesto.name, 'tipo': 'venta' if venta else 'compra',
                'base': self._r(signo * bases.get(impuesto, 0.0)),
                'impuesto': self._r(signo * cuotas.get(impuesto, 0.0)),
            })
        debito = self._r(sum(f['impuesto'] for f in filas if f['tipo'] == 'venta'))
        credito = self._r(sum(f['impuesto'] for f in filas if f['tipo'] == 'compra'))
        return {'reporte': 'itbms', 'titulo': 'Resumen de ITBMS', 'desde': str(desde), 'hasta': str(hasta),
                'moneda': self._moneda(), 'filas': filas,
                'resumen': {'debito_fiscal': debito, 'credito_fiscal': credito,
                            'a_pagar': self._r(debito - credito)}}

    # ------------------------------------------------------------------
    # Analítica
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def analitica(self, desde=None, hasta=None, borradores=False):
        """Rentabilidad por cuenta analítica (canal de venta u otro plan)."""
        desde, hasta = self._periodo(desde, hasta)
        Linea = self.env['account.analytic.line']
        dominio = [('date', '>=', desde), ('date', '<=', hasta), ('company_id', 'in', self.env.companies.ids + [False])]
        filas = []
        # Cada plan analítico guarda su cuenta en su propia columna de la línea analítica.
        for plan in self.env['account.analytic.plan'].search([('parent_id', '=', False)]):
            columna = plan._column_name()
            if columna not in Linea._fields:
                continue
            con_cuenta = dominio + [(columna, '!=', False)]
            ingresos = dict(Linea._read_group(con_cuenta + [('amount', '>', 0)], [columna], ['amount:sum']))
            costos = dict(Linea._read_group(con_cuenta + [('amount', '<', 0)], [columna], ['amount:sum']))
            for cuenta in sorted(set(ingresos) | set(costos), key=lambda c: c.name):
                ingreso = self._r(ingresos.get(cuenta, 0.0))
                costo = self._r(-costos.get(cuenta, 0.0))
                filas.append({'id': cuenta.id, 'plan': plan.name, 'nombre': cuenta.name, 'columna': columna,
                              'ingresos': ingreso, 'costos': costo, 'margen': self._r(ingreso - costo)})
        return {'reporte': 'analitica', 'titulo': 'Rentabilidad analítica', 'desde': str(desde), 'hasta': str(hasta),
                'moneda': self._moneda(), 'filas': filas}

    # ------------------------------------------------------------------
    # Punto de entrada para la pantalla y las exportaciones
    # ------------------------------------------------------------------

    REPORTES = ('resumen', 'estado_resultados', 'balance_general', 'flujo_efectivo', 'por_cobrar', 'por_pagar',
                'balance_comprobacion', 'libro_mayor', 'itbms', 'analitica')
    # Reportes con columnas de comparación (otro periodo al lado, con la variación).
    COMPARABLES = ('estado_resultados', 'balance_general', 'flujo_efectivo')
    COMPARACIONES = ('periodo_anterior', 'anio_anterior')

    @api.model
    def obtener(self, reporte, desde=None, hasta=None, borradores=False, cuenta_ids=None, comparar=None):
        if reporte not in self.REPORTES:
            raise ValueError(reporte)
        if not self.env.user.has_group('account.group_account_readonly'):
            raise AccessError(self.env._('Los reportes contables son solo para quien lleva la contabilidad.'))
        argumentos = {'desde': desde, 'hasta': hasta, 'borradores': borradores}
        if reporte == 'libro_mayor' and cuenta_ids:
            argumentos['cuenta_ids'] = cuenta_ids
        datos = getattr(self, reporte)(**argumentos)
        if comparar and reporte in self.COMPARABLES:
            if comparar not in self.COMPARACIONES:
                raise ValueError(comparar)
            p_desde, p_hasta = self._periodo(desde, hasta)
            c_desde, c_hasta = self._periodo_comparado(p_desde, p_hasta, comparar)
            anterior = getattr(self, reporte)(desde=c_desde, hasta=c_hasta, borradores=borradores)
            self._fusionar(datos, anterior, comparar)
        datos['empresa'] = self.env.company.name
        return datos

    # ------------------------------------------------------------------
    # Comparativos
    # ------------------------------------------------------------------

    @api.model
    def _periodo_comparado(self, desde, hasta, modo):
        """El periodo con el que se compara: el inmediato anterior de igual largo o el mismo del año pasado.

        Un periodo que empieza el día 1 se compara por meses (septiembre completo con agosto
        completo; del 1 al 15 de octubre con del 1 al 15 de septiembre). Si termina a fin de mes,
        el comparado también (febrero de 28 o 29 días).
        """
        def fin_de_mes(dia):
            return dia + relativedelta(day=31)

        if modo == 'anio_anterior':
            meses = 12
        elif desde.day == 1:
            meses = (hasta.year - desde.year) * 12 + hasta.month - desde.month + 1
        else:
            dias = (hasta - desde).days + 1
            return desde - timedelta(days=dias), desde - timedelta(days=1)
        c_desde = desde - relativedelta(months=meses)
        c_hasta = hasta - relativedelta(months=meses)
        if hasta == fin_de_mes(hasta):
            c_hasta = fin_de_mes(c_hasta)
        return c_desde, c_hasta

    @api.model
    def _variacion(self, actual, anterior):
        diferencia = self._r(actual - anterior)
        porcentaje = round(diferencia / abs(anterior) * 100, 1) if self._r(anterior) else None
        return diferencia, porcentaje

    @api.model
    def _fusionar(self, datos, anterior, modo):
        """Pone el periodo comparado al lado: cada fila y cada total llevan «comparado» y la variación."""
        por_clave = {s['clave']: s for s in anterior['secciones']}

        def llave(fila):
            return fila['id'] or fila['nombre']

        for seccion in datos['secciones']:
            vieja = por_clave.get(seccion['clave'], {'filas': [], 'total': 0.0})
            filas_viejas = {llave(f): f for f in vieja['filas']}
            presentes = set()
            for fila in seccion['filas']:
                presentes.add(llave(fila))
                fila['comparado'] = filas_viejas.get(llave(fila), {}).get('monto', 0.0)
            for clave, fila in filas_viejas.items():
                if clave not in presentes:  # cuentas que solo se movieron en el otro periodo
                    seccion['filas'].append({**fila, 'monto': 0.0, 'comparado': fila['monto']})
            for fila in seccion['filas']:
                fila['variacion'], fila['variacion_pct'] = self._variacion(fila['monto'], fila['comparado'])
            seccion['comparado'] = vieja['total']
            seccion['variacion'], seccion['variacion_pct'] = self._variacion(seccion['total'], vieja['total'])
        cifras = 'resumen' if 'resumen' in datos else 'totales'
        datos['comparado'] = {
            'modo': modo, 'desde': anterior['desde'], 'hasta': anterior['hasta'],
            'etiqueta': 'Mismo periodo del año anterior' if modo == 'anio_anterior' else 'Periodo anterior',
            cifras: anterior.get(cifras, {}),
        }
        return datos

    # ------------------------------------------------------------------
    # Flujo de efectivo (método indirecto)
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def flujo_efectivo(self, desde=None, hasta=None, borradores=False):
        """De dónde vino y a dónde se fue el dinero, partiendo de la utilidad (método indirecto, NIC 7).

        Cada cuenta de balance que no es efectivo aporta lo contrario de lo que se movió: si
        subió lo que te deben, entró menos dinero; si subió lo que debes, salió menos. Por partida
        doble, la suma de las tres actividades es exactamente la variación del efectivo, y el
        reporte lo comprueba («cuadra»). La clasificación sale del tipo de cuenta, salvo que la
        cuenta tenga su «Actividad en el flujo de efectivo» (``dcasa_actividad_flujo``): el plan
        ``l10n_pa`` trae el activo fijo (161-165) y los préstamos (222) como corrientes, y es el
        contador quien decide cómo presentarlos.
        """
        desde, hasta = self._periodo(desde, hasta)
        base = Domain.AND([self._dominio(borradores), [('date', '>=', desde), ('date', '<=', hasta)]])
        movimientos = self._sumas_por_cuenta(Domain.AND([base, [
            ('account_id.account_type', 'not in', TIPOS_RESULTADOS + ('asset_cash',))]]))
        resultados, resumen = self._resultado(desde, hasta, borradores)
        depreciacion = next(s['total'] for s in resultados if s['clave'] == 'depreciacion')

        def actividad(cuenta):
            if cuenta.dcasa_actividad_flujo:  # la que eligió el contador para esa cuenta
                return cuenta.dcasa_actividad_flujo
            return next((c for c, _t, tipos in SECCIONES_FLUJO if cuenta.account_type in tipos), 'operacion')

        secciones = []
        for clave, titulo, _tipos in SECCIONES_FLUJO:
            filas = []
            if clave == 'operacion':
                filas.append({'id': False, 'codigo': '', 'nombre': 'Utilidad neta del periodo', 'tipo': 'resultado',
                              'monto': resumen['utilidad_neta']})
                if depreciacion:
                    filas.append({'id': False, 'codigo': '', 'tipo': 'ajuste', 'monto': depreciacion,
                                  'nombre': 'Más: depreciación y amortización (no es salida de dinero)'})
            filas += [{**self._cuenta(c), 'monto': self._r(-v[2])}
                      for c, v in sorted(movimientos.items(), key=lambda cv: cv[0].code or '')
                      if actividad(c) == clave and self._r(v[2])]
            if clave == 'inversion' and depreciacion:
                filas.append({'id': False, 'codigo': '', 'tipo': 'ajuste', 'monto': -depreciacion,
                              'nombre': 'Menos: depreciación del periodo (ya sumada en la operación)'})
            secciones.append({'clave': clave, 'titulo': titulo, 'filas': filas,
                              'total': self._r(sum(f['monto'] for f in filas))})
        efectivo = Domain.AND([self._dominio(borradores), [('account_id.account_type', '=', 'asset_cash')]])
        inicial = sum(v[2] for v in self._sumas_por_cuenta(Domain.AND([efectivo, [('date', '<', desde)]])).values())
        final = sum(v[2] for v in self._sumas_por_cuenta(Domain.AND([efectivo, [('date', '<=', hasta)]])).values())
        variacion = self._r(sum(s['total'] for s in secciones))
        return {'reporte': 'flujo_efectivo', 'titulo': 'Flujo de efectivo', 'desde': str(desde), 'hasta': str(hasta),
                'moneda': self._moneda(), 'secciones': secciones,
                'resumen': {'efectivo_inicial': self._r(inicial), 'variacion': variacion,
                            'efectivo_final': self._r(final)},
                'cuadra': not self._r(inicial + variacion - final)}

    # ------------------------------------------------------------------
    # Antigüedad de saldos: por cobrar y por pagar
    # ------------------------------------------------------------------

    @api.model
    def _tramo(self, dias):
        for clave, _nombre, tope in TRAMOS:
            if tope is None or dias <= tope:
                return clave
        return TRAMOS[-1][0]

    @api.model
    def _antiguedad(self, tipo, hasta=None, borradores=False):
        """Lo pendiente de cada documento A LA FECHA DE CORTE, por tercero y por tramo de días vencidos.

        Un pago posterior al corte no cuenta: se suma de nuevo lo que se cruzó después
        (``account.partial.reconcile.max_date``), igual que el reporte de Enterprise.
        """
        _desde, corte = self._periodo(None, hasta)
        tipo_cuenta = 'asset_receivable' if tipo == 'por_cobrar' else 'liability_payable'
        signo = 1 if tipo == 'por_cobrar' else -1
        lineas = self.env['account.move.line'].search(Domain.AND([self._dominio(borradores), [
            ('account_id.account_type', '=', tipo_cuenta), ('date', '<=', corte),
            '|', '|', ('reconciled', '=', False), ('matched_debit_ids.max_date', '>', corte),
            ('matched_credit_ids.max_date', '>', corte)]]), order='date, id')
        aplicado = defaultdict(float)
        for parcial in self.env['account.partial.reconcile'].search([
                '|', ('debit_move_id', 'in', lineas.ids), ('credit_move_id', 'in', lineas.ids),
                ('max_date', '<=', corte)]):
            aplicado[parcial.debit_move_id.id] += parcial.amount
            aplicado[parcial.credit_move_id.id] -= parcial.amount
        terceros = {}
        claves = [t[0] for t in TRAMOS]
        for linea in lineas:
            pendiente = self._r(signo * (linea.balance - aplicado[linea.id]))
            if not pendiente:
                continue
            vence = linea.date_maturity or linea.date
            dias = (corte - vence).days
            tramo = self._tramo(dias)
            partner = linea.partner_id.commercial_partner_id
            fila = terceros.setdefault(partner, {
                'id': partner.id or False, 'nombre': partner.display_name or 'Sin tercero',
                'telefono': partner.phone or '', 'tramos': dict.fromkeys(claves, 0.0), 'total': 0.0,
                'vencido': 0.0, 'documentos': []})
            fila['tramos'][tramo] += pendiente
            fila['total'] += pendiente
            if dias > 0:
                fila['vencido'] += pendiente
            fila['documentos'].append({
                'id': linea.id, 'asiento_id': linea.move_id.id, 'documento': linea.move_id.name or '',
                'referencia': linea.move_id.ref or '', 'fecha': str(linea.date), 'vence': str(vence),
                'dias': max(dias, 0), 'tramo': tramo, 'monto': pendiente})
        filas = sorted(terceros.values(), key=lambda f: -f['total'])
        for fila in filas:
            fila['tramos'] = {k: self._r(v) for k, v in fila['tramos'].items()}
            fila['total'] = self._r(fila['total'])
            fila['vencido'] = self._r(fila['vencido'])
        totales = {k: self._r(sum(f['tramos'][k] for f in filas)) for k in claves}
        totales['total'] = self._r(sum(f['total'] for f in filas))
        totales['vencido'] = self._r(sum(f['vencido'] for f in filas))
        cobrar = tipo == 'por_cobrar'
        return {'reporte': tipo, 'titulo': 'Cuentas por cobrar' if cobrar else 'Cuentas por pagar',
                'desde': str(corte), 'hasta': str(corte), 'moneda': self._moneda(),
                'tramos': [{'clave': k, 'nombre': n} for k, n, _t in TRAMOS],
                'filas': filas, 'totales': totales}

    @api.private
    @api.model
    def por_cobrar(self, desde=None, hasta=None, borradores=False):
        return self._antiguedad('por_cobrar', hasta, borradores)

    @api.private
    @api.model
    def por_pagar(self, desde=None, hasta=None, borradores=False):
        return self._antiguedad('por_pagar', hasta, borradores)

    # ------------------------------------------------------------------
    # Resumen (tablero de la dueña)
    # ------------------------------------------------------------------

    @api.model
    def _saldos_bancos(self, hasta):
        """Saldo contable de cada banco, Yappy, tarjeta y caja, con lo que falta por conciliar."""
        diarios = self.env['account.journal'].search([('type', 'in', ('bank', 'cash')),
                                                      ('company_id', 'in', self.env.companies.ids)])
        sumas = self._sumas_por_cuenta(Domain.AND([self._dominio(), [
            ('date', '<=', hasta), ('account_id', 'in', diarios.default_account_id.ids)]]))
        Linea = self.env['account.bank.statement.line']
        return [{'id': d.id, 'nombre': d.name, 'tipo': d.type, 'cuenta_id': d.default_account_id.id,
                 'saldo': self._r(sumas.get(d.default_account_id, (0, 0, 0))[2]),
                 'por_conciliar': Linea.search_count([('journal_id', '=', d.id), ('is_reconciled', '=', False),
                                                      ('date', '<=', hasta)])}
                for d in diarios]

    @api.private
    @api.model
    def resumen(self, desde=None, hasta=None, borradores=False):
        """Lo que la dueña mira cada semana. Cada cifra sale de los reportes de arriba (nada aparte)."""
        desde, hasta = self._periodo(desde, hasta)
        bancos = self._saldos_bancos(hasta)
        cobrar = self._antiguedad('por_cobrar', hasta)
        pagar = self._antiguedad('por_pagar', hasta)
        itbms = self.itbms(desde, hasta)['resumen']
        resultados = self.estado_resultados(desde, hasta)
        c_desde, c_hasta = self._periodo_comparado(desde, hasta, 'periodo_anterior')
        antes = self.estado_resultados(c_desde, c_hasta)
        ventas = resultados['secciones'][0]['total']
        ventas_antes = antes['secciones'][0]['total']
        utilidad = resultados['resumen']['utilidad_neta']
        utilidad_antes = antes['resumen']['utilidad_neta']
        por_conciliar = sum(b['por_conciliar'] for b in bancos)
        borradores_n = self.env['account.move'].search_count([
            ('state', '=', 'draft'), ('date', '<=', hasta), ('company_id', 'in', self.env.companies.ids)])
        alertas = []
        if por_conciliar:
            alertas.append({'nivel': 'aviso', 'destino': 'conciliacion',
                            'texto': f'{por_conciliar} movimientos del banco sin conciliar.'})
        if cobrar['totales']['vencido'] > 0:
            alertas.append({'nivel': 'aviso', 'destino': 'por_cobrar',
                            'texto': 'Hay cobros vencidos: mira quién te debe en «Por cobrar».'})
        if borradores_n:
            alertas.append({'nivel': 'info', 'destino': 'borradores',
                            'texto': f'{borradores_n} facturas o asientos en borrador (no cuentan en los reportes).'})
        bloqueo = self.env.company.fiscalyear_lock_date
        tarjetas = [
            {'clave': 'bancos', 'titulo': 'Dinero en bancos y caja', 'valor': self._r(sum(b['saldo'] for b in bancos)),
             'nota': f'{por_conciliar} movimientos por conciliar' if por_conciliar else 'Todo conciliado'},
            {'clave': 'por_cobrar', 'titulo': 'Te deben', 'valor': cobrar['totales']['total'],
             'vencido': cobrar['totales']['vencido']},
            {'clave': 'por_pagar', 'titulo': 'Debes a proveedores', 'valor': pagar['totales']['total'],
             'vencido': pagar['totales']['vencido']},
            {'clave': 'itbms', 'titulo': 'ITBMS por pagar' if itbms['a_pagar'] >= 0 else 'ITBMS a favor',
             'valor': abs(itbms['a_pagar']), 'debito': itbms['debito_fiscal'], 'credito': itbms['credito_fiscal']},
            {'clave': 'ventas', 'titulo': 'Ventas', 'valor': ventas, 'comparado': ventas_antes,
             'variacion_pct': self._variacion(ventas, ventas_antes)[1]},
            {'clave': 'utilidad', 'titulo': 'Utilidad', 'valor': utilidad, 'comparado': utilidad_antes,
             'variacion_pct': self._variacion(utilidad, utilidad_antes)[1]},
        ]
        return {
            'reporte': 'resumen', 'titulo': 'Resumen contable', 'desde': str(desde), 'hasta': str(hasta),
            'moneda': self._moneda(), 'tarjetas': tarjetas, 'bancos': bancos,
            'deudores': [{k: f[k] for k in ('id', 'nombre', 'telefono', 'total', 'vencido')}
                         for f in cobrar['filas'][:5]],
            'acreedores': [{k: f[k] for k in ('id', 'nombre', 'total', 'vencido')} for f in pagar['filas'][:5]],
            'periodo_comparado': {'desde': str(c_desde), 'hasta': str(c_hasta)},
            'bloqueado_hasta': str(bloqueo) if bloqueo else None,
            'alertas': alertas,
        }

    @api.model
    def periodos(self):
        """Atajos de fechas para la pantalla (hoy en Panamá)."""
        hoy = fields.Date.context_today(self)
        inicio_mes = hoy.replace(day=1)
        fin_mes_pasado = inicio_mes - timedelta(days=1)
        ejercicio = self.env.company.compute_fiscalyear_dates(hoy)
        trimestre = date(hoy.year, 3 * ((hoy.month - 1) // 3) + 1, 1)
        return [
            {'clave': 'mes', 'nombre': 'Este mes', 'desde': str(inicio_mes), 'hasta': str(hoy)},
            {'clave': 'mes_pasado', 'nombre': 'Mes pasado', 'desde': str(fin_mes_pasado.replace(day=1)),
             'hasta': str(fin_mes_pasado)},
            {'clave': 'trimestre', 'nombre': 'Este trimestre', 'desde': str(trimestre), 'hasta': str(hoy)},
            {'clave': 'ejercicio', 'nombre': 'Este año fiscal', 'desde': str(ejercicio['date_from']),
             'hasta': str(ejercicio['date_to'])},
        ]

    # ------------------------------------------------------------------
    # Instalación
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_configurar_contabilidad(self):
        """Contabilidad completa a la vista para quien administra la contabilidad."""
        gerente = self.env.ref('account.group_account_manager')
        contador = self.env.ref('account.group_account_user')
        if contador not in gerente.implied_ids:
            gerente.implied_ids = [(4, contador.id)]
        analitica = self.env.ref('analytic.group_analytic_accounting')
        empleados = self.env.ref('base.group_user')
        if analitica not in empleados.implied_ids:
            empleados.implied_ids = [(4, analitica.id)]
        # Cheques con el formato de D'CASA en el diario del banco.
        company = self.env.company
        company.account_check_printing_layout = 'dcasa_contabilidad.accion_cheque'
        metodo = self.env.ref('account_check_printing.account_payment_method_check', raise_if_not_found=False)
        banco = self.env['account.journal'].search([('type', '=', 'bank'), ('code', '=', 'BNK1'),
                                                    ('company_id', '=', company.id)], limit=1)
        if metodo and banco and metodo not in banco.outbound_payment_method_line_ids.payment_method_id:
            banco.outbound_payment_method_line_ids = [(0, 0, {'payment_method_id': metodo.id, 'name': 'Cheque'})]
