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
    (r'mueble de tv', 'muebles_tv'),
    (r'sof[aá]', 'salas'),
    (r'zapatera', 'zapateras'),
    (r'escritorio|mesa ajustable', 'oficina'),
    (r'estante|librero|organizador|mueble de cocina|mueble type', 'organizacion'),
    (r'cama|camarote|mesa de noche|peinadora|tocador|gavetero', 'recamaras'),
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
