"""Reglas del catálogo de D'CASA sin dependencias de Odoo.

Las comparten la carga del catálogo (``catalogo.py``), el script que lee el Excel de la
empresa (``scripts/importar_catalogo.py``) y la importación de Excel de proveedores de Brian
(``dcasa_brian``): la misma categoría y el mismo tamaño salen del mismo nombre.
"""
import re
import unicodedata
from decimal import Decimal

TAMANOS = ['Twin', 'Full', 'Queen', 'King']

# Categoría de la tienda según el nombre del producto (primera regla que coincide).
CATEGORIAS = [
    (r'colch', 'colchones'),
    (r'mueble (de|para) tv|mueble tv', 'muebles_tv'),
    (r'sof[aá]', 'salas'),
    (r'zapatera', 'zapateras'),
    (r'escritorio|mesa ajustable', 'oficina'),
    (r'estante|librero|organizador|mueble de cocina|mueble type|biblioteca|despensa|mueble para jardin',
     'organizacion'),
    (r'cama|camarote|mesa de noche|peinadora|tocador|gavetero|c[oó]moda|box spring|box tapizado|cabecero|espejo'
     r'|almohada', 'recamaras'),
]


def categoria_de_nombre(nombre, defecto=None):
    """«Cama tapizada King» → 'recamaras'. Sin coincidencia → ``defecto``."""
    for patron, clave in CATEGORIAS:
        if re.search(patron, nombre or '', re.I):
            return clave
    return defecto


def tamano_del_nombre(nombre):
    """«Cama king» es de un solo tamaño, King: así aparece al filtrar la tienda por tamaño."""
    m = re.search(r'\b(twin|full|queen|king)\b', nombre or '', re.I)
    return m.group(1).capitalize() if m else None


# --- Precios: todos terminan en .99 (regla de la dueña, 2026-10-02) --------------------------

def precio_terminado_en_99(valor):
    """Se conserva la parte entera y los centavos pasan a .99: 318.66 → 318.99, 439.98 → 439.99.

    129.99 queda igual. Vale para el precio de la cama sola y para los de combo (siempre SIN
    ITBMS). Una celda vacía sigue vacía (``None``): un precio que no está no se inventa.
    """
    if valor is None or valor == '':
        return None
    entero = int(Decimal(str(valor)))
    return float(Decimal(entero) + Decimal('0.99'))


def codigo_del_pedido(codigo, existentes, sufijo):
    """Código de un pedido nuevo que ya existe en el catálogo → producto aparte con sufijo.

    Decisión de la dueña (2026-10-02): el producto que ya estaba no se toca (ni precio ni
    foto); las unidades del pedido nuevo son otro producto: ``Y0300300`` → ``Y0300300-LTSC07``.
    """
    return f'{codigo}-{sufijo}' if codigo in existentes else codigo


# --- Fotos de «up media» → fila del Excel de un pedido ---------------------------------------

# Del más largo al más corto: «gris claro» antes que «gris».
COLORES = ['gris claro', 'gris oscuro', 'beige', 'negro', 'negra', 'gris', 'blanco', 'blanca',
           'marron', 'crema', 'rosado']
SINONIMOS_COLOR = {'negra': 'negro', 'blanca': 'blanco'}
MATERIALES = ['cuero', 'lino', 'tela']


def normalizar(texto):
    """Sin tildes, en minúsculas, «×» → «x», letras y cifras separadas y un solo espacio.

    «tela Marrón205×151» → «tela marron 205 x 151» (el nombre del archivo pega color y medidas).
    """
    texto = str(texto or '').replace('×', 'x')
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower()
    texto = re.sub(r'(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def color_de(texto):
    """«Cama tapizada Queen – tela negra» → 'negro'. Sin color conocido → None."""
    limpio = normalizar(texto)
    for color in COLORES:
        if re.search(rf'\b{color}\b', limpio):
            return SINONIMOS_COLOR.get(color, color)
    return None


def material_de(texto):
    """«… – cuero marrón» → 'cuero'. Sin material conocido → None."""
    limpio = normalizar(texto)
    return next((m for m in MATERIALES if re.search(rf'\b{m}\b', limpio)), None)


def medidas_de(texto):
    """«203 × 193 × 123 cm» o «205×151×110» → (203, 193, 123). Sin tres cifras → None."""
    m = re.search(r'(\d{2,3})\s*x\s*(\d{2,3})\s*x\s*(\d{2,3})', normalizar(texto))
    return tuple(int(n) for n in m.groups()) if m else None


def codigo_al_inicio(nombre_archivo, codigos):
    """El archivo empieza por un código del Excel («908K - Cama…», «Y0200201 -Full…»)."""
    base = re.sub(r'\.[a-z0-9]+$', '', str(nombre_archivo), flags=re.I).strip().upper()
    for codigo in sorted(codigos, key=len, reverse=True):
        clave = codigo.upper()
        if base.startswith(clave) and (len(base) == len(clave) or not base[len(clave)].isalnum()):
            return codigo
    return None


def fila_para_comparar(codigo, descripcion, medidas):
    """Lo que se compara de una fila del Excel: código, tamaño, color, material y medidas."""
    return {
        'codigo': codigo,
        'tamano': tamano_del_nombre(descripcion),
        'color': color_de(descripcion),
        'material': material_de(descripcion),
        'medidas': medidas_de(medidas),
    }


def asignar_foto(nombre_archivo, filas, decisiones=None):
    """¿De qué fila del Excel es esta foto? Nunca adivina en silencio.

    1. ``decisiones`` (revisadas a mano, con su motivo) mandan: {archivo: (código, color, motivo)};
       el nombre del archivo se compara normalizado (tildes, «×», espacios).
    2. Si el archivo empieza por un código del Excel, es de ese código (si el código tiene
       varios colores, el color del archivo elige la fila). Si el color o el material del
       archivo no son los del Excel, se asigna igual por código y queda un aviso.
    3. Sin código: tamaño + color + medidas del nombre del archivo deben señalar UNA sola fila.

    ``filas`` sale de ``fila_para_comparar``. Devuelve {'fila': índice o None, 'como':
    'decision'|'codigo'|'descripcion'|'ambigua'|'sin_coincidencia', 'nota': texto del reporte}.
    """
    decisiones = {normalizar(k): v for k, v in (decisiones or {}).items()}
    if normalizar(nombre_archivo) in decisiones:
        codigo, color, motivo = decisiones[normalizar(nombre_archivo)]
        for i, fila in enumerate(filas):
            if fila['codigo'] == codigo and (color is None or fila['color'] == color):
                return {'fila': i, 'como': 'decision', 'nota': motivo}
        return {'fila': None, 'como': 'sin_coincidencia',
                'nota': f'la decisión apunta a {codigo} {color or ""}, que no está en el Excel'}

    color = color_de(nombre_archivo)
    material = material_de(nombre_archivo)
    codigo = codigo_al_inicio(nombre_archivo, {f['codigo'] for f in filas})
    if codigo:
        candidatas = [i for i, f in enumerate(filas) if f['codigo'] == codigo]
        if len(candidatas) > 1:
            por_color = [i for i in candidatas if filas[i]['color'] == color]
            if len(por_color) == 1:
                return {'fila': por_color[0], 'como': 'codigo', 'nota': f'código {codigo}, color {color}'}
            return {'fila': None, 'como': 'ambigua',
                    'nota': f'{codigo} tiene varios colores y el archivo no dice cuál'}
        fila = filas[candidatas[0]]
        avisos = []
        if color and fila['color'] and color != fila['color']:
            avisos.append(f'el archivo dice «{color}» y el Excel «{fila["color"]}»')
        if material and fila['material'] and material != fila['material']:
            avisos.append(f'el archivo dice «{material}» y el Excel «{fila["material"]}»')
        nota = f'código {codigo}' + (f' (ojo: {"; ".join(avisos)})' if avisos else '')
        return {'fila': candidatas[0], 'como': 'codigo', 'nota': nota}

    tamano = tamano_del_nombre(nombre_archivo)
    medidas = medidas_de(nombre_archivo)
    if not (tamano or color or medidas):
        return {'fila': None, 'como': 'sin_coincidencia',
                'nota': 'el nombre no trae código, tamaño, color ni medidas'}
    candidatas = [
        i for i, f in enumerate(filas)
        if (tamano is None or f['tamano'] == tamano)
        and (color is None or f['color'] == color)
        and (medidas is None or f['medidas'] == medidas)
    ]
    texto = ' · '.join([tamano or '¿tamaño?', color or '¿color?',
                        '×'.join(map(str, medidas)) if medidas else 'sin medidas'])
    if len(candidatas) == 1:
        return {'fila': candidatas[0], 'como': 'descripcion',
                'nota': f'{texto} → única fila del Excel: {filas[candidatas[0]]["codigo"]}'}
    if candidatas:
        codigos = ', '.join(dict.fromkeys(filas[i]['codigo'] for i in candidatas))
        return {'fila': None, 'como': 'ambigua', 'nota': f'{texto} coincide con varias filas: {codigos}'}
    return {'fila': None, 'como': 'sin_coincidencia',
            'nota': f'{texto}: ninguna fila del Excel tiene ese tamaño, color y medidas'}


# --- Inventario del sistema anterior (capturas del 2026-10-02) --------------------------------

# Filas que no son productos y no se importan (regla de la dueña, LEEME del inventario).
NO_SE_IMPORTAN = (r'^descuento$', r'^propinas$', r'^x colch[oó]n .* para combo$')


def clase_de_fila_inventario(nombre):
    """'omitir' (Descuento, Propinas, «X COLCHÓN … PARA COMBO»), 'combo' («COMBO … + COLCHÓN», también
    «+ 3 COLCHONES»; entra sin publicar) o 'producto'."""
    limpio = normalizar(nombre)
    if any(re.search(patron, limpio) for patron in NO_SE_IMPORTAN):
        return 'omitir'
    if limpio.startswith('combo') and re.search(r'\+.*colch', limpio):
        return 'combo'
    return 'producto'


def _numero(texto):
    if texto is None or str(texto).strip() == '':
        return None
    return float(Decimal(str(texto).strip()))


def filas_inventario(texto_csv):
    """Filas del CSV transcrito (pagina, fila, nombre, codigo, precio_venta, costo, a_la_mano,
    pronosticado, dudas) → dicts listos para cargar: números como float (``None`` si la celda
    está vacía), ``clase`` y ``llave`` (el código o, sin código, el nombre exacto)."""
    import csv
    import io
    filas = []
    for fila in csv.DictReader(io.StringIO(texto_csv)):
        nombre = fila['nombre'].strip()
        codigo = (fila.get('codigo') or '').strip()
        filas.append({
            'pagina': int(fila['pagina']) if fila.get('pagina') else None,
            'fila': int(fila['fila']) if fila.get('fila') else None,
            'nombre': nombre,
            'codigo': codigo,
            'llave': codigo or nombre,
            'precio': _numero(fila.get('precio_venta')),
            'costo': _numero(fila.get('costo')),
            'a_la_mano': _numero(fila.get('a_la_mano')),
            'dudas': (fila.get('dudas') or '').strip(),
            'clase': clase_de_fila_inventario(nombre),
        })
    return filas


def categoria_de_inventario(fila):
    """Categoría de una fila del inventario: un combo se clasifica por la cama (lo que va antes
    del «+»), no por el colchón."""
    nombre = fila['nombre']
    if fila['clase'] == 'combo':
        nombre = nombre.split('+')[0]
    return categoria_de_nombre(nombre)


def foto_por_codigo(codigos, archivos):
    """{código: archivo} para los códigos que tienen una foto cuyo nombre empieza por el código
    (``codigo_al_inicio``); con varias, la primera en orden alfabético (``X_1.jpg`` antes que ``X_2.jpg``)."""
    fotos = {}
    for archivo in sorted(archivos):
        if not re.search(r'\.(jpe?g|png|webp)$', archivo, re.I):
            continue
        codigo = codigo_al_inicio(archivo, codigos)
        if codigo and codigo not in fotos:
            fotos[codigo] = archivo
    return fotos


def planificar_inventario(filas, existentes, fotos):
    """Qué haría la carga, sin Odoo: ``existentes`` son los códigos ya en el catálogo y ``fotos``
    el {código: archivo} disponible. Lo usan el informe (docs/) y los tests para cuadrar con la carga real.

    Devuelve {'crear', 'actualizar', 'omitidos', 'repetidos', 'negativos', 'combos', 'sin_foto',
    'con_foto', 'dudas'} con las filas de cada grupo. Un código repetido en el CSV solo entra la
    primera vez (el segundo se anota)."""
    plan = {k: [] for k in ('crear', 'actualizar', 'omitidos', 'repetidos', 'negativos', 'combos',
                            'sin_foto', 'con_foto', 'dudas')}
    vistas = set()
    for fila in filas:
        if fila['dudas']:
            plan['dudas'].append(fila)
        if fila['clase'] == 'omitir':
            plan['omitidos'].append(fila)
            continue
        if fila['llave'] in vistas:
            plan['repetidos'].append(fila)
            continue
        vistas.add(fila['llave'])
        if fila['a_la_mano'] is not None and fila['a_la_mano'] < 0:
            plan['negativos'].append(fila)
        if fila['clase'] == 'combo':
            plan['combos'].append(fila)
        if fila['llave'] in existentes:
            plan['actualizar'].append(fila)
            continue
        plan['crear'].append(fila)
        if fila['clase'] == 'combo':
            continue
        if fila['codigo'] and fila['codigo'] in fotos:
            plan['con_foto'].append(fila)
        else:
            plan['sin_foto'].append(fila)
    return plan


# --- Combos que se arman en la venta: cama + colchón con «precio en combo» -------------------
#
# Decisión de la dueña (2026-10-22): cada colchón, en cada medida, puede tener un «precio en combo» que pone Gerencia.
# Si en la misma venta va una cama de su misma medida, el colchón se cobra a ese precio; si no tiene precio en combo,
# va a su precio normal (no se inventa ninguno). La cama va a su precio normal.

TIPOS_COMBO = ('cama', 'colchon')


def tipo_combo_del_nombre(nombre):
    """¿Es una cama o un colchón para armar combos? Se sugiere por el nombre; Gerencia lo corrige en el producto.

    «Colchón Flex semiortopédico» → 'colchon'; «Cama tapizada Queen», «Camarote full», «Box spring de metal»,
    «Base de cama metálica» → 'cama'. No son: un combo ya armado («COMBO CAMA … + COLCHÓN …»), una colchoneta, un
    protector o forro de colchón, un sofá cama, una mesa de noche o un cabecero solo → ``None``.
    """
    limpio = normalizar(nombre)
    if not limpio or limpio.startswith('combo'):
        return None
    if re.search(r'\bcolchon(es)?\b', limpio):
        if re.search(r'\b(protector|forro|funda|cubre ?colchon|sabana|almohada)', limpio):
            return None
        return 'colchon'
    if re.search(r'\bsofa\b', limpio):
        return None
    if re.search(r'\b(cama|camas|camarote|camarotes|litera|literas|box springs?|box tapizado|base de cama)\b', limpio):
        return 'cama'
    return None


def medida_del_nombre(nombre, tipo=None):
    """La medida (Twin, Full, Queen, King) que dice un nombre; ``None`` si no dice ninguna o dice dos distintas.

    En un colchón, además, «4/6» es Full, «3/4» es Twin y una «Q» o una «K» sueltas son Queen y King (así vienen en el
    inventario del sistema anterior: «COLCHON DULCESUENOS SEMI RESORTE Q»).
    """
    limpio = normalizar(nombre)
    vistas = []
    for m in re.finditer(r'\b(twin|full|queen|king)\b', limpio):
        medida = m.group(1).capitalize()
        if medida not in vistas:
            vistas.append(medida)
    if not vistas and tipo == 'colchon':
        texto = str(nombre or '').lower()
        for patron, medida in ((r'\b4/6\b', 'Full'), (r'\b3/4\b', 'Twin'), (r'\bq\b', 'Queen'), (r'\bk\b', 'King')):
            if re.search(patron, texto) and medida not in vistas:
                vistas.append(medida)
    return vistas[0] if len(vistas) == 1 else None


def medida_de_valor(valor):
    """El valor del atributo «Tamaño» de una variante → la medida, si es una de las de D'CASA («queen» → 'Queen')."""
    texto = normalizar(valor)
    return next((t for t in TAMANOS if t.lower() == texto), None)


_TOLERANCIA = 1e-6


def emparejar_combos(camas, colchones):
    """Qué colchón va en combo con qué cama de la misma venta.

    ``camas``: lista de dicts ``{'clave', 'medida', 'capacidad'}`` en el orden de la venta (capacidad = cuántas camas
    × cuántos colchones lleva cada una: 1, o 2 y 3 en un camarote).
    ``colchones``: lista de dicts ``{'clave', 'medida', 'cantidad', 'con_precio', 'preferida'}`` en el orden de la
    venta (``preferida``: la clave de la cama con la que ya estaba, o ``None``).

    Devuelve ``{clave del colchón: (clave de la cama, con_precio)}``. Reglas:

    * Un colchón entra en combo solo si TODA su cantidad cabe en lo que queda libre de las camas de su misma medida
      (dos colchones king con una sola cama king: uno va en combo y el otro a precio normal).
    * Primero los colchones CON precio en combo: un colchón sin precio nunca le quita el combo a uno que sí lo tiene.
    * Dentro de cada grupo, primero el que ya estaba con esa cama (no se reparten de nuevo al cambiar algo) y después
      en el orden de la venta. La cama que se muestra es la preferida si aún tiene lugar; si no, la primera con lugar.
    """
    libre = {cama['clave']: float(cama['capacidad'] or 0) for cama in camas}
    por_medida = {}
    for cama in camas:
        if cama['medida']:
            por_medida.setdefault(cama['medida'], []).append(cama['clave'])
    resultado = {}
    for con_precio in (True, False):
        grupo = [c for c in colchones if bool(c['con_precio']) == con_precio and c['medida'] and c['cantidad'] > 0]
        grupo.sort(key=lambda c: 0 if c.get('preferida') in por_medida.get(c['medida'], ()) else 1)
        for colchon in grupo:
            claves = por_medida.get(colchon['medida'], [])
            if sum(libre[clave] for clave in claves) + _TOLERANCIA < colchon['cantidad']:
                continue
            preferida = colchon.get('preferida')
            orden = ([preferida] if preferida in claves else []) + [c for c in claves if c != preferida]
            principal = next(clave for clave in orden if libre[clave] > _TOLERANCIA)
            falta = colchon['cantidad']
            for clave in [principal] + [c for c in orden if c != principal]:
                toma = min(libre[clave], falta)
                libre[clave] -= toma
                falta -= toma
                if falta <= _TOLERANCIA:
                    break
            resultado[colchon['clave']] = (principal, con_precio)
    return resultado
