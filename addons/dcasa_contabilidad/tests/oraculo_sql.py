"""Cálculo INDEPENDIENTE de las cifras contables, directo en SQL (ayuda de pruebas, no es un test).

No usa ``dcasa.reporte.contable`` ni el ORM de los apuntes: lee ``account_move_line``, ``account_move`` y
``account_account`` tal como están en la base y aplica a mano las reglas de la contabilidad. Así una prueba puede
cruzar «lo que dice el reporte» contra «lo que dicen los apuntes publicados» sin repetir el mismo código.
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta

RESULTADOS = ('income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')


def _estados(borradores):
    return ('posted', 'draft') if borradores else ('posted',)


def inicio_ejercicio(empresa, fecha):
    """Primer día del ejercicio fiscal de ``fecha`` según el cierre fiscal de la empresa (día/mes)."""
    dia, mes = empresa.fiscalyear_last_day, int(empresa.fiscalyear_last_month)

    def cierre(anio):
        return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))

    fin = cierre(fecha.year) if fecha <= cierre(fecha.year) else cierre(fecha.year + 1)
    return cierre(fin.year - 1) + timedelta(days=1)


def saldos(env, empresas, desde=None, hasta=None, tipos=None, sin_tipos=None, borradores=False):
    """{account_id: [debe, haber]} de apuntes con fecha en ``[desde, hasta]``."""
    sql = """
        SELECT l.account_id, COALESCE(SUM(l.debit), 0), COALESCE(SUM(l.credit), 0)
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
          JOIN account_account a ON a.id = l.account_id
         WHERE m.state IN %s AND l.company_id IN %s AND a.account_type <> 'off_balance'
    """
    params = [_estados(borradores), tuple(empresas.ids)]
    if desde:
        sql += ' AND l.date >= %s'
        params.append(desde)
    if hasta:
        sql += ' AND l.date <= %s'
        params.append(hasta)
    if tipos:
        sql += ' AND a.account_type IN %s'
        params.append(tuple(tipos))
    if sin_tipos:
        sql += ' AND a.account_type NOT IN %s'
        params.append(tuple(sin_tipos))
    sql += ' GROUP BY l.account_id'
    env.cr.execute(sql, params)
    return {cuenta: [float(debe), float(haber)] for cuenta, debe, haber in env.cr.fetchall()}


def neto(sumas):
    """Suma de (debe − haber) de un diccionario de ``saldos``."""
    return sum(d - h for d, h in sumas.values())


def por_tipo(env, empresas, desde=None, hasta=None, borradores=False):
    """{tipo de cuenta: debe − haber}."""
    env.cr.execute("""
        SELECT a.account_type, COALESCE(SUM(l.debit - l.credit), 0)
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
          JOIN account_account a ON a.id = l.account_id
         WHERE m.state IN %s AND l.company_id IN %s AND a.account_type <> 'off_balance'
           AND (%s::date IS NULL OR l.date >= %s) AND (%s::date IS NULL OR l.date <= %s)
         GROUP BY a.account_type
    """, [_estados(borradores), tuple(empresas.ids), desde, desde, hasta, hasta])
    return {tipo: float(v) for tipo, v in env.cr.fetchall()}


def impuestos(env, empresas, desde, hasta, borradores=False):
    """{impuesto_id: {'base': Σ balance de las líneas con ese impuesto, 'cuota': Σ balance de sus líneas de impuesto}}."""
    resultado = defaultdict(lambda: {'base': 0.0, 'cuota': 0.0})
    estados = _estados(borradores)
    env.cr.execute("""
        SELECT r.account_tax_id, COALESCE(SUM(l.balance), 0)
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
          JOIN account_move_line_account_tax_rel r ON r.account_move_line_id = l.id
         WHERE m.state IN %s AND l.company_id IN %s AND l.date BETWEEN %s AND %s
         GROUP BY r.account_tax_id
    """, [estados, tuple(empresas.ids), desde, hasta])
    for impuesto, valor in env.cr.fetchall():
        resultado[impuesto]['base'] = float(valor)
    env.cr.execute("""
        SELECT l.tax_line_id, COALESCE(SUM(l.balance), 0)
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
         WHERE m.state IN %s AND l.company_id IN %s AND l.date BETWEEN %s AND %s AND l.tax_line_id IS NOT NULL
         GROUP BY l.tax_line_id
    """, [estados, tuple(empresas.ids), desde, hasta])
    for impuesto, valor in env.cr.fetchall():
        resultado[impuesto]['cuota'] = float(valor)
    return dict(resultado)


def pendientes(env, empresas, tipo_cuenta, corte, borradores=False):
    """Lo pendiente de cada apunte de cobrar/pagar A LA FECHA ``corte``.

    [(apunte_id, tercero_id, vencimiento, pendiente_en_signo_natural)]. Un cruce cuenta solo si su ``max_date``
    (la fecha en que se hizo efectivo) es anterior o igual al corte; lo cruzado después sigue pendiente.
    """
    signo = 1 if tipo_cuenta == 'asset_receivable' else -1
    env.cr.execute("""
        SELECT l.id, l.partner_id, COALESCE(l.date_maturity, l.date), l.balance,
               COALESCE((SELECT SUM(p.amount) FROM account_partial_reconcile p
                          WHERE p.debit_move_id = l.id AND p.max_date <= %(corte)s), 0)
             - COALESCE((SELECT SUM(p.amount) FROM account_partial_reconcile p
                          WHERE p.credit_move_id = l.id AND p.max_date <= %(corte)s), 0)
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
          JOIN account_account a ON a.id = l.account_id
         WHERE m.state IN %(estados)s AND l.company_id IN %(empresas)s AND a.account_type = %(tipo)s
           AND l.date <= %(corte)s
    """, {'estados': _estados(borradores), 'empresas': tuple(empresas.ids), 'tipo': tipo_cuenta, 'corte': corte})
    filas = []
    for apunte, tercero, vence, balance, aplicado in env.cr.fetchall():
        pendiente = round(signo * (float(balance) - float(aplicado)), 2)
        if pendiente:
            filas.append((apunte, tercero, vence, pendiente))
    return filas


def tramo(dias):
    """El mismo reparto de días que muestra la pantalla: por vencer, 1-30, 31-60, 61-90, 91-120, más de 120."""
    if dias <= 0:
        return 'por_vencer'
    for tope, clave in ((30, 'd1_30'), (60, 'd31_60'), (90, 'd61_90'), (120, 'd91_120')):
        if dias <= tope:
            return clave
    return 'mas_120'


def analitica(env, empresas, columna, desde, hasta):
    """{cuenta analítica: (ingresos, costos)} del plan cuya cuenta vive en ``columna`` de la línea analítica."""
    env.cr.execute(f"""
        SELECT {columna},
               COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0),
               COALESCE(-SUM(amount) FILTER (WHERE amount < 0), 0)
          FROM account_analytic_line
         WHERE {columna} IS NOT NULL AND date BETWEEN %s AND %s AND company_id IN %s
         GROUP BY {columna}
    """, [desde, hasta, tuple(empresas.ids)])
    return {cuenta: (float(i), float(c)) for cuenta, i, c in env.cr.fetchall()}
