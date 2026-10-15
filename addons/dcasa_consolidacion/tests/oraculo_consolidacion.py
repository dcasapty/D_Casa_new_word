"""Cálculo INDEPENDIENTE de la consolidación, directo en SQL (ayuda de pruebas, no es un test).

No usa ``dcasa.consolidacion.motor`` ni los reportes: lee ``account_move_line`` tal como está en la base. Reglas:

* cuentan solo los asientos publicados;
* una operación es «entre empresas» cuando el tercero del apunte es la ficha (o un contacto de la ficha) de OTRA empresa
  del grupo; las líneas de impuesto no cuentan (el ITBMS se debe a la DGI, no a la otra empresa);
* solo se eliminan por cobrar y por pagar (balance) e ingresos y gastos (resultados).

``consolidado`` = suma de las empresas − lo eliminado, por tipo de cuenta, con el signo crudo (debe − haber).
"""
from collections import defaultdict

ACTIVOS = ('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments', 'asset_non_current', 'asset_fixed')
PASIVOS = ('liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current')
PATRIMONIO = ('equity', 'equity_unaffected')
RESULTADOS = ('income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')
BALANCE = ACTIVOS + PASIVOS + PATRIMONIO
ELIMINABLES_BALANCE = ('asset_receivable', 'liability_payable')


def por_empresa_y_tipo(env, empresas, desde=None, hasta=None, tipos=None):
    """{(empresa_id, tipo): [debe, haber]} de los apuntes publicados."""
    env.flush_all()
    env.cr.execute("""
        SELECT l.company_id, a.account_type, COALESCE(SUM(l.debit), 0), COALESCE(SUM(l.credit), 0)
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
          JOIN account_account a ON a.id = l.account_id
         WHERE m.state = 'posted' AND l.company_id IN %s AND a.account_type IN %s
           AND (%s::date IS NULL OR l.date >= %s) AND (%s::date IS NULL OR l.date <= %s)
         GROUP BY l.company_id, a.account_type
    """, [tuple(empresas.ids), tuple(tipos or BALANCE + RESULTADOS), desde, desde, hasta, hasta])
    return {(empresa, tipo): [float(debe), float(haber)] for empresa, tipo, debe, haber in env.cr.fetchall()}


def entre_empresas(env, empresas, desde=None, hasta=None, tipos=None):
    """{(empresa_id, tipo): [debe, haber]} de los apuntes cuyo tercero es OTRA empresa del grupo (sin impuestos)."""
    env.flush_all()
    env.cr.execute("""
        SELECT l.company_id, a.account_type, COALESCE(SUM(l.debit), 0), COALESCE(SUM(l.credit), 0)
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
          JOIN account_account a ON a.id = l.account_id
          JOIN res_partner p ON p.id = l.partner_id
          JOIN res_company c ON c.partner_id = COALESCE(p.commercial_partner_id, p.id)
         WHERE m.state = 'posted' AND l.company_id IN %s AND c.id IN %s AND c.id <> l.company_id
           AND l.tax_line_id IS NULL AND a.account_type IN %s
           AND (%s::date IS NULL OR l.date >= %s) AND (%s::date IS NULL OR l.date <= %s)
         GROUP BY l.company_id, a.account_type
    """, [tuple(empresas.ids), tuple(empresas.ids), tuple(tipos or BALANCE + RESULTADOS), desde, desde, hasta, hasta])
    return {(empresa, tipo): [float(debe), float(haber)] for empresa, tipo, debe, haber in env.cr.fetchall()}


def neto(sumas, empresa_id=None, tipos=None):
    """Σ (debe − haber) de las celdas de ``sumas`` (de una empresa y unos tipos, o de todas)."""
    return sum(d - h for (e, t), (d, h) in sumas.items()
               if (empresa_id is None or e == empresa_id) and (tipos is None or t in tipos))


def eliminaciones(env, empresas, tipos_eliminables, desde=None, hasta=None):
    """Lo que se elimina, con el signo crudo (debe − haber) de lo eliminado, por tipo: {tipo: valor}."""
    interno = entre_empresas(env, empresas, desde, hasta, tipos_eliminables)
    resultado = defaultdict(float)
    for (_empresa, tipo), (debe, haber) in interno.items():
        resultado[tipo] += debe - haber
    return dict(resultado)
