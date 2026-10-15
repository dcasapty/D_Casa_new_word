"""Cálculo INDEPENDIENTE de «lo real» de un presupuesto, directo en SQL (ayuda de pruebas, no es un test).

No usa el modelo ``dcasa.presupuesto`` ni el ORM de los apuntes: lee ``account_move_line`` y ``account_move`` tal como
están en la base. Regla: cuentan solo los asientos PUBLICADOS con fecha dentro del periodo; los ingresos, pasivos y
patrimonio (naturaleza acreedora) se presentan en positivo cuando tienen más haber que debe; lo demás, al revés.
Con cuenta analítica solo cuenta el porcentaje de cada apunte que la distribución le asigna.
"""

ACREEDORAS = ('income', 'income_other', 'liability_payable', 'liability_credit_card', 'liability_current',
              'liability_non_current', 'equity', 'equity_unaffected')


def saldo(env, empresa, cuenta, desde, hasta, analitica=None, borradores=False):
    """Σ (debe − haber) de los apuntes de ``cuenta`` con fecha en [desde, hasta]; con ``analitica``, solo su parte."""
    estados = ('posted', 'draft') if borradores else ('posted',)
    env.flush_all()
    if analitica:
        env.cr.execute("""
            SELECT COALESCE(SUM(l.balance * e.value::numeric / 100), 0)
              FROM account_move_line l
              JOIN account_move m ON m.id = l.move_id
              CROSS JOIN LATERAL jsonb_each_text(l.analytic_distribution) AS e(clave, value)
             WHERE m.state IN %s AND l.company_id = %s AND l.account_id = %s AND l.date BETWEEN %s AND %s
               AND %s = ANY(string_to_array(e.clave, ','))
        """, [estados, empresa.id, cuenta.id, desde, hasta, str(analitica.id)])
    else:
        env.cr.execute("""
            SELECT COALESCE(SUM(l.debit - l.credit), 0)
              FROM account_move_line l
              JOIN account_move m ON m.id = l.move_id
             WHERE m.state IN %s AND l.company_id = %s AND l.account_id = %s AND l.date BETWEEN %s AND %s
        """, [estados, empresa.id, cuenta.id, desde, hasta])
    return float(env.cr.fetchone()[0])


def real(env, empresa, cuenta, desde, hasta, analitica=None, borradores=False):
    """Lo ejecutado con el signo natural de la cuenta (ingresos y gastos en positivo)."""
    valor = saldo(env, empresa, cuenta, desde, hasta, analitica, borradores)
    return round(-valor if cuenta.account_type in ACREEDORAS else valor, 2)


def real_analitico_por_lineas(env, empresa, cuenta, analitica, desde, hasta):
    """Segunda vía para lo analítico: las líneas analíticas que Odoo crea al publicar (otra tabla, otro camino)."""
    columna = analitica.plan_id._column_name()
    env.flush_all()
    env.cr.execute(f"""
        SELECT COALESCE(SUM(l.amount), 0)
          FROM account_analytic_line l
         WHERE l.{columna} = %s AND l.general_account_id = %s AND l.company_id = %s AND l.date BETWEEN %s AND %s
    """, [analitica.id, cuenta.id, empresa.id, desde, hasta])
    valor = float(env.cr.fetchone()[0])      # la línea analítica es haber − debe: ingresos en positivo
    return round(valor if cuenta.account_type in ACREEDORAS else -valor, 2)
