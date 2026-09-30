"""Prepara el catálogo real de D'CASA para Odoo: python scripts/importar_catalogo.py

Lee «up media/DCASA_listado_productos.xlsx» y las fotos de «up media/» (el nombre de cada
foto es el código del producto, con _1, _2… cuando hay varias) y genera:

  · addons/dcasa_catalogo/data/catalogo.json      un producto por código
  · addons/dcasa_catalogo/static/img/productos/  las fotos optimizadas para la web (JPEG)
  · docs/CATALOGO_REVISAR.md                      lo que el Excel deja en duda

Reglas (no se inventa nada):
  · Precio: el del Excel, tal cual, con ITBMS incluido. En Odoo esos productos llevan el
    impuesto «ITBMS 7 % incluido», así la web, la cotización y la factura dan exactamente
    el precio de la ficha (sin centavos de diferencia por redondeo).
  · Códigos repetidos: un solo producto; manda la primera fila del Excel. Si las fichas
    tienen precios distintos, queda anotado para revisar.
  · «Precios por tamaño» → variantes (Twin/Full/Queen/King). Un tamaño sin precio no se crea.
  · Combo con colchón y «el par»: van como texto en la ficha, con el precio del Excel.
  · Sin foto: el producto entra al inventario pero no se publica en la web.

Se corre cada vez que cambie el Excel o las fotos; después, actualizar el módulo.
"""
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

import openpyxl
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / 'up media'
EXCEL = ORIGEN / 'DCASA_listado_productos.xlsx'
MODULO = RAIZ / 'addons' / 'dcasa_catalogo'
DESTINO_IMG = MODULO / 'static' / 'img' / 'productos'
DESTINO_JSON = MODULO / 'data' / 'catalogo.json'
REPORTE = RAIZ / 'docs' / 'CATALOGO_REVISAR.md'
# Fichas revisadas foto por foto (descriptor visible, medidas impresas en la foto, portada,
# fotos con problemas). Se editan a mano; el importador solo las aplica.
FICHAS = MODULO / 'data' / 'fichas.json'

LADO_MAXIMO = 1600   # px del lado largo: nítido en pantalla y liviano (Odoo guarda hasta 1920)
CALIDAD = 82
TAMANOS = ['Twin', 'Full', 'Queen', 'King']
# Fotos que no sirven de portada (borrosas o casi en blanco): van al final de la galería.
FOTOS_AL_FINAL = {'clb0119018_1.png'}

# Categoría de la tienda según el nombre del producto (primera regla que coincide).
CATEGORIAS = [
    (r'colch', 'colchones'),
    (r'mueble de tv', 'muebles_tv'),
    (r'sof[aá]', 'salas'),
    (r'zapatera', 'zapateras'),
    (r'escritorio|mesa ajustable', 'oficina'),
    (r'estante|librero|organizador|mueble de cocina|mueble type', 'organizacion'),
    (r'cama|camarote|mesa de noche|peinadora|tocador|gavetero', 'recamaras'),
]


def codigo_archivo(codigo):
    """Las fotos no pueden tener «/» en el nombre: 1062010734/5/6N → 1062010734-5-6N."""
    return codigo.replace('/', '-')


def precio(texto):
    m = re.search(r'\$\s*([\d,]+\.\d{2})', texto or '')
    return float(m.group(1).replace(',', '')) if m else None


def por_tamano(texto):
    """'Twin $39.99 · Full $59.99 · Queen $— …' → {'Twin': 39.99, 'Full': 59.99} (sin los vacíos)."""
    salida = OrderedDict()
    for parte in (texto or '').split('·'):
        m = re.match(r'\s*(Twin|Full|Queen|King)\s*(.*)', parte.strip())
        if m and (valor := precio(m.group(2))):
            salida[m.group(1)] = valor
    return salida


def texto_precios(precios):
    return ' · '.join(f'{k} ${v:.2f}'.strip() for k, v in precios.items())


def categoria(nombre):
    for patron, clave in CATEGORIAS:
        if re.search(patron, nombre, re.I):
            return clave
    return 'organizacion'


def fotos_de(codigo, archivos):
    """Fotos de un código, en orden: CODIGO.png o CODIGO_1.png primero."""
    base = codigo_archivo(codigo).upper()
    propias = []
    for f in archivos:
        stem = Path(f).stem
        m = re.match(r'(.+?)(?:_(\d+))?$', stem)
        if m.group(1).upper() == base:
            propias.append((int(m.group(2) or 0), f))
    return [f for _n, f in sorted(propias, key=lambda nf: (nf[1] in FOTOS_AL_FINAL, nf[0]))]


def ordenar_fotos(fotos, ficha):
    """La portada elegida primero; las fotos con texto del proveedor o de otro producto, al final."""
    problema = set(ficha.get('fotos_problema') or [])
    portada = ficha.get('portada')
    return sorted(fotos, key=lambda f: (f in problema, f != portada))


def nombre_web(nombre, precios, ficha):
    """«Mesa de noche» + «blanca con 2 gavetas». Con tamaños, el tamaño va en la variante."""
    if len(precios) > 1:
        nombre = re.sub(r'\s*\b(twin|full|queen|king)\b', '', nombre, flags=re.I).strip()
    descriptor = (ficha.get('descriptor') or '').strip()
    return f'{nombre} {descriptor}'.strip() if descriptor else nombre


def ancho(medidas):
    m = re.search(r'Alto:\s*([\d.,]+)', medidas or '')
    return f'{m.group(1)} cm de ancho' if m else None


def desempatar(catalogo):
    """Dos productos que se ven iguales no pueden llamarse igual: se les suma el ancho o la referencia."""
    grupos = {}
    for item in catalogo:
        grupos.setdefault(item['nombre_web'].lower(), []).append(item)
    for items in grupos.values():
        if len(items) < 2:
            continue
        anchos = [ancho(i['medidas']) for i in items]
        distintos = None not in anchos and len(set(anchos)) == len(anchos)
        for item, a in zip(items, anchos, strict=True):
            item['nombre_web'] += f', {a}' if distintos else f' (ref. {item["codigo"]})'


def optimizar(archivo):
    destino = DESTINO_IMG / (Path(archivo).stem + '.jpg')
    if not destino.exists():
        with Image.open(ORIGEN / archivo) as original:
            foto = original.convert('RGB')
        foto.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
        foto.save(destino, 'JPEG', quality=CALIDAD, optimize=True, progressive=True)
    return destino.name


def main():
    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    filas = list(wb['Productos'].iter_rows(min_row=2, values_only=True))
    archivos = sorted(f.name for f in ORIGEN.iterdir() if f.suffix.lower() in ('.png', '.jpg', '.jpeg'))
    DESTINO_IMG.mkdir(parents=True, exist_ok=True)

    productos = OrderedDict()
    revisar = []
    for celda_codigo, nombre, unico, tamanos, combo, _stock, obs in filas:
        if not celda_codigo:
            continue
        codigo = str(celda_codigo).strip()
        precios = por_tamano(tamanos) if tamanos else OrderedDict()
        if not precios and unico:
            precios = OrderedDict([('', float(unico))])
        if codigo in productos:
            actual = productos[codigo]
            if any(actual['precios_ficha'].get(k) not in (None, v) for k, v in precios.items()):
                revisar.append(f'`{codigo}` ({nombre}): el Excel trae dos precios, '
                               f'{texto_precios(actual["precios_ficha"])} y {texto_precios(precios)}. '
                               'Se usó el primero.')
            if combo and not actual['combo']:
                actual['combo'] = combo
            continue
        if obs and 'revisar' in obs.lower():
            revisar.append(f'`{codigo}` ({nombre}): {obs}.')
        if tamanos and ('$—' in tamanos or '$00' in (obs or '')):
            revisar.append(f'`{codigo}` ({nombre}): un tamaño viene sin precio y no se creó.')
        productos[codigo] = {
            'codigo': codigo,
            'nombre': nombre.strip(),
            'categoria': categoria(nombre),
            'precios_ficha': precios,
            'combo': combo,
        }

    fichas = json.loads(FICHAS.read_text(encoding='utf-8')) if FICHAS.exists() else {}
    catalogo = []
    sin_foto = []
    for orden, p in enumerate(productos.values(), start=1):
        if not p['precios_ficha']:
            revisar.append(f'`{p["codigo"]}` ({p["nombre"]}): sin precio en el Excel; no se importó.')
            continue
        ficha = fichas.get(p['codigo'], {})
        fotos = ordenar_fotos([optimizar(f) for f in fotos_de(p['codigo'], archivos)], ficha)
        if not fotos:
            sin_foto.append(f'`{p["codigo"]}` ({p["nombre"]})')
        catalogo.append({
            'codigo': p['codigo'],
            'nombre': p['nombre'],
            'nombre_web': nombre_web(p['nombre'], p['precios_ficha'], ficha),
            'medidas': ficha.get('medidas'),
            'categoria': p['categoria'],
            'orden': orden,
            'precios': p['precios_ficha'],
            'combo': p['combo'],
            'fotos': fotos,
        })

    desempatar(catalogo)
    otro_tipo = [f'`{c}` ({f["tipo_real"]})' for c, f in fichas.items() if f.get('tipo_real')]
    DESTINO_JSON.parent.mkdir(parents=True, exist_ok=True)
    DESTINO_JSON.write_text(json.dumps(catalogo, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    lineas = [
        '# Catálogo: lo que hay que revisar',
        '',
        'Generado por `scripts/importar_catalogo.py` a partir de `up media/DCASA_listado_productos.xlsx`.',
        'Nada de esto se adivinó: donde el Excel duda, se tomó la primera ficha y se anota aquí.',
        '',
        f'- Productos importados: **{len(catalogo)}** '
        f'({sum(1 for c in catalogo if len(c["precios"]) > 1)} con tamaños como variantes).',
        f'- Fotos optimizadas: **{sum(len(c["fotos"]) for c in catalogo)}**.',
        '- Existencias: el Excel dice «Sin confirmar» en todos; el inventario arranca en 0 y la web '
        'deja comprar igual (se confirma por WhatsApp).',
        '',
        '## Precios y fichas en duda',
        '',
        *[f'- {r}' for r in revisar],
        '',
        '## Sin foto (en inventario, no publicados en la web)',
        '',
        *[f'- {s}' for s in sin_foto],
        '',
        '## Las fotos muestran otro tipo de mueble que el nombre del Excel',
        '',
        *[f'- {t}' for t in otro_tipo],
        '',
        f'Nombres web y medidas: `{FICHAS.relative_to(RAIZ)}` (revisadas foto por foto; las medidas solo '
        'cuando están impresas en la foto).',
        '',
    ]
    REPORTE.write_text('\n'.join(lineas), encoding='utf-8')
    print(f'{len(catalogo)} productos, {sum(len(c["fotos"]) for c in catalogo)} fotos, '
          f'{len(revisar)} para revisar, {len(sin_foto)} sin foto.')


if __name__ == '__main__':
    sys.exit(main())
