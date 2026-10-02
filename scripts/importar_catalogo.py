"""Prepara el catálogo real de D'CASA para Odoo: python scripts/importar_catalogo.py

Lee «up media/DCASA_listado_productos.xlsx» y las fotos de «up media/» (el nombre de cada
foto es el código del producto, con _1, _2… cuando hay varias) y genera:

  · addons/dcasa_catalogo/data/catalogo.json      un producto por código
  · addons/dcasa_catalogo/static/img/productos/  las fotos optimizadas para la web (JPEG)
  · docs/CATALOGO_REVISAR.md                      lo que el Excel deja en duda

Reglas (no se inventa nada):
  · Precio: el del Excel, tal cual, SIN ITBMS («+ITBMS»). En Odoo esos productos llevan el
    impuesto «ITBMS 7%», que se suma al precio: la web muestra «$39.99 + ITBMS» y la
    cotización y la factura suman el 7 % (factura INV/2026/00821: 329.99 + 23.10 = 353.09).
  · Códigos repetidos: un solo producto; manda la primera fila del Excel. Si las fichas
    tienen precios distintos, queda anotado para revisar.
  · «Precios por tamaño» → variantes (Twin/Full/Queen/King). Un tamaño sin precio no se crea.
  · Combo con colchón y «el par»: van como texto en la ficha, con el precio del Excel.
  · Sin foto: el producto entra al inventario pero no se publica en la web.

Pedidos nuevos (PEDIDOS, p. ej. «Catalogo_LTSC-07_…xlsm»), cargados igual que la mercancía
inicial (inventario + web), con estas reglas además:
  · Todo precio termina en .99 (``reglas.precio_terminado_en_99``): 318.66 → 318.99. Aplica a
    la cama sola y a los combos (cama + colchón, SIN ITBMS). Las columnas con ITBMS se ignoran.
  · Combo con el nombre del colchón: «Combo con colchón First Class $439.99». Celda vacía = sin combo.
  · Fotos de «up media/»: primero por código al inicio del nombre del archivo; si no trae
    código, por tamaño + color + medidas (una sola fila del Excel). Lo dudoso lo resuelven
    las decisiones escritas a mano (DECISIONES), con su motivo, o queda sin foto y anotado.
    Sin foto de la carpeta → la foto incrustada en la fila del Excel.
  · El mismo código en varias filas con colores distintos → un producto con variantes de Color.
  · Código que ya está en el catálogo → producto aparte con sufijo (``-LTSC07``): el que
    ya estaba no se toca.
  Todas las decisiones y dudas quedan en docs/CATALOGO_REVISAR.md.

Se corre cada vez que cambie el Excel o las fotos; después, actualizar el módulo.
"""
import io
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

# Categorías y tamaños: las mismas reglas que usan Odoo y la importación de Brian.
sys.path.insert(0, str(MODULO))
from reglas import (  # noqa: E402
    asignar_foto,
    categoria_de_nombre,
    codigo_del_pedido,
    fila_para_comparar,
    medidas_de,
    normalizar,
    precio_terminado_en_99,
)

LADO_MAXIMO = 1600   # px del lado largo: nítido en pantalla y liviano (Odoo guarda hasta 1920)
CALIDAD = 82
# Fotos que no sirven de portada (borrosas o casi en blanco): van al final de la galería.
FOTOS_AL_FINAL = {'clb0119018_1.png'}

# Decisiones de la dueña ya anotadas en el reporte (se conservan al regenerarlo).
DECISIONES_DUENA = [
    '## Decisiones de la dueña (30/09/2026)',
    '',
    '- Precios dudosos (dos precios por código): quedan como están (se usa el primero).',
    '- Fotos idénticas en códigos distintos (CHCH070202/203, HYI360702/726, YH1003Fb/FDG, '
    'ZQ063605/606): quedan como están.',
    '- Reseñas de Google: quedan como están.',
]

# Pedidos nuevos del proveedor: mismo formato («Catálogo LTSC-07»: encabezado en la fila 4).
PEDIDOS = [{
    'pedido': 'LTSC-07',
    'excel': 'Catalogo_LTSC-07_Precios_PRODUCTOS_NUEVOS.xlsm',
    'hoja': 'Catálogo LTSC-07',
    'fila_encabezado': 4,
    # Código que ya está en el catálogo → producto aparte (decisión de la dueña, 2026-10-02).
    'sufijo': 'LTSC07',
    # Columnas de combo (cama + colchón, SIN ITBMS): el encabezado es el nombre del colchón.
    'combos': ['Imperial', 'Dulce Sueños', 'First Class'],
    # Fotos que el nombre no resuelve solo: revisadas a mano, contra la foto del Excel.
    'decisiones': {
        'Y0400300-Q  Queen tela marron205×151×110 cm.jpg': (
            'Y0400400-Q', None,
            'el nombre dice Y0400300-Q, pero esa fila es «tela negra» y ya tiene su foto «tela negra»; '
            'la cama de esta foto es marrón y la Queen «tela marrón» de la misma serie (Y04…-Q) es '
            'Y0400400-Q, que no tenía foto (Y0300400 tiene la suya)'),
        'Cama tapizada Full – gris 193 × 135 × 120 cm.jpg': (
            '823F', None,
            'en el Excel 823F y 903F son «Full – gris 193 × 135 × 120 cm»; 903F ya tiene su foto con '
            'código (cabecero de botones con piecera) y esta muestra el cabecero de canales con alas '
            'de la foto del Excel de 823F'),
        'Cama tapizada Queen – beige 213 × 158 × 120 cm.jpg': (
            '811Q', None,
            'en el Excel 809Q y 811Q son «Queen – beige 213 × 158 × 120 cm»; esta foto tiene el '
            'cabecero de canales verticales de la foto del Excel de 811Q (la de 809Q es de cabecero '
            'curvo con alas)'),
        'image_20261001_183440-ahora-esta-cama-tapizada-queen-en-color-beige-213.jpg': (
            '809Q', None,
            'el nombre dice «queen … beige 213» (809Q u 811Q); cabecero curvo con alas, como la foto '
            'del Excel de 809Q'),
        'Cama tapizada Queen – beige 213 × 199 × 125 cm.jpg': (
            '811K', None,
            'el nombre dice Queen, pero 213 × 199 × 125 cm son las medidas de 811K (King – beige) y '
            'ninguna Queen del Excel las tiene; es casi la misma imagen que la de 811Q'),
    },
    # Medidas del Excel que no se publican (se ven copiadas de otra fila).
    'medidas_dudosas': {
        'N-F10018-Q-BK': 'base metálica sin cabecero con 110 cm de alto (las mismas medidas que las '
                         'camas tapizadas Queen): no se publican hasta que la dueña las confirme',
    },
    # Lo que se vio al revisar las fotos a mano (va tal cual al reporte).
    'notas': [
        '`888Q`: la descripción del Excel no trae color («Cama tapizada Queen»); 888K sí dice beige. '
        'Sale sin color en el nombre.',
        '`822F` y `HK-BF-022-N-F-1-W` son los dos «Full – blanco». La foto sin código «Full – blanco '
        '193 × 135 × 110» fue a 822F porque solo 822F tiene esas medidas en el Excel; HK-BF-022-N-F-1-W '
        'tiene su propia foto con código.',
        '`908K` beige: sus tres fotos son casi la misma imagen (una dice «con colchón»); quedan las tres '
        'en ese color, la de «con colchón» al final.',
        '`811Q` y `811K` quedan con casi la misma imagen (los nombres de archivo dicen 213 × 158 y '
        '213 × 199): confirmar que 811K es esa cama.',
        'La foto incrustada en el Excel de `822F` muestra una cama de color tostado, no blanca: la foto '
        'de la carpeta («Full – blanco») sí es blanca. Confirmar el color con la mercancía.',
    ],
}]



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
    return categoria_de_nombre(nombre, 'organizacion')


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


# --- Pedidos nuevos (Excel del proveedor + fotos de «up media») ------------------------------

EXTENSIONES_PEDIDO = ('.png', '.jpg', '.jpeg', '.webp')


def guardar_foto(origen, nombre):
    """Foto (ruta o bytes del Excel) → static/img/productos/<nombre>.jpg, 1600 px, JPEG."""
    with Image.open(origen) as original:
        foto = original.convert('RGB')
    foto.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
    destino = DESTINO_IMG / f'{nombre}.jpg'
    foto.save(destino, 'JPEG', quality=CALIDAD, optimize=True, progressive=True)
    return destino.name


def leer_pedido(pedido, avisos):
    """Filas del Excel del pedido (las que tienen código), cada una con su foto incrustada.

    La foto es de la fila donde TERMINA su ancla: en «Catálogo LTSC-07» dos fotos empiezan
    al pie de la fila anterior.
    """
    wb = openpyxl.load_workbook(ORIGEN / pedido['excel'], data_only=True)
    hoja = wb[pedido['hoja']]
    enc = pedido['fila_encabezado']
    titulos = [str(c.value or '').strip() for c in hoja[enc]]

    def columna(inicio):
        return next(i for i, t in enumerate(titulos) if t.startswith(inicio))

    imagenes = {}
    for imagen in hoja._images:
        ancla = imagen.anchor
        desde = ancla._from.row + 1
        hasta = ancla.to.row + 1 if getattr(ancla, 'to', None) is not None else desde
        if hasta != desde:
            avisos.append(f'La foto incrustada que empieza en la fila {desde} del Excel termina en la '
                          f'fila {hasta}: se tomó como foto de la fila {hasta}.')
        imagenes.setdefault(hasta, imagen._data())
    c_codigo, c_desc, c_medidas, c_precio = (columna('Código'), columna('Descripción'),
                                             columna('Medidas'), columna('Precio cama sola'))
    combos = {marca: columna(marca) for marca in pedido['combos']}
    filas = []
    for n, valores in enumerate(hoja.iter_rows(min_row=enc + 1, values_only=True), start=enc + 1):
        if not valores[c_codigo]:
            continue
        filas.append({
            'fila': n,
            'codigo': str(valores[c_codigo]).strip(),
            'descripcion': str(valores[c_desc] or '').strip(),
            'medidas': str(valores[c_medidas] or '').strip(),
            'precio': valores[c_precio],
            'combos': {m: valores[c] for m, c in combos.items() if valores[c] not in (None, '')},
            'imagen': imagenes.get(n),
        })
    return filas


def _slug(texto):
    return normalizar(texto).replace(' ', '-')


class Pedido:
    """Un pedido nuevo → productos para catalogo.json + su parte del reporte."""

    COMO = {'codigo': 'por código', 'descripcion': 'por descripción', 'decision': 'decisión revisada a mano'}

    def __init__(self, pedido, catalogo, usadas):
        self.pedido = pedido
        self.nombre = pedido['pedido']
        self.catalogo = catalogo
        self.avisos = []
        self.filas = leer_pedido(pedido, self.avisos)
        self.existentes = {item['codigo'] for item in catalogo}
        self.comparables = [fila_para_comparar(f['codigo'], f['descripcion'], f['medidas']) for f in self.filas]
        self.grupos = OrderedDict()
        for i, f in enumerate(self.filas):
            self.grupos.setdefault(f['codigo'], []).append(i)
        self.fotos_fila = {i: [] for i in range(len(self.filas))}
        self.asignadas, self.dudosas, self.ajenas = [], [], []
        self.aparte, self.precios, self.foto_excel = [], [], []
        self.destino_de = {}
        self._asignar_fotos(usadas)

    def codigo(self, codigo_excel):
        return codigo_del_pedido(codigo_excel, self.existentes, self.pedido['sufijo'])

    def _asignar_fotos(self, usadas):
        """Fotos de la carpeta que no son de la carga inicial → fila del Excel."""
        archivos = sorted(f.name for f in ORIGEN.iterdir()
                          if f.suffix.lower() in EXTENSIONES_PEDIDO and f.name not in usadas)
        for archivo in archivos:
            r = asignar_foto(archivo, self.comparables, self.pedido['decisiones'])
            if r['fila'] is not None:
                self.fotos_fila[r['fila']].append(archivo)
                self.asignadas.append((archivo, r))
            elif r['como'] == 'ambigua' or describe_una_cama(archivo):
                self.dudosas.append(f'`{archivo}`: {r["nota"]}. **No se usó.**')
            else:
                self.ajenas.append(archivo)

    def _fotos_de_fila(self, i, base, etiqueta):
        originales = sorted(self.fotos_fila[i], key=lambda a: ('colchon' in normalizar(a), a))
        if originales:
            guardadas = [guardar_foto(ORIGEN / a, f'{base}_{n}') for n, a in enumerate(originales, start=1)]
            self.destino_de.update(zip(originales, guardadas, strict=True))
            return guardadas
        if self.filas[i]['imagen']:
            self.foto_excel.append(f'{etiqueta} (fila {self.filas[i]["fila"]})')
            return [guardar_foto(io.BytesIO(self.filas[i]['imagen']), f'{base}_excel')]
        return []

    def _medidas(self, codigo_excel, texto):
        medidas = medidas_de(texto)
        if codigo_excel in self.pedido['medidas_dudosas']:
            self.avisos.append(f'`{codigo_excel}`: el Excel dice «{texto}»; '
                               f'{self.pedido["medidas_dudosas"][codigo_excel]}.')
            return None
        if not medidas:
            self.avisos.append(f'`{codigo_excel}`: en «Medidas» el Excel dice «{texto}» (no son medidas): '
                               'la ficha sale sin medidas.')
            return None
        return 'Largo × Ancho × Alto: ' + ' × '.join(map(str, medidas)) + ' cm'

    def _filas_del_codigo(self, codigo_excel, indices):
        """Filas que forman el producto: varias solo si cada una es de un color distinto."""
        primera = self.filas[indices[0]]
        for i in indices[1:]:
            f = self.filas[i]
            if (f['precio'], f['combos'], f['medidas']) != (primera['precio'], primera['combos'], primera['medidas']):
                self.avisos.append(f'`{codigo_excel}`: las filas {primera["fila"]} y {f["fila"]} tienen precio, '
                                   'combo o medidas distintos; se usó la primera.')
        colores = [self.comparables[i]['color'] for i in indices]
        if len(indices) > 1 and (None in colores or len(set(colores)) != len(colores)):
            self.avisos.append(f'`{codigo_excel}`: filas repetidas sin un color que las distinga; se usó la primera.')
            return indices[:1]
        return indices

    def producto(self, codigo_excel, indices, orden):
        indices = self._filas_del_codigo(codigo_excel, indices)
        primera = self.filas[indices[0]]
        precio = precio_terminado_en_99(primera['precio'])
        if precio is None:
            self.avisos.append(f'`{codigo_excel}` ({primera["descripcion"]}): sin precio en el Excel; no se importó.')
            return None
        codigo = self.codigo(codigo_excel)
        if codigo != codigo_excel:
            viejo = next(i for i in self.catalogo if i['codigo'] == codigo_excel)
            self.aparte.append(
                f'`{codigo_excel}` ya está en el catálogo («{viejo["nombre_web"]}», '
                f'${viejo["precios"].get("", 0):.2f}); el pedido {self.nombre} dice ${precio:.2f}. El que '
                f'estaba no se toca; las unidades del pedido son el producto aparte **`{codigo}`**.')
        con_colores = len(indices) > 1
        nombre = primera['descripcion']
        if con_colores:
            nombre = re.split(r'\s+[–-]\s+', nombre)[0].strip()
        combo = ' · '.join(f'Combo con colchón {marca} ${precio_terminado_en_99(valor):.2f}'
                           for marca, valor in primera['combos'].items()) or None
        base = codigo_archivo(codigo)
        item = {
            'codigo': codigo,
            'nombre': nombre,
            'nombre_web': nombre,
            'medidas': self._medidas(codigo_excel, primera['medidas']),
            'categoria': categoria(nombre),
            'orden': orden,
            'precios': {'': precio},
            'combo': combo,
            'fotos': [],
            'pedido': self.nombre,
        }
        if con_colores:
            item['colores'] = OrderedDict()
            for i in indices:
                color = self.comparables[i]['color']
                item['colores'][color.capitalize()] = self._fotos_de_fila(
                    i, f'{base}-{_slug(color)}', f'`{codigo}` {color}')
            item['fotos'] = next((f[:1] for f in item['colores'].values() if f), [])
        else:
            item['fotos'] = self._fotos_de_fila(indices[0], base, f'`{codigo}`')
        excel_combos = ', '.join(f'{m} {v:.2f}' for m, v in primera['combos'].items())
        self.precios.append(f'| `{codigo}` | {primera["precio"]:.2f} → **{precio:.2f}** | '
                            f'{excel_combos or "—"} → {combo or "sin combo"} |')
        return item

    def productos(self):
        orden = max(item['orden'] for item in self.catalogo)
        nuevos = []
        for codigo_excel, indices in self.grupos.items():
            item = self.producto(codigo_excel, indices, orden + 1)
            if item:
                orden += 1
                nuevos.append(item)
        # Dos productos no pueden llamarse igual: se les suma la referencia.
        usados = {item['nombre_web'].lower() for item in self.catalogo}
        repetidos = {}
        for item in nuevos:
            repetidos.setdefault(item['nombre_web'].lower(), []).append(item)
        for clave, items in repetidos.items():
            if len(items) > 1 or clave in usados:
                for item in items:
                    item['nombre_web'] += f' (ref. {item["codigo"]})'
        return nuevos

    def reporte(self, nuevos):
        por_fila = {
            i: f'**{self.codigo(f["codigo"])}**'
               + (f' {self.comparables[i]["color"]}' if len(self.grupos[f['codigo']]) > 1 else '')
            for i, f in enumerate(self.filas)
        }
        variantes = [f'`{i["codigo"]}` ({", ".join(i["colores"])})' for i in nuevos if i.get('colores')]
        lineas = [
            f'## Pedido {self.nombre} (`up media/{self.pedido["excel"]}`)',
            '',
            f'Generado por `scripts/importar_catalogo.py`. Productos nuevos: **{len(nuevos)}** '
            f'({len(self.filas)} filas del Excel). Con variantes de color (un producto por código, misma '
            f'cifra en cada color y su foto propia): {", ".join(variantes) or "ninguno"}.',
            '',
            'Precios SIN ITBMS y terminados en .99 (se conserva la parte entera). Las columnas «Total '
            'con ITBMS» del Excel no se usan. Un combo vacío en el Excel no se crea.',
            '',
            '### Códigos que ya estaban en el catálogo: producto aparte',
            '',
            *([f'- {a}' for a in self.aparte] or ['- Ninguno.']),
            '',
            '### Precios (Excel → precio cargado)',
            '',
            '| Producto | Cama sola | Combo (Excel → cargado) |',
            '|---|---|---|',
            *self.precios,
            '',
            '### Fotos de la carpeta: a qué producto fue cada una',
            '',
            'Primera foto = principal; las demás, a la galería (fotos «con colchón» al final).',
            '',
            *[f'- `{a}` → {por_fila[r["fila"]]} (`{self.destino_de.get(a, "?")}`): '
              f'{self.COMO[r["como"]]} — {r["nota"]}.' for a, r in self.asignadas],
            '',
            '### Fotos dudosas que no se usaron',
            '',
            *([f'- {d}' for d in self.dudosas] or ['- Ninguna.']),
            '',
            '### Productos con la foto del Excel (no había foto en la carpeta)',
            '',
            *([f'- {f}' for f in self.foto_excel] or ['- Ninguno.']),
            '',
            '### Otras dudas del Excel',
            '',
            *[f'- {a}' for a in self.avisos + self.pedido.get('notas', [])],
            '',
        ]
        if self.ajenas:
            lineas += [f'Fotos de «up media» que no son de ningún producto (ni de la carga inicial ni de '
                       f'{self.nombre}): {", ".join(f"`{a}`" for a in self.ajenas)}.', '']
        return lineas


def cargar_pedido(pedido, catalogo, usadas):
    """Productos de un pedido nuevo para catalogo.json + las líneas del reporte."""
    p = Pedido(pedido, catalogo, usadas)
    nuevos = p.productos()
    return nuevos, p.reporte(nuevos)


def describe_una_cama(archivo):
    """¿El nombre del archivo describe una cama (tamaño o medidas)? Entonces no es ajeno."""
    return bool(re.search(r'\b(twin|full|queen|king)\b', normalizar(archivo)) or medidas_de(archivo))


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
    usadas = {f for p in productos.values() for f in fotos_de(p['codigo'], archivos)}
    inicial = list(catalogo)
    lineas_pedidos = []
    for pedido in PEDIDOS:
        nuevos, lineas_pedido = cargar_pedido(pedido, catalogo, usadas)
        catalogo.extend(nuevos)
        lineas_pedidos += lineas_pedido
        print(f'Pedido {pedido["pedido"]}: {len(nuevos)} productos nuevos.')
    DESTINO_JSON.parent.mkdir(parents=True, exist_ok=True)
    DESTINO_JSON.write_text(json.dumps(catalogo, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    catalogo = inicial

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
        *DECISIONES_DUENA,
        '',
        *lineas_pedidos,
    ]
    REPORTE.write_text('\n'.join(lineas), encoding='utf-8')
    print(f'{len(catalogo)} productos, {sum(len(c["fotos"]) for c in catalogo)} fotos, '
          f'{len(revisar)} para revisar, {len(sin_foto)} sin foto.')


if __name__ == '__main__':
    sys.exit(main())
