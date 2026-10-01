#!/usr/bin/env python3
"""Campaña completa: arranque en frío, memoria en reposo/caliente/bajo carga, latencia y CPU.

Uso: campana.py <etiqueta> <workers> <cron> <shared_buffers> [reps] [--db r3_med_base] [--port 8170]
Reinicia el clúster propio (5441) con shared_buffers dado y, en cada repetición, arranca Odoo de
cero. Escribe una línea JSON por repetición en res_campana.jsonl.
"""
import json
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import medir  # noqa: E402

PGDATA = '/tmp/r3_med_pgdata'


def sh(*a, **kw):
    return subprocess.run(a, check=True, capture_output=True, text=True, **kw).stdout.strip()


def pg_reinicia(sb, extra=''):
    subprocess.run([f'{AQUI}/pg_propio.sh', 'stop'], capture_output=True)
    sh(f'{AQUI}/pg_propio.sh', 'start', sb, *extra.split())
    time.sleep(1)


def matar(pid):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(100):
        if not os.path.exists(f'/proc/{pid}'):
            return
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)


def mem_ambos(pid):
    o = medir.mem(medir.hijos(pid))
    p = medir.mem(medir.pg_pids(PGDATA))
    return {'odoo_rss': round(o[0] / 1024), 'odoo_pss': round(o[1] / 1024),
            'pg_rss': round(p[0] / 1024), 'pg_pss': round(p[1] / 1024),
            'total_pss': round((o[1] + p[1]) / 1024)}


def una(etiqueta, workers, cron, sb, port, db, rep, maxconn='16', extra_odoo=()):
    env = dict(os.environ, DB=db, TAG=f'{etiqueta}_{rep}')
    base = f'http://127.0.0.1:{port}'
    t0 = time.time()
    pid = int(sh(f'{AQUI}/odoo_run.sh', str(port), str(workers), str(cron), maxconn, *extra_odoo, env=env))
    res = {'etiqueta': etiqueta, 'rep': rep, 'workers': workers, 'cron': cron, 'shared_buffers': sb, 'db': db}
    try:
        medir.esperar(base + '/', 600)
        res['arranque_s'] = round(time.time() - t0, 2)
        time.sleep(10)
        res['mem_reposo'] = mem_ambos(pid)
        medir.calentar_silencioso = True
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            medir.calentar(base)
            medir.calentar(base)
        time.sleep(2)
        res['mem_caliente'] = mem_ambos(pid)
        res['lat_secuencial'] = medir.lat_secuencial(base, pid, 30)
        res['carga_20'] = medir.carga(base, pid, 20, 400, PGDATA)
        res['carga_50'] = medir.carga(base, pid, 50, 1000, PGDATA)
        time.sleep(5)
        res['mem_tras_carga'] = mem_ambos(pid)
    finally:
        matar(pid)
    return res


if __name__ == '__main__':
    args = sys.argv[1:]
    def opt(n, d):
        if n in args:
            i = args.index(n)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return d
    db = opt('--db', 'r3_med_base')
    port = int(opt('--port', '8170'))
    pgextra = opt('--pgextra', '')
    etiqueta, workers, cron, sb, *r = args
    reps = int(r[0]) if r else 3
    pg_reinicia(sb, pgextra)
    with open(f'{AQUI}/res_campana.jsonl', 'a') as f:
        for rep in range(1, reps + 1):
            res = una(etiqueta, workers, cron, sb, port, db, rep)
            f.write(json.dumps(res) + '\n')
            f.flush()
            print(json.dumps({k: res[k] for k in ('etiqueta', 'rep', 'arranque_s', 'mem_reposo', 'mem_caliente',
                                                  'mem_tras_carga')}))
            print('  carga50', {k: res['carga_50'][k] for k in ('rps', 'cpu_ms_por_peticion', 'pico_pss_odoo_MiB',
                                                                 'pico_pss_pg_MiB', 'pico_pss_total_MiB', 'errores')})
