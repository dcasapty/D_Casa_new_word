"""Memoria real del contenedor: cgroup (anónima vs caché de archivos) y RSS/PSS por proceso.

La métrica de memoria del panel de Cloudflare Containers puede incluir la caché de páginas
(«file»), que el kernel libera cuando hace falta: 0,8-1 GiB en el panel no es lo mismo que
0,8-1 GiB de Odoo + PostgreSQL. Esto separa:

* ``cgroup``: ``memory.current``/``memory.max`` y, de ``memory.stat``, ``anon`` (lo que de
  verdad usan los procesos), ``file`` (caché, recuperable), ``kernel`` y ``shmem``
  (``shared_buffers`` de PostgreSQL); ``eventos`` = ``memory.events`` (``oom``,
  ``oom_kill``: si suben, hubo un OOM). Cgroup v2, con respaldo para v1.
* ``procesos``: suma de RSS y PSS (``smaps_rollup``) de Odoo, de PostgreSQL y del resto.
  La RSS de PostgreSQL cuenta ``shared_buffers`` una vez por proceso: la PSS es la buena.

Solo biblioteca estándar: lo usa el reporte mensual de ``dcasa.mantenimiento`` y el
arranque del contenedor (``docker/entrypoint.sh``) como script suelto:

    python3 memoria.py arranque   →   {"evento": "memoria", "momento": "arranque", ...}
"""
import json
import os
import sys

CGROUP = '/sys/fs/cgroup'
PROC = '/proc'


def _leer(ruta):
    try:
        with open(ruta, 'rb') as archivo:
            return archivo.read().decode(errors='replace')
    except OSError:
        return None


def _numero(texto):
    if texto is None:
        return None
    texto = texto.strip()
    if not texto or texto == 'max':
        return None  # sin límite
    try:
        return int(texto)
    except ValueError:
        return None


def _pares(texto):
    """«clave valor [unidad]» por línea → dict de enteros."""
    datos = {}
    for linea in (texto or '').splitlines():
        partes = linea.split()
        if len(partes) >= 2 and partes[1].lstrip('-').isdigit():
            datos[partes[0]] = int(partes[1])
    return datos


def cgroup(base=CGROUP):
    if os.path.exists(os.path.join(base, 'memory.current')):  # cgroup v2
        stat = _pares(_leer(os.path.join(base, 'memory.stat')))
        kernel = stat.get('kernel')
        if kernel is None and stat:  # kernels < 5.18 no traen «kernel»
            kernel = sum(stat.get(k, 0) for k in ('kernel_stack', 'pagetables', 'percpu', 'sock', 'slab'))
        eventos = _pares(_leer(os.path.join(base, 'memory.events')))
        return {
            'version': 2,
            'current': _numero(_leer(os.path.join(base, 'memory.current'))),
            'max': _numero(_leer(os.path.join(base, 'memory.max'))),
            'anon': stat.get('anon'),
            'file': stat.get('file'),
            'kernel': kernel,
            'shmem': stat.get('shmem'),
            'eventos': {k: eventos.get(k) for k in ('oom', 'oom_kill', 'max', 'high')},
        }
    v1 = os.path.join(base, 'memory')
    if os.path.exists(os.path.join(v1, 'memory.usage_in_bytes')):  # cgroup v1
        stat = _pares(_leer(os.path.join(v1, 'memory.stat')))
        oom = _pares(_leer(os.path.join(v1, 'memory.oom_control')))
        limite = _numero(_leer(os.path.join(v1, 'memory.limit_in_bytes')))
        return {
            'version': 1,
            'current': _numero(_leer(os.path.join(v1, 'memory.usage_in_bytes'))),
            # v1 sin límite da un número enorme (PAGE_COUNTER_MAX): se trata como «sin límite».
            'max': limite if limite and limite < 2 ** 60 else None,
            'anon': stat.get('total_rss', stat.get('rss')),
            'file': stat.get('total_cache', stat.get('cache')),
            'kernel': _numero(_leer(os.path.join(v1, 'memory.kmem.usage_in_bytes'))),
            'shmem': stat.get('total_shmem', stat.get('shmem')),
            'eventos': {'oom_kill': oom.get('oom_kill'), 'failcnt': _numero(_leer(os.path.join(v1, 'memory.failcnt')))},
        }
    return {'version': None}


def _grupo(pid, proc=PROC):
    comm = (_leer(os.path.join(proc, pid, 'comm')) or '').strip()
    if comm == 'postgres':
        return 'postgres'
    cmdline = _leer(os.path.join(proc, pid, 'cmdline')) or ''
    if 'odoo-bin' in cmdline:
        return 'odoo'
    return 'otros'


def procesos(proc=PROC):
    """{'odoo'|'postgres'|'otros': {'n', 'rss', 'pss'}} en bytes (PSS si es legible)."""
    totales = {g: {'n': 0, 'rss': 0, 'pss': 0} for g in ('odoo', 'postgres', 'otros')}
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return totales
    for pid in pids:
        rss = _pares((_leer(os.path.join(proc, pid, 'status')) or '').replace(':', ' ')).get('VmRSS')
        if not rss:
            continue  # hilos del kernel o proceso ya terminado
        grupo = totales[_grupo(pid, proc)]
        grupo['n'] += 1
        grupo['rss'] += rss * 1024
        pss = _pares((_leer(os.path.join(proc, pid, 'smaps_rollup')) or '').replace(':', ' ')).get('Pss')
        grupo['pss'] += (pss or 0) * 1024
    return totales


def medir():
    return {'cgroup': cgroup(), 'procesos': procesos()}


def linea(momento):
    """Una línea JSON para el log del contenedor (un solo evento de Workers Logs)."""
    return json.dumps({'evento': 'memoria', 'momento': momento, **medir()}, sort_keys=True)


if __name__ == '__main__':
    print(linea(sys.argv[1] if len(sys.argv) > 1 else 'manual'), flush=True)
