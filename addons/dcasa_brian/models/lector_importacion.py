"""Lectura de un Excel de proveedor para importar productos (funciones puras, sin modelos).

``leer_tabla(crudo, hoja=None, columna_precio=None)`` devuelve la tabla ya interpretada:

* encabezado: la fila (entre las 10 primeras) con más columnas reconocidas y más celdas
  llenas; las de arriba (título, proveedor, buscador) se ignoran;
* columnas por rol (``codigo``, ``nombre``, ``precio``, ``medidas``, ``tamano``,
  ``categoria``, ``imagen``) según el texto del encabezado; el precio es la primera columna
  que dice «precio» (nunca «costo»), o la que se pida;
* filas de datos con su número de fila de Excel (1 = primera fila);
* fotos incrustadas asignadas a SU fila por la posición del ancla (la fila que cubre la
  mayor parte de la foto). Una foto que cruza dos filas por igual, que cae fuera de la tabla
  o que comparte fila con otra NO se asigna: se reporta. Nunca se adivina.

Los precios no se calculan: se redondean a 2 decimales (``418.65999999999997`` → 418.66).
"""
import io
import re
import unicodedata
import zipfile

from PIL import Image

from odoo.tools.image import image_process

FILAS_ENCABEZADO = 10
EMU_POR_PUNTO = 12700
ALTO_FILA_DEFECTO = 15.0           # puntos
FRACCION_MINIMA = 0.6              # la foto debe estar al menos 60 % dentro de su fila
LADO_FOTO = 1920
CALIDAD_FOTO = 85

# Rol → palabras del encabezado (sin tildes, en minúsculas). Gana la columna más a la izquierda.
ROLES = {
    'codigo': ('codigo', 'cod', 'sku', 'referencia', 'ref', 'item no', 'articulo no'),
    'nombre': ('descripcion', 'nombre', 'producto', 'articulo', 'description', 'name'),
    'medidas': ('medidas', 'medida', 'dimensiones', 'dimension', 'dimensions', 'size cm'),
    'tamano': ('tamano', 'talla', 'size'),
    'categoria': ('categoria', 'category'),
    'imagen': ('imagen', 'foto', 'image', 'picture', 'photo'),
}
PALABRAS_PRECIO = ('precio', 'price', 'pvp')
PALABRAS_NO_PRECIO = ('costo', 'cost', 'fob', 'compra')
FILAS_TOTAL = ('total', 'totales', 'subtotal')


class ErrorImportacion(Exception):
    """El archivo no sirve para importar: el mensaje (en español) dice por qué y qué hacer."""


def normalizar(texto):
    texto = unicodedata.normalize('NFKD', str(texto or '').lower())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', texto).split())


def letra(indice):
    """0 → A, 27 → AB."""
    texto = ''
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        texto = chr(65 + resto) + texto
    return texto


def indice_de_letra(texto):
    if not re.fullmatch(r'[A-Za-z]{1,3}', texto or ''):
        return None
    valor = 0
    for c in texto.upper():
        valor = valor * 26 + ord(c) - 64
    return valor - 1


def _rol(encabezado):
    norma = normalizar(encabezado)
    if not norma:
        return None
    for rol, claves in ROLES.items():
        if any(norma == clave or norma.startswith(clave + ' ') for clave in claves):
            return rol
    palabras = norma.split()
    for rol, claves in ROLES.items():
        if any(len(clave) > 3 and clave in palabras for clave in claves):
            return rol
    return None


def es_precio(encabezado):
    norma = normalizar(encabezado)
    return any(p in norma.split() or norma.startswith(p) for p in PALABRAS_PRECIO) and not any(
        p in norma for p in PALABRAS_NO_PRECIO)


def texto_celda(valor):
    """Texto limpio de una celda (los códigos numéricos sin «.0»)."""
    if valor is None:
        return ''
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return ' '.join(str(valor).split())


def precio_de(valor):
    """Número de una celda de precio: 259.99, «$1,234.50», «B/. 99.99». «$—», texto o vacío → None."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    texto = str(valor).replace('B/.', '').replace('$', '').replace(',', '').strip()
    if not re.fullmatch(r'-?\d+(\.\d+)?', texto):
        return None
    return round(float(texto), 2)


def _encabezado(filas):
    """(índice en ``filas``, {col: texto}) de la fila de encabezado."""
    mejor, mejor_puntaje = None, (-1, -1)
    for i, fila in enumerate(filas[:FILAS_ENCABEZADO]):
        celdas = {c: texto_celda(v) for c, v in enumerate(fila) if texto_celda(v)
                  and not str(v).startswith('=')}
        roles = {_rol(t) for t in celdas.values()} - {None}
        precio = any(es_precio(t) for t in celdas.values())
        puntaje = (len(roles) + precio, len(celdas))
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = (i, celdas), puntaje
    if not mejor or mejor_puntaje[0] < 2:
        raise ErrorImportacion(
            'No encontré la fila de encabezados (Código, Descripción, Precio…) en las primeras '
            f'{FILAS_ENCABEZADO} filas de la hoja.')
    return mejor


def _columnas(encabezados, columna_precio=None):
    """{rol: col} y la lista de columnas de precio candidatas [(col, texto)]."""
    columnas = {}
    for col in sorted(encabezados):
        rol = _rol(encabezados[col])
        if rol and rol not in columnas and not es_precio(encabezados[col]):
            columnas[rol] = col
    precios = [(col, encabezados[col]) for col in sorted(encabezados) if es_precio(encabezados[col])]
    if columna_precio:
        pedido = str(columna_precio).strip()
        col = indice_de_letra(pedido)
        if col is None or col not in encabezados:
            norma = normalizar(pedido)
            exactas = [c for c, t in encabezados.items() if normalizar(t) == norma]
            parecidas = [c for c, t in sorted(encabezados.items()) if norma and norma in normalizar(t)]
            col = (exactas or parecidas or [None])[0]
        if col is None:
            opciones = ', '.join(f'{letra(c)} «{t}»' for c, t in precios) or 'ninguna dice «precio»'
            raise ErrorImportacion(f'No encontré la columna de precio «{pedido}». Columnas de precio: {opciones}.')
        columnas['precio'] = col
    elif precios:
        columnas['precio'] = precios[0][0]
    return columnas, precios


def _altos(hoja, hasta):
    """Alto en EMU de cada fila (índice 0 = fila 1), hasta la fila ``hasta`` (0-based) incluida."""
    defecto = getattr(hoja.sheet_format, 'defaultRowHeight', None) or ALTO_FILA_DEFECTO
    altos = []
    for fila in range(1, hasta + 2):
        dimension = hoja.row_dimensions.get(fila) if hasattr(hoja.row_dimensions, 'get') else None
        if dimension is not None and dimension.hidden:
            altos.append(0)
            continue
        alto = dimension.height if dimension is not None and dimension.height else defecto
        altos.append(int(alto * EMU_POR_PUNTO))
    return altos


def _span(ancla):
    """(fila, desplazamiento, fila_fin, desplazamiento_fin, columna) en EMU, o None."""
    desde = getattr(ancla, '_from', None)
    if desde is None:
        posicion, tamano = getattr(ancla, 'pos', None), getattr(ancla, 'ext', None)
        if posicion is None or tamano is None:
            return None
        return ('abs', posicion.y, posicion.y + (tamano.height or 0), None)
    hasta = getattr(ancla, 'to', None)
    if hasta is not None:
        return ('celdas', (desde.row, desde.rowOff), (hasta.row, hasta.rowOff), desde.col)
    tamano = getattr(ancla, 'ext', None)
    alto = getattr(tamano, 'height', None) or getattr(tamano, 'cy', None) or 0
    return ('alto', (desde.row, desde.rowOff), alto, desde.col)


def _ubicar(span, altos):
    """(fila 0-based con más cobertura, fracción cubierta, otra fila tocada)."""
    inicios = [0]
    for alto in altos:
        inicios.append(inicios[-1] + alto)

    def y(fila, desplazamiento):
        if fila >= len(altos):
            return inicios[-1] + desplazamiento
        return inicios[fila] + desplazamiento

    if span[0] == 'abs':
        y0, y1 = span[1], span[2]
    elif span[0] == 'celdas':
        y0, y1 = y(*span[1]), y(*span[2])
    else:
        y0 = y(*span[1])
        y1 = y0 + span[2]
    if y1 <= y0:
        fila = next((f for f in range(len(altos)) if inicios[f] <= y0 < inicios[f + 1]), len(altos) - 1)
        return fila, 1.0, None
    coberturas = []
    for fila, alto in enumerate(altos):
        cubierto = min(y1, inicios[fila] + alto) - max(y0, inicios[fila])
        if cubierto > 0:
            coberturas.append((cubierto, fila))
    if not coberturas:
        return None, 0.0, None
    coberturas.sort(reverse=True)
    cubierto, fila = coberturas[0]
    otra = coberturas[1][1] if len(coberturas) > 1 else None
    return fila, cubierto / (y1 - y0), otra


def foto_normalizada(crudo):
    """Bytes listos para ``image_1920``: lado mayor ≤ 1920 px; JPEG calidad 85, o PNG si tiene
    transparencia. Lanza ``ValueError`` si no es una imagen que se pueda abrir."""
    try:
        imagen = Image.open(io.BytesIO(crudo))
        imagen.load()
    except Exception as error:  # noqa: BLE001 — EMF/WMF u otro formato que PIL no abre
        raise ValueError('formato de imagen que no puedo abrir') from error
    transparente = imagen.mode in ('RGBA', 'LA', 'PA') or (
        imagen.mode == 'P' and 'transparency' in imagen.info)
    if transparente:
        return image_process(crudo, size=(LADO_FOTO, LADO_FOTO), verify_resolution=True, output_format='PNG')
    return image_process(crudo, size=(LADO_FOTO, LADO_FOTO), verify_resolution=True,
                         quality=CALIDAD_FOTO, output_format='JPEG')


def _imagenes(hoja, fila_encabezado, filas_datos):
    """Fotos asignadas: ({fila_excel: bytes crudos}, [avisos], total)."""
    imagenes = list(getattr(hoja, '_images', []) or [])
    if not imagenes:
        return {}, [], 0
    ultima = max(filas_datos) if filas_datos else fila_encabezado
    altos = _altos(hoja, ultima + 50)
    por_fila, avisos = {}, []
    for numero, imagen in enumerate(imagenes, start=1):
        span = _span(imagen.anchor)
        fila, fraccion, otra = _ubicar(span, altos) if span else (None, 0.0, None)
        fila_excel = fila + 1 if fila is not None else None
        if fila_excel is None:
            avisos.append(f'La foto {numero} no tiene una posición que pueda leer: no la asigné.')
            continue
        if fraccion < FRACCION_MINIMA and otra is not None:
            avisos.append(f'La foto {numero} cae entre las filas {fila_excel} y {otra + 1}: no sé de cuál '
                          'producto es, no la asigné.')
            continue
        if fila_excel not in filas_datos:
            avisos.append(f'La foto {numero} está en la fila {fila_excel}, que no es de un producto: '
                          'no la asigné.')
            continue
        por_fila.setdefault(fila_excel, []).append(imagen)
    asignadas = {}
    for fila_excel, lista in sorted(por_fila.items()):
        if len(lista) > 1:
            avisos.append(f'La fila {fila_excel} tiene {len(lista)} fotos: no sé cuál es la del producto, '
                          'no asigné ninguna.')
            continue
        try:
            asignadas[fila_excel] = lista[0]._data()
        except Exception:  # noqa: BLE001 — imagen dañada dentro del zip
            avisos.append(f'La foto de la fila {fila_excel} está dañada: no la asigné.')
    return asignadas, avisos, len(imagenes)


def leer_tabla(crudo, hoja=None, columna_precio=None):
    """Interpreta el Excel. Ver el docstring del módulo. Lanza ``ErrorImportacion``."""
    import openpyxl
    try:
        nombres = set(zipfile.ZipFile(io.BytesIO(crudo)).namelist())
    except zipfile.BadZipFile as error:
        raise ErrorImportacion('Solo importo Excel .xlsx (el archivo no lo es o está dañado).') from error
    if 'xl/workbook.xml' not in nombres:
        raise ErrorImportacion('Solo importo Excel .xlsx: este archivo no es una hoja de cálculo.')
    avisos = []
    if any(n.startswith('xl/richData/') for n in nombres):
        avisos.append('El archivo trae fotos DENTRO de celdas (Excel 365): esas todavía no las leo. '
                      'Si las necesitas, en Excel usa «Colocar sobre las celdas».')
    libro = openpyxl.load_workbook(io.BytesIO(crudo), data_only=True)
    try:
        hojas = [h.title for h in libro.worksheets]
        if hoja:
            elegida = next((h for h in libro.worksheets if normalizar(h.title) == normalizar(hoja)), None)
            if elegida is None:
                raise ErrorImportacion(f'No hay una hoja «{hoja}». Hojas: {", ".join(hojas)}.')
        else:
            visibles = [h for h in libro.worksheets if h.sheet_state == 'visible'] or libro.worksheets
            elegida = max(visibles, key=lambda h: (bool(getattr(h, '_images', None)), h.max_row or 0))
        filas = [list(f) for f in elegida.iter_rows(values_only=True)]
        indice, encabezados = _encabezado(filas)
        columnas, precios = _columnas(encabezados, columna_precio)
        if 'codigo' not in columnas:
            raise ErrorImportacion('No encontré la columna «Código» (o SKU / Referencia): sin código no '
                                   'puedo saber si un producto ya existe.')
        fila_encabezado = indice + 1
        datos = []
        for i, fila in enumerate(filas[indice + 1:], start=indice + 2):
            valores = {rol: (fila[col] if col < len(fila) else None) for rol, col in columnas.items()}
            if not any(texto_celda(v) for rol, v in valores.items() if rol != 'imagen'):
                continue
            if not texto_celda(valores.get('codigo')) and any(
                    normalizar(v) in FILAS_TOTAL for v in valores.values() if isinstance(v, str)):
                continue  # fila de totales al pie de la tabla
            datos.append({'fila': i, 'valores': valores})
        formulas = _formulas_sin_valor(crudo, elegida.title, columnas.get('precio'),
                                       [d['fila'] for d in datos if d['valores'].get('precio') is None])
        fotos, avisos_fotos, total_fotos = _imagenes(elegida, fila_encabezado, {d['fila'] for d in datos})
    finally:
        libro.close()
    return {
        'hojas': hojas,
        'hoja': elegida.title,
        'fila_encabezado': fila_encabezado,
        'encabezados': {letra(c): t for c, t in sorted(encabezados.items())},
        'columnas': {rol: {'columna': letra(c), 'encabezado': encabezados.get(c, '')}
                     for rol, c in columnas.items()},
        'columnas_precio': [{'columna': letra(c), 'encabezado': t} for c, t in precios],
        'filas': datos,
        'formulas_sin_valor': formulas,
        'fotos': fotos,
        'fotos_en_hoja': total_fotos,
        'avisos': avisos + avisos_fotos,
    }


def _formulas_sin_valor(crudo, hoja, col, filas):
    """Filas cuyo precio es una fórmula sin valor guardado (el archivo no se guardó en Excel)."""
    if col is None or not filas:
        return []
    import openpyxl
    libro = openpyxl.load_workbook(io.BytesIO(crudo), read_only=True, data_only=False)
    try:
        hoja_formulas = libro[hoja]
        salida = []
        for fila in filas:
            valor = hoja_formulas.cell(row=fila, column=col + 1).value
            if isinstance(valor, str) and valor.startswith('='):
                salida.append(fila)
        return salida
    finally:
        libro.close()
