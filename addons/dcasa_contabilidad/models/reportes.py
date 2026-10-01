"""Motor de los reportes contables de D'CASA.

Todo sale de los apuntes contables (account.move.line) de asientos publicados: nada
se guarda aparte ni se calcula a mano. Reglas de presentación (NIIF, práctica local):

* Cuentas de balance: el saldo inicial es todo lo anterior al periodo.
* Cuentas de resultados: el saldo inicial es solo lo del ejercicio en curso; lo de
  ejercicios anteriores pasa al patrimonio como «resultados no asignados».
* Ingresos, pasivos y patrimonio se presentan en positivo (haber − debe).
"""
from datetime import date, timedelta

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

    REPORTES = ('balance_comprobacion', 'libro_mayor', 'estado_resultados', 'balance_general', 'itbms', 'analitica')

    @api.model
    def obtener(self, reporte, desde=None, hasta=None, borradores=False, cuenta_ids=None):
        if reporte not in self.REPORTES:
            raise ValueError(reporte)
        if not self.env.user.has_group('account.group_account_readonly'):
            raise AccessError(self.env._('Los reportes contables son solo para quien lleva la contabilidad.'))
        argumentos = {'desde': desde, 'hasta': hasta, 'borradores': borradores}
        if reporte == 'libro_mayor' and cuenta_ids:
            argumentos['cuenta_ids'] = cuenta_ids
        datos = getattr(self, reporte)(**argumentos)
        datos['empresa'] = self.env.company.name
        return datos

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
