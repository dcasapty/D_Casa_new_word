#!/usr/bin/env python3
"""Actividad de Odoo en reposo contra la base (task 7).

Uso: reposo.py <etiqueta> <workers> <cron> <minutos> [--ws]
Reinicia el clúster propio con log_min_duration_statement=0 (todas las sentencias al log) y
pg_stat_statements; arranca Odoo, calienta, espera 30 s y luego, durante <minutos>, sin tráfico:
  - muestrea pg_stat_activity cada 5 s (conexiones por estado y aplicación)
  - cuenta sentencias en pg_stat_statements (top por llamadas) y en el log por minuto
  - mide CPU (utime+stime) de Odoo y de PostgreSQL
--ws abre además un websocket del bus (como un navegador con el backend abierto).
Resultado: una línea JSON en res_reposo.jsonl.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import campana  # noqa: E402
import medir  # noqa: E402

PG = ['psql', '-h', 'localhost', '-p', '5441', '-U', 'odoo', '-d', 'r3_med_base', '-Atc']
os.environ['PGPASSWORD'] = 'odoo'


def q(sql):
    return subprocess.run(PG + [sql], capture_output=True, text=True, check=True).stdout.strip()


def ws_abierto(base, parar):
    """Websocket del bus con sesión admin, suscrito como lo hace el cliente web."""
    try:
        import websocket  # websocket-client
    except ImportError:
        return
    import httpx
    with httpx.Client(base_url=base) as c:
        medir.sesion(c)
        cookie = '; '.join(f'{k}={v}' for k, v in c.cookies.items())
    ws = websocket.create_connection(base.replace('http', 'ws') + '/websocket', header=[f'Cookie: {cookie}'],
                                     origin=base)
    ws.send(json.dumps({'event_name': 'subscribe', 'data': {'channels': [], 'last': 0}}))
    ws.settimeout(1)
    while not parar.is_set():
        try:
            ws.recv()
        except Exception:  # noqa: BLE001 - timeout de lectura
            pass
    ws.close()


if __name__ == '__main__':
    etiqueta, workers, cron, minutos = sys.argv[1:5]
    con_ws = '--ws' in sys.argv
    campana.pg_reinicia('128MB', '-c log_min_duration_statement=0 -c log_line_prefix=%m|%a|%p|_ '
                                 '-c log_connections=on -c log_disconnections=on')
    log = '/tmp/r3_med_pgdata/server.log'
    port = 8172
    base = f'http://127.0.0.1:{port}'
    pid = int(subprocess.run([f'{AQUI}/odoo_run.sh', str(port), workers, cron, '16'], capture_output=True, text=True,
                             env=dict(os.environ, TAG=f'reposo_{etiqueta}'), check=True).stdout)
    try:
        medir.esperar(base + '/', 300)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            medir.calentar(base)
        parar = threading.Event()
        if con_ws:
            threading.Thread(target=ws_abierto, args=(base, parar), daemon=True).start()
        time.sleep(30)
        q('select pg_stat_statements_reset()')
        log_ini = os.path.getsize(log)
        c_odoo0 = medir.cpu(medir.hijos(pid))
        c_pg0 = medir.cpu(medir.pg_pids('/tmp/r3_med_pgdata'))
        muestras = []
        t_fin = time.time() + float(minutos) * 60
        while time.time() < t_fin:
            filas = q("select coalesce(application_name,''), state, count(*) from pg_stat_activity "
                      "where datname='r3_med_base' and pid<>pg_backend_pid() group by 1,2")
            muestras.append({'t': round(time.time()), 'conexiones': filas.replace('\n', ' ; ')})
            time.sleep(5)
        c_odoo1 = medir.cpu(medir.hijos(pid))
        c_pg1 = medir.cpu(medir.pg_pids('/tmp/r3_med_pgdata'))
        parar.set()
        top = q("select calls, left(regexp_replace(query, '\\s+', ' ', 'g'), 110) from pg_stat_statements "
                "where query not like '%pg_stat%' order by calls desc limit 12")
        total_calls = q("select coalesce(sum(calls),0) from pg_stat_statements where query not like '%pg_stat%' "
                        "and query not like '%pg_backend_pid%'")
        with open(log, errors='replace') as f:
            f.seek(log_ini)
            lineas = [line for line in f if 'statement:' in line and 'pg_stat' not in line
                      and 'pg_backend_pid' not in line]
        por_min = {}
        for line in lineas:
            m = re.match(r'(\d{4}-\d\d-\d\d \d\d:\d\d)', line)
            if m:
                por_min[m.group(1)] = por_min.get(m.group(1), 0) + 1
        mx = max((sum(int(x.split('|')[-1]) for x in s['conexiones'].split(' ; ') if x) for s in muestras), default=0)
        res = {
            'etiqueta': etiqueta, 'workers': workers, 'cron': cron, 'ws': con_ws, 'minutos': float(minutos),
            'cpu_odoo_s': round(c_odoo1 - c_odoo0, 2), 'cpu_pg_s': round(c_pg1 - c_pg0, 2),
            'cpu_odoo_s_por_hora': round((c_odoo1 - c_odoo0) * 60 / float(minutos), 1),
            'cpu_pg_s_por_hora': round((c_pg1 - c_pg0) * 60 / float(minutos), 1),
            'sentencias_total': int(total_calls), 'sentencias_log_por_minuto': por_min,
            'conexiones_max': mx, 'conexiones_muestras': [muestras[0], muestras[len(muestras) // 2], muestras[-1]],
            'top_sentencias': top.split('\n'),
            'mem_odoo': medir.mem(medir.hijos(pid)),
        }
        with open(f'{AQUI}/res_reposo.jsonl', 'a') as f:
            f.write(json.dumps(res) + '\n')
        print(json.dumps(res, indent=1))
    finally:
        campana.matar(pid)
