#!/usr/bin/env python3
"""Costo mensual de R2 para WAL + respaldos base + pg_dump diario, con tarifas OFICIALES.
Fuente: https://developers.cloudflare.com/r2/pricing/ (Last updated 2026-08-07, consultada 2026-10-01):
almacenamiento estándar $0,015/GB-mes; Clase A $4,50/M; Clase B $0,36/M; gratis/mes: 10 GB-mes,
1 M Clase A, 10 M Clase B; se redondea al siguiente millón / GB.
Clase A = PUT/POST/LIST (mutan o listan); Clase B = GET/HEAD.
Los parámetros por defecto son los MEDIDOS en el prototipo (ver datos.md §2); cámbialos por argumento.
"""
import argparse, math

p = argparse.ArgumentParser()
p.add_argument("--wal-por-hora", type=float, default=60)       # archive_timeout=60 y cron por minuto
p.add_argument("--a-por-wal", type=float, default=1)           # PUT por segmento (medido)
p.add_argument("--b-por-wal", type=float, default=2)           # GET/HEAD por segmento (medido)
p.add_argument("--kib-por-wal", type=float, default=60)        # tamaño comprimido+cifrado medido
p.add_argument("--base-mb", type=float, default=103)           # respaldo base medido (pgBackRest)
p.add_argument("--a-por-base", type=float, default=4600)       # PUT por respaldo base sin bundle
p.add_argument("--bases-por-mes", type=float, default=4.3)     # semanal
p.add_argument("--bases-retenidas", type=float, default=2)     # repo1-retention-full=2
p.add_argument("--dias-wal", type=float, default=14)           # WAL retenido (~2 semanas con 2 completos semanales)
p.add_argument("--dump-mb", type=float, default=114)           # pg_dump -Fc diario medido
p.add_argument("--dumps-retenidos", type=float, default=23)    # 7 diarios + 4 semanales + 12 mensuales
p.add_argument("--restauraciones-por-mes", type=float, default=31)  # prueba diaria + arranques
p.add_argument("--b-por-restauracion", type=float, default=3600)
a = p.parse_args()

h = 720
wal_mes = a.wal_por_hora * h
clase_a = wal_mes * a.a_por_wal + a.bases_por_mes * a.a_por_base + 30 * 2
clase_b = wal_mes * a.b_por_wal + a.restauraciones_por_mes * a.b_por_restauracion
gb = (a.base_mb * a.bases_retenidas + a.wal_por_hora * 24 * a.dias_wal * a.kib_por_wal / 1024
      + a.dump_mb * a.dumps_retenidos) / 1024
ca = max(0, math.ceil((clase_a - 1e6) / 1e6)) * 4.50
cb = max(0, math.ceil((clase_b - 10e6) / 1e6)) * 0.36
cs = max(0, math.ceil(gb - 10)) * 0.015
print(f"Clase A/mes: {clase_a:,.0f} (gratis 1 000 000) -> ${ca:.2f}")
print(f"Clase B/mes: {clase_b:,.0f} (gratis 10 000 000) -> ${cb:.2f}")
print(f"Almacenamiento: {gb:.2f} GB-mes (gratis 10) -> ${cs:.2f}")
print(f"TOTAL R2: ${ca+cb+cs:.2f}/mes")
