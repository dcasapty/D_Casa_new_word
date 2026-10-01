"""TCO a 12 y 24 meses de los tres caminos (r3-reconstruccion, 2026-10-01).

Todas las cifras de infraestructura vienen de la documentación oficial de Cloudflare
leída vía MCP (o de los informes r3-cf-plataforma / ronda2 cf-costos que la citan).
Las horas y el valor de la hora son SUPUESTOS explícitos: cámbialos aquí y vuelve a correr.

Uso: python3 docs/auditoria/ronda3/reconstruccion/tco.py
"""

VALOR_HORA = 15.0      # USD/h · SUPUESTO: costo de oportunidad del dueño-programador (no medido)
H_SEMANA = 40

# ---------------- Infraestructura mensual (USD) -----------------------------
INFRA = {
    # Workers Paid $5 (https://developers.cloudflare.com/workers/platform/pricing/, 2026-08-28)
    'worker': 5.00,
    # Odoo en VPS + Tunnel + R2 de respaldos: $12-17 con el Worker (ronda2/cf-costos.md §6) → VPS sin Worker ≈ 7-12
    'odoo_vps': (7.0, 12.0),
    # Odoo en Container standard-1 24/7, CPU 10 %, SIN los $5 del plan (r3-cf-plataforma: 34,24 con plan)
    'odoo_container_247': 29.24,
    # Odoo en Container standard-1 en horario 12 h x 26 d, sin plan (r3-cf-plataforma: 16,6-18,9 con plan)
    'odoo_container_horario': (11.6, 13.9),
    # PostgreSQL gestionado (Neon) 24/7 ≈ 19,8 (ronda2 cf-costos); en horario con autosuspensión ≈ 8-12 (SUPUESTO)
    'pg_247': 19.8,
    'pg_horario': (8.0, 12.0),
    # Nativo: D1/DO/R2/Queues/Workflows dentro de lo incluido en Paid para este volumen (ver §4.3); margen 0-2
    'nativo_extra': (0.0, 2.0),
}


def rango(x):
    return x if isinstance(x, tuple) else (x, x)


def suma(*xs):
    lo = sum(rango(x)[0] for x in xs)
    hi = sum(rango(x)[1] for x in xs)
    return lo, hi


# ---------------- Caminos ------------------------------------------------------
# Cada camino: infraestructura mensual por tramo y semanas de desarrollo por año.
# Semanas = rango (bajo, alto). Mantenimiento en h/semana.
CAMINOS = {
    '1a · Odoo adelgazado en VPS': {
        'infra': [(24, suma(INFRA['worker'], INFRA['odoo_vps']))],
        'semanas_a1': (6 + 3, 10 + 6),   # P0/P1 a producción + FE DGI
        'semanas_a2': (3, 6),            # migración a Odoo 20/21 antes de sep-2028
        'mant_h_sem': 4,
        # riesgo: P(migración se duplica)=0,3 x (3-6 sem)
        'riesgo_usd': (0.3 * 3 * H_SEMANA * VALOR_HORA, 0.3 * 6 * H_SEMANA * VALOR_HORA),
    },
    '1b · Odoo adelgazado en Container 24/7 + Neon': {
        'infra': [(24, suma(INFRA['worker'], INFRA['odoo_container_247'], INFRA['pg_247']))],
        'semanas_a1': (6 + 3, 10 + 6),
        'semanas_a2': (3, 6),
        'mant_h_sem': 4,
        'riesgo_usd': (0.3 * 3 * H_SEMANA * VALOR_HORA, 0.3 * 6 * H_SEMANA * VALOR_HORA),
    },
    '2 · Reconstrucción total nativa': {
        # Mientras se reconstruye, el negocio necesita facturar: Odoo mínimo en VPS los primeros 15 meses
        # (si no, se retrasa el lanzamiento 1,1-1,6 años). Después solo $5 + extra.
        'infra': [(15, suma(INFRA['worker'], INFRA['odoo_vps'])), (9, suma(INFRA['worker'], INFRA['nativo_extra']))],
        # año 1: P0 mínimo de Odoo (6-10) + reconstrucción hasta completar 46 semanas; año 2: resto + FE nativa
        'semanas_total': (6 + 57 + 3, 10 + 83 + 6),
        'mant_h_sem': 6,
        # riesgos: P=0,5 de pasarse +30 % (17-25 sem); P=0,3 de error contable material (1 000-3 000 USD)
        'riesgo_usd': (0.5 * 17 * H_SEMANA * VALOR_HORA + 0.3 * 1000, 0.5 * 25 * H_SEMANA * VALOR_HORA + 0.3 * 3000),
    },
    '3 · Híbrido por fases (strangler)': {
        # Meses 1-3 Odoo en VPS completo; desde el 4 el sitio/socios/Brian en el borde y Odoo back-office en VPS.
        'infra': [(24, suma(INFRA['worker'], INFRA['odoo_vps']))],
        'semanas_a1': (6 + 3 + 10, 10 + 6 + 15),  # P0 + FE DGI en Odoo + sitio/socios/Brian al borde
        'semanas_a2': (2, 4),                      # migración de Odoo con menos superficie (sin website/socios)
        'mant_h_sem': 5,
        # riesgo: P=0,2 de error de sincronización (pedidos duplicados/perdidos) x 500 USD + P=0,3 migración x2
        'riesgo_usd': (0.2 * 500 + 0.3 * 2 * H_SEMANA * VALOR_HORA, 0.2 * 500 + 0.3 * 4 * H_SEMANA * VALOR_HORA),
    },
}


def infra_meses(tramos, meses):
    lo = hi = 0.0
    restante = meses
    for dur, (a, b) in tramos:
        m = min(dur, restante)
        lo += m * a
        hi += m * b
        restante -= m
        if restante <= 0:
            break
    return lo, hi


def semanas(c, meses):
    if 'semanas_total' in c:
        lo, hi = c['semanas_total']
        cap = 46 * (meses / 12)       # máximo de semanas trabajables en el periodo
        return min(lo, cap), min(hi, cap)
    a1 = c['semanas_a1']
    if meses <= 12:
        return a1
    a2 = c['semanas_a2']
    return a1[0] + a2[0], a1[1] + a2[1]


print(f'VALOR_HORA = ${VALOR_HORA}/h (SUPUESTO) · {H_SEMANA} h/semana\n')
print(f"{'Camino':48} {'Mes':>4} {'Infra USD':>15} {'Horas dev+mant':>17} {'USD horas':>17} {'Riesgo USD':>13} {'TOTAL USD':>17}")
for nombre, c in CAMINOS.items():
    for meses in (12, 24):
        i_lo, i_hi = infra_meses(c['infra'], meses)
        s_lo, s_hi = semanas(c, meses)
        sem_dev_lo, sem_dev_hi = s_lo, s_hi
        # mantenimiento solo en las semanas que no son de desarrollo
        sem_libres_lo = max(0, 46 * meses / 12 - sem_dev_hi)
        sem_libres_hi = max(0, 46 * meses / 12 - sem_dev_lo)
        h_lo = sem_dev_lo * H_SEMANA + sem_libres_lo * c['mant_h_sem']
        h_hi = sem_dev_hi * H_SEMANA + sem_libres_hi * c['mant_h_sem']
        r_lo, r_hi = c['riesgo_usd']
        if meses == 12 and '2 ·' not in nombre:
            r_lo, r_hi = r_lo * 0.3, r_hi * 0.3      # la migración de Odoo cae en el año 2
        t_lo = i_lo + h_lo * VALOR_HORA + r_lo
        t_hi = i_hi + h_hi * VALOR_HORA + r_hi
        print(f'{nombre:48} {meses:>4} {i_lo:>7.0f}–{i_hi:<7.0f} {h_lo:>8.0f}–{h_hi:<8.0f} '
              f'{h_lo*VALOR_HORA:>8.0f}–{h_hi*VALOR_HORA:<8.0f} {r_lo:>6.0f}–{r_hi:<6.0f} {t_lo:>8.0f}–{t_hi:<8.0f}')
print('\nNotas: tokens de IA, dominio, PAC de la FE DGI y correo no se incluyen (iguales en los tres caminos).')
print('El camino 2 en 12 meses NO ha terminado: el negocio sigue sobre Odoo mínimo.')
