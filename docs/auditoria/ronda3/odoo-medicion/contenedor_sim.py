#!/usr/bin/env python3
"""Simula un tipo de instancia de Containers con cgroups v1 (memoria + cuota de CPU) y mete DENTRO
Odoo y PostgreSQL (clúster propio 5441) o solo Odoo.

Uso: contenedor_sim.py <etiqueta> <mem_MiB> <vcpu> <workers> <cron> <db_maxconn> <shared_buffers>
                       <pg_max_connections> [--solo-odoo] [--reps 3]
Mide: arranque hasta el primer 200 en / (bajo la cuota de CPU), regeneración de bundles, carga
20 conc. (400 pet.) y 50 conc. (600 pet.), pico de memoria del cgroup (memory.max_usage_in_bytes,
incluye caché de página), pico de RSS anónimo (muestreo de memory.stat total_rss), fallos de
límite (failcnt) y OOM kills. Resultado: res_contenedor_sim.jsonl.
No representa el hardware de Cloudflare: la cuota de CPU simula la fracción de vCPU, no su velocidad.
"""
import json
import os
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import campana  # noqa: E402
import medir  # noqa: E402

MEM = '/sys/fs/cgroup/memory/r3_med'
CPU = '/sys/fs/cgroup/cpu/r3_med'


def escribir(ruta, valor):
    with open(ruta, 'w') as f:
        f.write(str(valor))


def leer(ruta):
    with open(ruta) as f:
        return f.read()


def stat():
    return {k: int(v) for k, v in (line.split() for line in leer(f'{MEM}/memory.stat').splitlines())}


def preparar(mem_mib, vcpu):
    os.makedirs(MEM, exist_ok=True)
    os.makedirs(CPU, exist_ok=True)
    escribir(f'{MEM}/memory.limit_in_bytes', mem_mib * 1024 * 1024)
    try:
        escribir(f'{MEM}/memory.memsw.limit_in_bytes', mem_mib * 1024 * 1024)  # sin swap, como Containers
    except OSError:
        pass
    escribir(f'{CPU}/cpu.cfs_period_us', 100000)
    escribir(f'{CPU}/cpu.cfs_quota_us', int(100000 * vcpu))


def en_cgroup(cmd, env=None):
    envolt = f'echo $$ > {MEM}/cgroup.procs; echo $$ > {CPU}/cgroup.procs; exec {cmd}'
    return subprocess.run(['bash', '-c', envolt], capture_output=True, text=True, env=env)


class Pico(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.rss = 0
        self.alto = threading.Event()

    def run(self):
        while not self.alto.is_set():
            try:
                s = stat()
                self.rss = max(self.rss, s.get('total_rss', s.get('rss', 0)) + s.get('total_shmem', 0))
            except OSError:
                pass
            time.sleep(0.2)


def oom_kills():
    for line in leer(f'{MEM}/memory.oom_control').splitlines():
        if line.startswith('oom_kill '):
            return int(line.split()[1])
    return -1


if __name__ == '__main__':
    a = sys.argv[1:]
    solo_odoo = '--solo-odoo' in a
    reps = int(a[a.index('--reps') + 1]) if '--reps' in a else 3
    etiqueta, mem_mib, vcpu, workers, cron, maxconn, sb, pgmax = a[:8]
    mem_mib, vcpu = int(mem_mib), float(vcpu)
    preparar(mem_mib, vcpu)
    # PostgreSQL: dentro del cgroup o fuera (BD externa)
    subprocess.run([f'{AQUI}/pg_propio.sh', 'stop'], capture_output=True)
    cmd_pg = f'{AQUI}/pg_propio.sh start {sb} -c max_connections={pgmax}'
    r = en_cgroup(cmd_pg) if not solo_odoo else subprocess.run(['bash', '-c', cmd_pg], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    port = 8173
    base = f'http://127.0.0.1:{port}'
    for rep in range(1, reps + 1):
        escribir(f'{MEM}/memory.max_usage_in_bytes', 0)
        escribir(f'{MEM}/memory.failcnt', 0)
        oom0 = oom_kills()
        res = {'etiqueta': etiqueta, 'rep': rep, 'mem_MiB': mem_mib, 'vcpu': vcpu, 'workers': workers, 'cron': cron,
               'db_maxconn': maxconn, 'shared_buffers': sb, 'pg_max_connections': pgmax, 'solo_odoo': solo_odoo}
        pico = Pico()
        pico.start()
        t0 = time.time()
        env = dict(os.environ, TAG=f'sim_{etiqueta}_{rep}',
                   LIMSOFT=str(int(mem_mib * 1024 * 1024 * 0.45)), LIMHARD=str(int(mem_mib * 1024 * 1024 * 0.6)))
        r = en_cgroup(f'{AQUI}/odoo_run.sh {port} {workers} {cron} {maxconn}', env=env)
        pid = int(r.stdout.strip())
        try:
            res['arranque_s'] = round(medir.esperar(base + '/', 600) + 0 * t0, 2)
            res['arranque_total_s'] = round(time.time() - t0, 2)
            time.sleep(5)
            res['cg_reposo_MiB'] = round(int(leer(f'{MEM}/memory.usage_in_bytes')) / 2**20)
            res['rss_reposo_MiB'] = round((stat().get('total_rss', 0) + stat().get('total_shmem', 0)) / 2**20)
            # 1.ª visita al backend tras borrar bundles = lo que pasa tras un deploy
            if rep == 1:
                q = ['psql', '-h', 'localhost', '-p', '5441', '-U', 'odoo', '-d', 'r3_med_base', '-Atqc',
                     "delete from ir_attachment where url like '/web/assets/%'"]
                subprocess.run(q, env=dict(os.environ, PGPASSWORD='odoo'), check=True)
            t = time.time()
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                medir.calentar(base)
            res['calentar_s'] = round(time.time() - t, 1)
            res['bundles_regenerados'] = rep == 1
            res['lat_secuencial'] = medir.lat_secuencial(base, pid, 10)
            for conc, n in ((20, 400), (50, 600)):
                c = medir.carga(base, pid, conc, n)
                res[f'carga_{conc}'] = {k: c[k] for k in ('ok', 'errores', 'rps', 'cpu_ms_por_peticion', 'lat_ms')}
            time.sleep(3)
            res['cg_tras_carga_MiB'] = round(int(leer(f'{MEM}/memory.usage_in_bytes')) / 2**20)
        except Exception as e:  # noqa: BLE001 - se registra (p. ej. OOM a mitad)
            res['excepcion'] = repr(e)[:300]
        finally:
            pico.alto.set()
            pico.join()
            res['pico_cgroup_con_cache_MiB'] = round(int(leer(f'{MEM}/memory.max_usage_in_bytes')) / 2**20)
            res['pico_rss_anon_MiB'] = round(pico.rss / 2**20)
            res['failcnt'] = int(leer(f'{MEM}/memory.failcnt'))
            res['oom_kills'] = oom_kills() - oom0
            res['odoo_vivo'] = os.path.exists(f'/proc/{pid}')
            campana.matar(pid)
            time.sleep(2)
        with open(f'{AQUI}/res_contenedor_sim.jsonl', 'a') as f:
            f.write(json.dumps(res) + '\n')
        print(json.dumps({k: v for k, v in res.items() if k not in ('lat_secuencial',)})[:1500])
    subprocess.run([f'{AQUI}/pg_propio.sh', 'stop'], capture_output=True)
