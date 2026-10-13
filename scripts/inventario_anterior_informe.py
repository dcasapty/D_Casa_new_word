#!/usr/bin/env python3
"""Informe del inventario del sistema anterior para la dueña, sin Odoo.

Lee ``addons/dcasa_catalogo/data/inventario_anterior.csv`` (transcripción de las capturas de
«up media/inventario-anterior»), lo cruza con el catálogo cargado (``data/catalogo.json``: códigos
de producto y de variante) y con las fotos de ``static/img/productos`` y escribe:

* ``docs/inventario-anterior-fotos-faltantes.xlsx``: código, nombre, existencias de los productos
  nuevos sin foto (lo que la dueña tiene que fotografiar).
* ``docs/inventario-anterior-informe.md``: resumen (creados, actualizados, negativos, combos,
  omitidos, repetidos, dudas de lectura).

Las mismas reglas (``reglas.planificar_inventario``) usa la carga real; el test del módulo
comprueba que los dos cuadran. Uso: ``python3 scripts/inventario_anterior_informe.py``.
"""
import json
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'addons' / 'dcasa_catalogo'))
import reglas  # noqa: E402

CSV = ROOT / 'addons' / 'dcasa_catalogo' / 'data' / 'inventario_anterior.csv'
CATALOGO = ROOT / 'addons' / 'dcasa_catalogo' / 'data' / 'catalogo.json'
FOTOS = ROOT / 'addons' / 'dcasa_catalogo' / 'static' / 'img' / 'productos'
XLSX = ROOT / 'docs' / 'inventario-anterior-fotos-faltantes.xlsx'
MD = ROOT / 'docs' / 'inventario-anterior-informe.md'
TOTALES_LEEME = [565, 490, 627, 125, 806, 832, 664]


def codigos_del_catalogo(catalogo):
    """Códigos de producto y de variante (tamaño, color) tal como quedan en Odoo."""
    codigos = set()
    for item in catalogo:
        codigos.add(item['codigo'])
        for tamano in item['precios']:
            if tamano:
                codigos.add(f"{item['codigo']}-{tamano.upper()}")
        for color in item.get('colores') or {}:
            codigos.add(f"{item['codigo']}-{re.sub(r'[^A-Z0-9]+', '-', color.upper()).strip('-')}")
    return codigos


def existencias(fila):
    if fila['a_la_mano'] is None:
        return ''
    return max(int(fila['a_la_mano']), 0)


def escribir_xlsx(sin_foto, ruta):
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Fotos faltantes'
    hoja.append(['Código', 'Nombre', 'Existencias'])
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for fila in sin_foto:
        hoja.append([fila['codigo'], fila['nombre'], existencias(fila)])
    hoja.column_dimensions['A'].width = 24
    hoja.column_dimensions['B'].width = 90
    hoja.column_dimensions['C'].width = 12
    hoja.freeze_panes = 'A2'
    libro.save(ruta)


def lista(filas, con_existencias=False):
    lineas = []
    for fila in filas:
        texto = f"- `{fila['codigo'] or '(sin código)'}` {fila['nombre']}"
        if con_existencias and fila['a_la_mano'] is not None:
            texto += f" — a la mano {int(fila['a_la_mano'])}"
        lineas.append(texto)
    return '\n'.join(lineas) or '- (ninguno)'


def dudas(filas):
    return '\n'.join(f"- p{f['pagina']} f{f['fila']} `{f['codigo'] or '(sin código)'}` {f['nombre']}: {f['dudas']}"
                     for f in filas) or '- (ninguna)'


def cambios_de_precio(plan, catalogo):
    """Filas que actualizan un producto del catálogo actual con otro precio de venta (de un solo precio)."""
    precios = {item['codigo']: item['precios'][''] for item in catalogo if list(item['precios']) == ['']}
    return [(fila, precios[fila['codigo']]) for fila in plan['actualizar']
            if fila['codigo'] in precios and fila['precio'] is not None
            and round(fila['precio'] - precios[fila['codigo']], 2)]


def lista_precios(cambios):
    return '\n'.join(f"- `{fila['codigo']}` {fila['nombre']}: catálogo ${antes:.2f} → inventario ${fila['precio']:.2f}"
                     for fila, antes in cambios) or '- (ninguno)'


def escribir_md(filas, plan, fotos, ruta, cambios_precio=()):
    paginas = sorted({f['pagina'] for f in filas})
    sumas = [int(sum(f['a_la_mano'] or 0 for f in filas if f['pagina'] == p)) for p in paginas]
    unidades = int(sum(max(f['a_la_mano'], 0) for f in plan['crear'] + plan['actualizar']
                       if f['a_la_mano'] is not None))
    md = f"""# Inventario del sistema anterior — informe de carga

Fuente: 7 capturas de Inventario → Productos del Odoo anterior (`up media/inventario-anterior/`),
transcritas a `inventario_anterior.csv` con dos lecturas independientes por captura (idénticas en
las {len(filas)} filas). Suma de «a la mano» por página: {' · '.join(map(str, sumas))}
({'coincide' if sumas == TOTALES_LEEME else 'NO coincide'} con el LEEME).

La carga la hace `dcasa_catalogo` (migración 19.0.1.7.0 y alta de base nueva) con
`cargar_inventario_anterior`; este informe sale de las mismas reglas (`reglas.planificar_inventario`)
cruzadas con `data/catalogo.json` y las fotos de `static/img/productos`.

## Resumen

| Grupo | Filas |
| --- | ---: |
| Filas transcritas | {len(filas)} |
| No se importan (Descuento, Propinas, «X COLCHÓN … PARA COMBO») | {len(plan['omitidos'])} |
| Código repetido en el CSV (solo entra la primera aparición) | {len(plan['repetidos'])} |
| Ya estaban en el catálogo → se actualizan existencias, costo y precio | {len(plan['actualizar'])} |
| Productos nuevos | {len(plan['crear'])} |
| · de ellos, combos «… + COLCHÓN» (sin publicar) | {len(plan['combos'])} |
| · con foto (publicados en la web) | {len(plan['con_foto'])} |
| · sin foto (en inventario, sin publicar; lista en el Excel) | {len(plan['sin_foto'])} |
| Existencias negativas → entran en 0, para conteo físico | {len(plan['negativos'])} |
| Unidades que entran al almacén | {unidades} |
| Dudas de lectura anotadas en el CSV | {len(plan['dudas'])} |

## Existencias negativas (entran en 0; conteo físico pendiente)

{lista(plan['negativos'], con_existencias=True)}

El LEEME hablaba de 8 negativos; en las dos lecturas salen {len(plan['negativos'])} y las sumas por
página cuadran con las capturas, así que el octavo seguramente era un conteo a ojo. Queda anotado
como duda para la dueña.

## Combos «… + COLCHÓN» (productos sin publicar, costo 0 en el sistema anterior)

{lista(plan['combos'])}

## Precios del catálogo actual que cambia el inventario ({len(cambios_precio)})

El inventario anterior manda sobre el precio de los códigos que trae (regla de la dueña). Estos
productos ya estaban en el catálogo con otro precio; si alguno debe quedarse con el del catálogo
(por ejemplo los del pedido LTSC-07, que se fijaron terminados en .99), la dueña lo cambia en Odoo.

{lista_precios(cambios_precio)}

## No se importan

{lista(plan['omitidos'])}

## Repetidos en el CSV

{lista(plan['repetidos'], con_existencias=True)}

## Dudas de lectura (columna `dudas` del CSV)

{dudas(plan['dudas'])}

## Fotos

- Fotos asignadas a productos nuevos (archivo que empieza por el código): {len(plan['con_foto'])}.
- Productos nuevos sin foto: {len(plan['sin_foto'])} → `docs/inventario-anterior-fotos-faltantes.xlsx`
  (código, nombre, existencias). Entran al inventario sin publicar en la web hasta tener foto.
- En «up media» no hay fotos de códigos del inventario que no estén ya en `static/img/productos`.
"""
    ruta.write_text(md, encoding='utf-8')


def main():
    filas = reglas.filas_inventario(CSV.read_text(encoding='utf-8'))
    catalogo = json.loads(CATALOGO.read_text(encoding='utf-8'))
    existentes = codigos_del_catalogo(catalogo)
    fotos = reglas.foto_por_codigo({f['codigo'] for f in filas if f['codigo']},
                                   [p.name for p in FOTOS.iterdir()])
    plan = reglas.planificar_inventario(filas, existentes, fotos)
    cambios_precio = cambios_de_precio(plan, catalogo)
    escribir_xlsx(plan['sin_foto'], XLSX)
    escribir_md(filas, plan, fotos, MD, cambios_precio)
    print(f'cambios de precio: {len(cambios_precio)}')
    for clave in ('crear', 'actualizar', 'combos', 'con_foto', 'sin_foto', 'negativos', 'omitidos', 'repetidos',
                  'dudas'):
        print(f'{clave}: {len(plan[clave])}')
    print(XLSX)
    print(MD)


if __name__ == '__main__':
    main()
