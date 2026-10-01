#!/usr/bin/env python3
"""Mide el tamaño del catálogo de herramientas de Brian SIN arrancar Odoo (análisis estático con ast).

Reconstruye el mismo esquema que `registro.py:esquema()` (name, description + ejemplos, input_schema) y
lo mide en caracteres; los tokens son ESTIMACIONES (caracteres / factor). Sirve también como prueba de
regresión en CI: `--max-chars N` falla si el catálogo crece más de lo acordado.

    python3 medir_herramientas.py [--json] [--max-chars 26500]
"""
import argparse
import ast
import json
import sys
import types
from collections import defaultdict
from pathlib import Path

MODELOS = Path(__file__).resolve().parents[4] / 'addons' / 'dcasa_brian' / 'models'
FACTORES = {'repo (caracteres/4)': 4.0, 'español+JSON (3.3)': 3.3, 'tokenizador nuevo, +30% (2.5)': 2.5}


def ns_de(arbol, base=None):
    ns = dict(base or {})
    for n in arbol.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            try:
                ns[n.targets[0].id] = eval(ast.unparse(n.value), ns)
            except Exception:  # noqa: BLE001 — constante que depende de Odoo: se ignora
                pass
    return ns


def cargar():
    comun = ns_de(ast.parse((MODELOS / 'herramientas_comun.py').read_text(encoding='utf-8')))
    cm = types.SimpleNamespace(**{k: v for k, v in comun.items() if k.isidentifier()})
    reg = ns_de(ast.parse((MODELOS / 'registro.py').read_text(encoding='utf-8')))
    herramientas = []
    for f in sorted(MODELOS.glob('herramientas_*.py')):
        arbol = ast.parse(f.read_text(encoding='utf-8'))
        ns = ns_de(arbol, {'c': cm, 'CATEGORIAS': reg.get('CATEGORIAS', {})})
        for n in ast.walk(arbol):
            if not isinstance(n, ast.FunctionDef):
                continue
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, 'id', '') == 'herramienta':
                    kw = {k.arg: eval(ast.unparse(k.value), ns) for k in d.keywords}
                    kw['_ruta'] = f'{f.name}:{n.lineno}'
                    herramientas.append(kw)
    return herramientas


def esquema(h):
    desc = h['descripcion'] + (' Ejemplos: ' + '; '.join(h['ejemplos']) if h.get('ejemplos') else '')
    return {'name': h['nombre'], 'description': desc,
            'input_schema': {'type': 'object', 'properties': h.get('parametros', {}),
                             'required': list(h.get('requeridos', [])), 'additionalProperties': False}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--max-chars', type=int)
    a = ap.parse_args()
    hs = cargar()
    tam = {h['nombre']: len(json.dumps(esquema(h), ensure_ascii=False)) for h in hs}
    total = sum(tam.values())
    por_cat, por_grupo = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for h in hs:
        c = por_cat[h.get('categoria', 'general')]
        c[0] += 1
        c[1] += tam[h['nombre']]
        g = por_grupo[','.join(h.get('grupos', ())) or '(sin grupo: todos)']
        g[0] += 1
        g[1] += tam[h['nombre']]
    # vista por rol (aproximada: no resuelve grupos implicados de Odoo)
    roles = {'administrador': lambda g: True,
             'vendedor': lambda g: set(g) <= {'base.group_user', 'sales_team.group_sale_salesman'},
             'cajero/contador': lambda g: set(g) <= {'base.group_user', 'account.group_account_invoice'}}
    por_rol = {r: sum(tam[h['nombre']] for h in hs if f(h.get('grupos', ()))) for r, f in roles.items()}
    top = sorted(tam.items(), key=lambda kv: -kv[1])[:8]
    sal = {'herramientas': len(hs), 'chars_total': total, 'chars_medio': round(total / len(hs)),
           'tokens_estimados': {k: round(total / v) for k, v in FACTORES.items()},
           'por_categoria': dict(por_cat), 'por_grupo': dict(por_grupo), 'chars_por_rol': por_rol,
           'mas_pesadas': top,
           'sin_ejemplos': [h['nombre'] for h in hs if not h.get('ejemplos')],
           'parametros_medios': round(sum(len(h.get('parametros', {})) for h in hs) / len(hs), 2)}
    if a.json:
        print(json.dumps(sal, ensure_ascii=False, indent=1))
    else:
        for k, v in sal.items():
            print(f'{k}: {v}')
    if a.max_chars and total > a.max_chars:
        print(f'FALLA: el catálogo mide {total} caracteres (> {a.max_chars})', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
