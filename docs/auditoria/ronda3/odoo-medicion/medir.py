#!/usr/bin/env python3
"""Herramientas de medición de Odoo + PostgreSQL (ronda 3, r3-odoo-medicion).

Subcomandos:
  mem <pid>                    RSS/PSS (kB) del árbol de procesos de <pid> (smaps_rollup)
  pgmem <datadir>              RSS/PSS del clúster cuyo postmaster.pid está en <datadir>
  esperar <url> [timeout]      segundos hasta el primer 200 en <url>
  calentar <base_url>          visita las páginas públicas y el backend con sesión admin
  carga <base_url> <pid> <conc> <n> [--pg DATADIR] [--rutas a,b,c]
                               N peticiones con C concurrentes, latencias p50/p95 por ruta,
                               CPU (utime+stime) consumida por el árbol de Odoo y pico de memoria
  lat <base_url> <pid> <n>     latencia secuencial (conc=1) por ruta + CPU por petición

Sin dependencias fuera de httpx (ya instalado por Odoo).
"""
import asyncio
import json
import os
import statistics
import sys
import threading
import time

import httpx

CLK = os.sysconf('SC_CLK_TCK')
ADMIN_LOGIN = os.environ.get('ODOO_LOGIN', 'admin')
ADMIN_PASSWORD = os.environ.get('ODOO_PASSWORD', 'admin')
DB = os.environ.get('DB', 'r3_med_base')


# ---------- procesos ----------
def hijos(pid):
    """pid + todos sus descendientes."""
    ppid = {}
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                with open(f'/proc/{d}/stat') as f:
                    s = f.read()
                ppid[int(d)] = int(s[s.rfind(')') + 2:].split()[1])
            except OSError:
                pass
    out, pend = [], [int(pid)]
    while pend:
        p = pend.pop()
        out.append(p)
        pend.extend(c for c, pp in ppid.items() if pp == p)
    return out


def mem(pids):
    rss = pss = 0
    for p in pids:
        try:
            with open(f'/proc/{p}/smaps_rollup') as f:
                for line in f:
                    if line.startswith('Rss:'):
                        rss += int(line.split()[1])
                    elif line.startswith('Pss:'):
                        pss += int(line.split()[1])
        except OSError:
            pass
    return rss, pss


def cpu(pids):
    t = 0
    for p in pids:
        try:
            with open(f'/proc/{p}/stat') as f:
                s = f.read()
            campos = s[s.rfind(')') + 2:].split()
            t += int(campos[11]) + int(campos[12])  # utime, stime (+ cutime/cstime no: hijos vivos)
        except OSError:
            pass
    return t / CLK


def pg_pids(datadir):
    with open(os.path.join(datadir, 'postmaster.pid')) as f:
        return hijos(int(f.readline()))


class Muestreo(threading.Thread):
    """Muestrea memoria cada 0,2 s y guarda el pico."""

    def __init__(self, pid, datadir=None):
        super().__init__(daemon=True)
        self.pid, self.datadir = pid, datadir
        self.pico_odoo = self.pico_pg = self.pico_total = 0
        self.pico_odoo_pss = self.pico_pg_pss = self.pico_total_pss = 0
        self.alto = threading.Event()

    def run(self):
        while not self.alto.is_set():
            o_rss, o_pss = mem(hijos(self.pid))
            p_rss, p_pss = mem(pg_pids(self.datadir)) if self.datadir else (0, 0)
            self.pico_odoo = max(self.pico_odoo, o_rss)
            self.pico_odoo_pss = max(self.pico_odoo_pss, o_pss)
            self.pico_pg = max(self.pico_pg, p_rss)
            self.pico_pg_pss = max(self.pico_pg_pss, p_pss)
            self.pico_total = max(self.pico_total, o_rss + p_rss)
            self.pico_total_pss = max(self.pico_total_pss, o_pss + p_pss)
            time.sleep(0.2)


# ---------- HTTP ----------
def rutas_publicas(base):
    """/, /shop, una ficha real del catálogo, /visitanos, /web/login, /socios."""
    with httpx.Client(base_url=base, timeout=60, follow_redirects=True) as c:
        r = c.get('/shop')
        import re
        fichas = sorted(set(re.findall(r'href="(/shop/[a-z0-9-]+-\d+)"', r.text)))
    ficha = fichas[0] if fichas else '/shop'
    return {'/': '/', '/shop': '/shop', 'ficha': ficha, '/visitanos': '/visitanos',
            '/web/login': '/web/login', '/socios': '/socios'}


def sesion(client):
    r = client.post('/web/session/authenticate', json={
        'jsonrpc': '2.0', 'method': 'call',
        'params': {'db': DB, 'login': ADMIN_LOGIN, 'password': ADMIN_PASSWORD}})
    r.raise_for_status()
    res = r.json()
    if 'error' in res:
        raise RuntimeError(res['error'].get('data', {}).get('message'))
    return res['result']['uid']


def call_kw(model, method, args=None, kwargs=None):
    return {'jsonrpc': '2.0', 'method': 'call', 'params': {
        'model': model, 'method': method, 'args': args or [], 'kwargs': kwargs or {}}}


BACKEND = {
    'rpc productos': ('product.template', 'web_search_read', {
        'specification': {'name': {}, 'list_price': {}, 'default_code': {}, 'categ_id': {'fields': {'display_name': {}}},
                          'qty_available': {}}, 'limit': 80, 'domain': []}),
    'rpc facturas': ('account.move', 'web_search_read', {
        'specification': {'name': {}, 'partner_id': {'fields': {'display_name': {}}}, 'amount_total': {},
                          'state': {}, 'invoice_date': {}}, 'limit': 80,
        'domain': [['move_type', 'in', ['out_invoice', 'out_refund']]]}),
}


def calentar(base):
    rutas = rutas_publicas(base)
    with httpx.Client(base_url=base, timeout=120, follow_redirects=True) as c:
        for nombre, r in rutas.items():
            t = time.time()
            s = c.get(r).status_code
            print(f'{nombre:12s} {r:40s} {s} {time.time() - t:.2f}s')
    with httpx.Client(base_url=base, timeout=120, follow_redirects=True) as c:
        uid = sesion(c)
        print('sesion admin uid', uid)
        for p in ['/odoo', '/odoo/action-product.product_template_action', '/odoo/action-account.action_move_out_invoice_type']:
            t = time.time()
            print(f'{p:50s} {c.get(p).status_code} {time.time() - t:.2f}s')
        for nombre, (m, meth, kw) in BACKEND.items():
            t = time.time()
            r = c.post(f'/web/dataset/call_kw/{m}/{meth}', json=call_kw(m, meth, [], kw)).json()
            n = r.get('result', {}).get('length') if 'result' in r else r.get('error', {}).get('data', {}).get('message')
            print(f'{nombre:12s} {n} {time.time() - t:.2f}s')
        # assets del backend (los bundles los genera la primera visita)
        html = c.get('/odoo').text
        import re
        for a in sorted(set(re.findall(r'(/web/assets/[^"]+)', html))):
            t = time.time()
            r = c.get(a)
            print(f'asset {a[:60]:60s} {r.status_code} {len(r.content)}B {time.time() - t:.2f}s')
    return rutas


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float('nan')
    k = (len(xs) - 1) * p / 100
    f = int(k)
    return xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f)


async def _carga(base, conc, n, rutas, con_backend):
    lat = {k: [] for k in rutas}
    errores = {}
    cod = {}
    sem = asyncio.Semaphore(conc)
    tr = httpx.AsyncHTTPTransport(limits=httpx.Limits(max_connections=conc))
    async with httpx.AsyncClient(base_url=base, timeout=120, follow_redirects=True, transport=tr) as c:
        if con_backend:
            r = await c.post('/web/session/authenticate', json={'jsonrpc': '2.0', 'method': 'call', 'params': {
                'db': DB, 'login': ADMIN_LOGIN, 'password': ADMIN_PASSWORD}})
            r.raise_for_status()
        claves = list(rutas)

        async def una(i):
            k = claves[i % len(claves)]
            async with sem:
                t = time.perf_counter()
                if k.startswith('rpc'):
                    m, meth, kw = BACKEND[k]
                    r = await c.post(f'/web/dataset/call_kw/{m}/{meth}', json=call_kw(m, meth, [], kw))
                    ok = r.status_code == 200 and 'result' in r.json()
                else:
                    anon = httpx.AsyncClient(base_url=base, timeout=120, follow_redirects=True, transport=tr)
                    r = await anon.get(rutas[k])  # sin cookies: visitante anónimo
                    ok = r.status_code == 200
                dt = time.perf_counter() - t
            if ok:
                lat[k].append(dt)
            else:
                errores[k] = errores.get(k, 0) + 1
                cod[r.status_code] = cod.get(r.status_code, 0) + 1

        t0 = time.perf_counter()
        await asyncio.gather(*(una(i) for i in range(n)))
        total = time.perf_counter() - t0
    return lat, dict(errores, codigos=cod) if errores else errores, total


def carga(base, pid, conc, n, datadir=None, rutas=None, con_backend=True):
    rutas = rutas or rutas_publicas(base)
    if con_backend:
        rutas = dict(rutas)
        rutas.update({k: None for k in BACKEND})
    m = Muestreo(pid, datadir)
    m.start()
    c0 = cpu(hijos(pid))
    lat, errores, total = asyncio.run(_carga(base, conc, n, rutas, con_backend))
    c1 = cpu(hijos(pid))
    m.alto.set()
    m.join()
    ok = sum(len(v) for v in lat.values())
    res = {
        'conc': conc, 'n': n, 'ok': ok, 'errores': errores, 'segundos': round(total, 2),
        'rps': round(ok / total, 2), 'cpu_s': round(c1 - c0, 2),
        'cpu_ms_por_peticion': round((c1 - c0) * 1000 / max(ok, 1), 1),
        'pico_rss_odoo_MiB': round(m.pico_odoo / 1024), 'pico_pss_odoo_MiB': round(m.pico_odoo_pss / 1024),
        'pico_rss_pg_MiB': round(m.pico_pg / 1024), 'pico_pss_pg_MiB': round(m.pico_pg_pss / 1024),
        'pico_pss_total_MiB': round(m.pico_total_pss / 1024),
        'lat_ms': {k: {'n': len(v), 'p50': round(pct(v, 50) * 1000), 'p95': round(pct(v, 95) * 1000)}
                   for k, v in lat.items()},
    }
    return res


def lat_secuencial(base, pid, n):
    """Latencia con base caliente y una petición a la vez; CPU por petición y por ruta."""
    rutas = rutas_publicas(base)
    out = {}
    with httpx.Client(base_url=base, timeout=120, follow_redirects=True) as c, \
            httpx.Client(base_url=base, timeout=120, follow_redirects=True) as anon:
        sesion(c)
        for k in list(rutas) + list(BACKEND):
            ts = []
            c0 = cpu(hijos(pid))
            for _ in range(n):
                t = time.perf_counter()
                if k in BACKEND:
                    m, meth, kw = BACKEND[k]
                    r = c.post(f'/web/dataset/call_kw/{m}/{meth}', json=call_kw(m, meth, [], kw))
                else:
                    anon.cookies.clear()  # visitante anónimo nuevo en cada petición
                    r = anon.get(rutas[k])
                assert r.status_code == 200, (k, r.status_code)
                ts.append(time.perf_counter() - t)
            c1 = cpu(hijos(pid))
            out[k] = {'n': n, 'p50_ms': round(pct(ts, 50) * 1000), 'p95_ms': round(pct(ts, 95) * 1000),
                      'cpu_ms': round((c1 - c0) * 1000 / n, 1)}
    return out


def esperar(url, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.get(url, timeout=120, follow_redirects=True).status_code == 200:
                return time.time() - t0
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError(url)


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    if cmd == 'mem':
        rss, pss = mem(hijos(int(a[0])))
        print(json.dumps({'rss_MiB': round(rss / 1024, 1), 'pss_MiB': round(pss / 1024, 1),
                          'procesos': len(hijos(int(a[0])))}))
    elif cmd == 'pgmem':
        ps = pg_pids(a[0])
        rss, pss = mem(ps)
        print(json.dumps({'rss_MiB': round(rss / 1024, 1), 'pss_MiB': round(pss / 1024, 1), 'procesos': len(ps)}))
    elif cmd == 'esperar':
        print(f'{esperar(a[0], float(a[1]) if len(a) > 1 else 600):.2f}')
    elif cmd == 'calentar':
        calentar(a[0])
    elif cmd == 'carga':
        datadir = a[a.index('--pg') + 1] if '--pg' in a else None
        sin_backend = '--sin-backend' in a
        print(json.dumps(carga(a[0], int(a[1]), int(a[2]), int(a[3]), datadir, con_backend=not sin_backend)))
    elif cmd == 'lat':
        print(json.dumps(lat_secuencial(a[0], int(a[1]), int(a[2]))))
