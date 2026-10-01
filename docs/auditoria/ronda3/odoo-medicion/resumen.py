#!/usr/bin/env python3
"""Mediana y rango [mín-máx] por etiqueta de res_campana.jsonl (las tablas del informe salen de aquí)."""
import json
import os
import statistics
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
f = sys.argv[1] if len(sys.argv) > 1 else f'{AQUI}/res_campana.jsonl'
por = {}
for line in open(f):
    r = json.loads(line)
    por.setdefault(r['etiqueta'], []).append(r)


def m(xs):
    xs = [x for x in xs if x is not None]
    return f'{statistics.median(xs):g} [{min(xs):g}-{max(xs):g}]' if xs else '-'


for et, rs in por.items():
    print(f'\n## {et} (n={len(rs)}, workers={rs[0]["workers"]}, cron={rs[0]["cron"]}, '
          f'db_maxconn={rs[0].get("db_maxconn", "16")}, shared_buffers={rs[0]["shared_buffers"]})')
    print('arranque_s', m([r['arranque_s'] for r in rs]))
    for fase in ('mem_reposo', 'mem_caliente', 'mem_tras_carga'):
        print(fase, {k: m([r[fase][k] for r in rs]) for k in rs[0][fase]})
    for c in ('carga_20', 'carga_50'):
        print(c, {k: m([r[c][k] for r in rs]) for k in ('ok', 'rps', 'cpu_ms_por_peticion', 'pico_pss_odoo_MiB',
                                                       'pico_pss_pg_MiB', 'pico_pss_total_MiB', 'pico_rss_odoo_MiB')})
        print('   errores', [sum(v for k, v in r[c]['errores'].items() if k != 'codigos') if r[c]['errores'] else 0
                             for r in rs], [r[c]['errores'].get('codigos') if r[c]['errores'] else {} for r in rs])
        print('   lat p50/p95 ms', {k: (m([r[c]['lat_ms'][k]['p50'] for r in rs]), m([r[c]['lat_ms'][k]['p95'] for r in rs]))
                                    for k in rs[0][c]['lat_ms']})
    print('secuencial p50 / p95 / cpu_ms', {k: (m([r['lat_secuencial'][k]['p50_ms'] for r in rs]),
                                               m([r['lat_secuencial'][k]['p95_ms'] for r in rs]),
                                               m([r['lat_secuencial'][k]['cpu_ms'] for r in rs]))
                                           for k in rs[0]['lat_secuencial']})
