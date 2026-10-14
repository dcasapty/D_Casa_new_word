"""Combos de cama + colchón: lectura de ``combos.csv`` y lectura del NOMBRE de un combo.

Funciones PURAS (sin base de datos), como ``reglas.py``. Dos trabajos:

1. ``filas_combos``: lee el archivo ``combos.csv`` que deja Cowork (una fila por pieza de cada combo) y arma, para cada
   combo, la lista de GRUPOS que lleva el tipo «Combo» de Odoo: cada pieza es un grupo de una sola opción; las piezas
   marcadas « [opción]» son opciones de UN mismo grupo (el cliente escoge una).
2. ``resolver_combo``: lee un nombre como «COMBO CAMA FELPA KING WHITE XHT022-K-W + COLCHÓN FIRST» y busca la cama y el
   colchón entre los productos que se le pasan. Nunca adivina: cada pieza queda ``claro`` (un solo producto posible),
   ``dudoso`` (varios candidatos o una suposición) o ``sin_resolver``.
"""
import re
import unicodedata

from .reglas import leer_csv, numero

COLUMNAS_COMBOS = ('codigo_combo', 'nombre_combo', 'codigo_componente', 'nombre_componente')
MAX_CANTIDAD = 10
_MARCA_OPCION = re.compile(r'\s*\[\s*opci[oó]n\s*\]\s*$', re.IGNORECASE)
TAMANOS = ('twin', 'full', 'queen', 'king')
ETIQUETA_TAMANO = {'twin': 'Twin', 'full': 'Full', 'queen': 'Queen', 'king': 'King'}
CLARO, DUDOSO, SIN_RESOLVER = 'claro', 'dudoso', 'sin_resolver'


def limpio(texto):
    """Sin tildes ni mayúsculas y con un solo espacio: «COLCHÓN  Dulces Sueños» → «colchon dulces suenos»."""
    texto = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', texto).strip()


def _espacios(texto):
    return re.sub(r'\s+', ' ', str(texto or '')).strip()


# ----------------------------------------------------------------------------------------------
# combos.csv
# ----------------------------------------------------------------------------------------------

def nombre_de_grupo(nombre_pieza, numero_de=1, de=1, a_escoger=False):
    """El nombre que ve la dueña en la pestaña del combo: «Cama», «Colchón», «Colchón 2 de 3», «Colchón (a escoger)»."""
    texto = limpio(nombre_pieza)
    if re.search(r'colch', texto):
        rol = 'Colchón'
    elif re.search(r'cama|camarote|box spring|cabecero|base', texto):
        rol = 'Cama'
    else:
        rol = _espacios(nombre_pieza)[:60] or 'Pieza'
    if de > 1:
        rol = f'{rol} {numero_de} de {de}'
    return f'{rol} (a escoger)' if a_escoger else rol


def _entero_positivo(texto, columna, fila):
    """``''`` → 1; ``'2'`` o ``'2.0'`` → 2; ``'0'``, ``'-1'`` o ``'1.5'`` → ``None`` (no sirve)."""
    valor = numero(texto, columna, fila)
    if valor is None:
        return 1
    if valor != int(valor) or not 1 <= valor <= MAX_CANTIDAD:
        return None
    return int(valor)


def filas_combos(texto):
    """``(combos, errores)`` de combos.csv.

    Una fila por pieza de cada combo: ``codigo_combo, nombre_combo, precio_combo, codigo_componente,
    nombre_componente, cantidad, precio_extra`` (y, si hace falta, una columna ``grupo``). El combo se identifica por su
    código y, sin código, por su nombre exacto. Cada combo trae:

    * ``codigo``, ``nombre``, ``clave`` (el código o, sin código, el nombre), ``precio`` (``None`` si no se registró:
      vacío o 0) y ``fila`` (la primera fila del archivo);
    * ``grupos``: lista de ``{'nombre', 'opciones': [{'codigo', 'nombre', 'extra'}], 'a_escoger'}``. Cada pieza es un
      grupo de una sola opción; una pieza con ``cantidad`` N es N grupos iguales (Odoo no tiene cantidad por opción).
      Las piezas cuyo nombre termina en « [opción]» son las opciones de UN grupo (o de uno por cada valor distinto de
      la columna ``grupo``);
    * ``sin_piezas``: ``True`` si el archivo lo lista sin ninguna pieza.

    Un combo mal escrito no se carga: va a ``errores`` como ``(clave, motivo)``. Un número ilegible corta todo el
    archivo (con su fila), como en los demás archivos.
    """
    combos, errores, orden, malos = {}, [], [], {}
    for posicion, celdas in enumerate(leer_csv(texto, COLUMNAS_COMBOS, 'combos.csv'), start=2):
        clave = celdas.get('codigo_combo', '') or _espacios(celdas.get('nombre_combo', ''))
        if not clave:
            errores.append((f'fila {posicion}', 'la fila no tiene código ni nombre de combo'))
            continue
        if clave not in combos:
            orden.append(clave)
            combos[clave] = {'clave': clave, 'codigo': celdas.get('codigo_combo', ''), 'nombre': '', 'precio': None,
                             'fila': posicion, 'piezas': [], 'sin_piezas': False}
        problema = _sumar_fila(combos[clave], celdas, posicion)
        if problema:
            malos.setdefault(clave, problema)
    resultado = []
    for clave in orden:
        combo = combos[clave]
        grupos, problema = _grupos_de(combo['piezas']) if clave not in malos else ([], malos[clave])
        if problema:
            errores.append((clave, problema))
            continue
        resultado.append({
            'clave': clave, 'codigo': combo['codigo'], 'nombre': combo['nombre'], 'precio': combo['precio'],
            'fila': combo['fila'], 'grupos': grupos, 'sin_piezas': combo['sin_piezas'] and not grupos})
    return resultado, errores


def _sumar_fila(combo, celdas, posicion):
    """Agrega al ``combo`` lo que dice una fila del archivo. Devuelve el problema de la fila o ``None``."""
    nombre = _espacios(celdas.get('nombre_combo', ''))
    if nombre and not combo['nombre']:
        combo['nombre'] = nombre
    problema = None
    precio = numero(celdas.get('precio_combo'), 'precio_combo', posicion)
    if precio:  # 0 o vacío: «no se registró»
        if combo['precio'] not in (None, precio):
            problema = 'el precio del combo no es el mismo en todas sus filas'
        combo['precio'] = precio
    codigo, nombre_pieza = celdas.get('codigo_componente', ''), _espacios(celdas.get('nombre_componente', ''))
    cantidad_cruda, extra_crudo = celdas.get('cantidad', ''), celdas.get('precio_extra', '')
    cantidad = _entero_positivo(cantidad_cruda, 'cantidad', posicion)
    extra = numero(extra_crudo, 'precio_extra', posicion)
    if not codigo and not nombre_pieza:
        combo['sin_piezas'] = True
        if cantidad_cruda or extra_crudo:
            return problema or f'fila {posicion}: trae cantidad o precio extra pero ninguna pieza'
        return problema
    if cantidad is None:
        return problema or f'fila {posicion}: la cantidad tiene que ser un número entero de 1 a {MAX_CANTIDAD}'
    if extra is not None and extra < 0:
        return problema or f'fila {posicion}: el precio extra no puede ser negativo'
    a_escoger = bool(_MARCA_OPCION.search(nombre_pieza))
    combo['piezas'].append({
        'codigo': codigo, 'nombre': _MARCA_OPCION.sub('', nombre_pieza).strip(), 'cantidad': cantidad,
        'extra': extra or 0.0, 'a_escoger': a_escoger, 'grupo': celdas.get('grupo', '') if a_escoger else '',
        'fila': posicion})
    return problema


def _grupos_de(piezas):
    """``(grupos, motivo)``: de las filas de un combo a los grupos de Odoo (ver ``filas_combos``)."""
    grupos, de_opciones = [], {}
    for pieza in piezas:
        opcion = {'codigo': pieza['codigo'], 'nombre': pieza['nombre'], 'extra': pieza['extra']}
        if not pieza['a_escoger']:
            for n in range(1, pieza['cantidad'] + 1):
                grupos.append({'nombre': nombre_de_grupo(pieza['nombre'], n, pieza['cantidad']),
                               'opciones': [dict(opcion)], 'a_escoger': False})
            continue
        grupo = de_opciones.get(pieza['grupo'])
        if grupo is None:
            grupo = de_opciones[pieza['grupo']] = {
                'copias': pieza['cantidad'], 'opciones': [], 'nombre': pieza['nombre']}
            grupos.append(grupo)
        elif grupo['copias'] != pieza['cantidad']:
            return [], f'fila {pieza["fila"]}: las opciones de un mismo grupo tienen que pedir la misma cantidad'
        grupo['opciones'].append(opcion)
    resultado = []
    for grupo in grupos:
        if 'copias' not in grupo:
            resultado.append(grupo)
            continue
        a_escoger = len(grupo['opciones']) > 1
        for n in range(1, grupo['copias'] + 1):
            resultado.append({'nombre': nombre_de_grupo(grupo['nombre'], n, grupo['copias'], a_escoger),
                              'opciones': [dict(o) for o in grupo['opciones']], 'a_escoger': a_escoger})
    return resultado, None


# ----------------------------------------------------------------------------------------------
# El nombre de un combo
# ----------------------------------------------------------------------------------------------

def tamanos_en(texto):
    """Los tamaños que nombra un texto, sin repetir y en orden: «CAMA FULL … KING» → ['full', 'king']."""
    vistos = []
    for m in re.finditer(r'\b(twin|full|queen|king)\b', limpio(texto)):
        if m.group(1) not in vistos:
            vistos.append(m.group(1))
    return vistos


def tamano_de_colchon(texto):
    """El tamaño de un colchón por su nombre. Además de Twin/Full/Queen/King, «4/6» es Full, «3/4» es Twin y una «Q» o
    una «K» sueltas son Queen y King. ``None`` si no dice cuál (o dice dos)."""
    claro = limpio(texto)
    tamanos = tamanos_en(claro)
    if not tamanos:
        for patron, tamano in ((r'\b4/6\b', 'full'), (r'\b3/4\b', 'twin'), (r'\bq\b', 'queen'), (r'\bk\b', 'king')):
            if re.search(patron, claro) and tamano not in tamanos:
                tamanos.append(tamano)
    return tamanos[0] if len(tamanos) == 1 else None


def tamano_de_cama(texto):
    tamanos = tamanos_en(texto)
    return tamanos[0] if len(tamanos) == 1 else None


def forma_de_marca(texto):
    """Para comparar marcas aunque estén mal escritas: solo letras, sin tildes y sin letras repetidas seguidas
    («DULCES SUEÑOS» y «DULCESUENOS» dan lo mismo)."""
    return re.sub(r'(.)\1+', r'\1', re.sub(r'[^a-z]', '', limpio(texto)))


_COLCHON = re.compile(r'^(?:(?P<n>\d+)\s*)?colch\w*\s*(?P<marca>.*)$')


def analizar_nombre(nombre):
    """Lee «COMBO <cama> + <colchón>». Devuelve ``{'ok', 'cama', 'colchon', 'tamano', 'tamanos', 'marca',
    'cantidad_colchones', 'problema'}``. ``ok`` es ``False`` si el nombre no tiene esa forma (``problema`` dice por
    qué). El tamaño sale de la parte de la cama."""
    original = _espacios(nombre)
    resultado = {'ok': False, 'cama': '', 'colchon': '', 'tamano': None, 'tamanos': [], 'marca': '',
                 'cantidad_colchones': 1, 'problema': None}
    claro = limpio(original)
    if not claro.startswith('combo'):
        resultado['problema'] = 'el nombre no empieza por «COMBO»'
        return resultado
    if '+' not in claro:
        resultado['problema'] = 'el nombre no tiene el «+» que separa la cama del colchón'
        return resultado
    antes, _mas, despues = original.rpartition('+')
    colchon = _COLCHON.match(limpio(despues))
    if not colchon:
        resultado['problema'] = 'después del «+» no dice «colchón»'
        return resultado
    cama = re.sub(r'^\s*combo\s+', '', antes, flags=re.IGNORECASE).strip()
    marca = ' '.join(p for p in limpio(colchon.group('marca')).split() if p not in TAMANOS)
    resultado.update({
        'cama': cama, 'colchon': _espacios(despues), 'marca': marca,
        'cantidad_colchones': int(colchon.group('n')) if colchon.group('n') else 1,
        'tamanos': tamanos_en(cama), 'tamano': tamano_de_cama(cama)})
    if not cama:
        resultado['problema'] = 'el nombre no dice cuál es la cama'
    elif not marca:
        resultado['problema'] = 'el nombre no dice la marca del colchón'
    else:
        resultado['ok'] = True
    return resultado


# --- Colores (para acotar candidatos cuando no hay código) -------------------------------------

_COLORES = (
    ('light grey', r'light gr[ae]y|ligth gr[ae]y|ligth gery|light gery|gris claro'),
    ('dark grey', r'dark gr[ae]y|charcoal gr[ae]y|gris oscuro'),
    ('black', r'black|blak|negr[oa]s?'),
    ('white', r'white|blanc[oa]s?|marfil'),
    ('beige', r'beige|crema|arena'),
    ('brown', r'brown|bronw|marr[oó]n|marron|cafe'),
    ('grey', r'gr[ae]y|gris'),
    ('pink', r'pink|rosad[oa]|rosa'),
    ('stone', r'stone'),
    ('ivory', r'ivory'),
)


def color_de(texto):
    """El color que dice un texto en inglés o en español, en una palabra canónica; ``None`` si no dice."""
    claro = limpio(texto)
    for canonico, patron in _COLORES:
        if re.search(rf'\b(?:{patron})\b', claro):
            return canonico
    return None


# --- La cama ------------------------------------------------------------------------------------

_PALABRAS_VACIAS = {
    'cama', 'camas', 'combo', 'color', 'de', 'con', 'tamano', 'sencillo', 'metal', 'y', 'el', 'la', 'en', 'para',
    'size', 'sku', 'box', 'spring', 'springs', 'base', 'cabecero', 'tipo', 'del', 'los', 'las',
}


def _fichas(texto):
    return re.findall(r'[a-z0-9]+', limpio(texto))


def _contiene(fichas, buscada):
    """¿``buscada`` (lista de fichas) aparece seguida dentro de ``fichas``?"""
    n = len(buscada)
    return bool(n) and any(fichas[i:i + n] == buscada for i in range(len(fichas) - n + 1))


def _alias_de_codigo(codigo):
    """Las formas en que un código puede aparecer escrito en un nombre: el código y, si termina en un tamaño
    (``XHT022-F-W-FULL``), el código sin él (``XHT022-F-W``)."""
    fichas = _fichas(codigo)
    alias = [fichas] if len(''.join(fichas)) >= 4 else []
    if len(fichas) > 1 and fichas[-1] in TAMANOS and len(''.join(fichas[:-1])) >= 4:
        alias.append(fichas[:-1])
    return alias


def _numeros(texto, minimo):
    return set(re.findall(rf'\d{{{minimo},}}', limpio(texto)))


def _resumen(pieza):
    return {k: pieza.get(k) for k in ('id', 'codigo', 'nombre', 'tamano', 'precio', 'existencias', 'origen')}


def _desempatar(candidatas, texto_original=''):
    """Si varios productos parecen el mismo: primero el que tiene el código escrito idéntico (mayúsculas incluidas)
    en el nombre del combo; después el que viene del inventario del sistema anterior. ``(elegida o None, regla)``."""
    exactas = [c for c in candidatas if c.get('codigo') and c['codigo'] in texto_original]
    if len(exactas) == 1:
        return exactas[0], 'tiene el código escrito igual que en el nombre del combo'
    pool = exactas or candidatas
    inventario = [c for c in pool if c.get('origen') == 'inventario']
    if len(inventario) == 1:
        return inventario[0], 'viene del inventario del sistema anterior (el que usaban los combos)'
    return None, ''


def _pieza(estado, elegida=None, opciones=(), motivo='', nota='', otras=()):
    return {'estado': estado, 'elegida': _resumen(elegida) if elegida else None,
            'opciones': [_resumen(o) for o in opciones], 'motivo': motivo, 'nota': nota,
            'otras': [_resumen(o) for o in otras]}


def resolver_cama(texto_cama, tamano, camas):
    """Busca la cama del combo entre ``camas`` (dicts con ``id, codigo, nombre, tamano, precio, existencias, origen``).

    1. El código que trae el nombre (aunque esté escrito con otros separadores o sin el sufijo de tamaño de la
       variante); si el nombre dice un tamaño, la cama tiene que ser de ese tamaño.
    2. Sin código: el nombre exacto de una cama.
    3. Si no, una SUPOSICIÓN (queda ``dudoso``): las camas que comparten el número largo del nombre o todas sus palabras
       (tamaño, color y modelo).
    """
    fichas = _fichas(texto_cama)
    por_codigo = []
    for cama in camas:
        for alias in _alias_de_codigo(cama.get('codigo') or ''):
            if _contiene(fichas, alias):
                por_codigo.append((cama, alias))
    # El código más largo manda: «8017-1003-K DG» le gana a «8017-1003-K».
    maximos = [(c, a) for c, a in por_codigo
               if not any(a != b and c['id'] != d['id'] and _contiene(b, a) for d, b in por_codigo)]
    candidatas = list({c['id']: c for c, _a in maximos}.values())
    if candidatas:
        parecidas = [c for c in candidatas if not (tamano and c.get('tamano') and c['tamano'] != tamano)]
        if not parecidas:
            return _pieza(DUDOSO, opciones=candidatas, motivo=(
                f'el código es de una cama {ETIQUETA_TAMANO.get(candidatas[0]["tamano"], "de otro tamaño")} y el combo '
                f'dice {ETIQUETA_TAMANO.get(tamano, "otro tamaño")}'))
        if len(parecidas) == 1:
            return _pieza(CLARO, parecidas[0], motivo='por su código')
        elegida, regla = _desempatar(parecidas, texto_cama)
        if elegida:
            return _pieza(CLARO, elegida, motivo='por su código', nota=f'hay otro con el mismo código: {regla}',
                          otras=[c for c in parecidas if c is not elegida])
        return _pieza(DUDOSO, opciones=parecidas, motivo='varias camas llevan ese código')
    exactas = [c for c in camas if limpio(c.get('nombre')) == limpio(texto_cama)]
    exactas = [c for c in exactas if not (tamano and c.get('tamano') and c['tamano'] != tamano)]
    if len(exactas) == 1:
        return _pieza(CLARO, exactas[0], motivo='por su nombre exacto')
    if len(exactas) > 1:
        elegida, regla = _desempatar(exactas, texto_cama)
        if elegida:
            return _pieza(CLARO, elegida, motivo='por su nombre exacto', nota=regla,
                          otras=[c for c in exactas if c is not elegida])
        return _pieza(DUDOSO, opciones=exactas, motivo='varias camas se llaman igual')
    return _suponer_cama(texto_cama, tamano, camas)


def _suponer_cama(texto_cama, tamano, camas):
    """Sin código ni nombre exacto: candidatas por el número largo o por todas las palabras. Siempre ``dudoso``."""
    numeros = _numeros(texto_cama, 4)
    color = color_de(texto_cama)
    palabras = {p for p in _fichas(texto_cama)
                if p not in _PALABRAS_VACIAS and p not in TAMANOS and not re.fullmatch(r'\d{1,3}', p)}
    candidatas = []
    for cama in camas:
        if tamano and cama.get('tamano') and cama['tamano'] != tamano:
            continue
        propias = f"{cama.get('codigo') or ''} {cama.get('nombre') or ''}"
        if color and color_de(propias) and color_de(propias) != color:
            continue
        comparte_numero = bool(numeros & _numeros(propias, 4))
        todas_las_palabras = bool(palabras) and palabras <= set(_fichas(propias))
        if comparte_numero or todas_las_palabras:
            candidatas.append(cama)
    if not candidatas:
        return _pieza(SIN_RESOLVER, motivo='no hay en el catálogo una cama con ese código ni con ese nombre')
    if len(candidatas) > 6:
        return _pieza(SIN_RESOLVER, motivo=f'hay {len(candidatas)} camas parecidas: son demasiadas para escoger')
    return _pieza(DUDOSO, opciones=candidatas, motivo='es una suposición: el nombre no trae un código que coincida')


# --- El colchón ---------------------------------------------------------------------------------

def resolver_colchon(marca, tamano, colchones):
    """Busca el colchón de la ``marca`` (tal como la escribe el combo) en ese ``tamano`` entre ``colchones`` (dicts con
    ``id, codigo, nombre, tamano, precio, existencias, origen``).

    Un solo producto: ``claro``. Si hay dos del mismo colchón y uno viene del inventario del sistema anterior (el que
    usaban los combos viejos), se usa ese y el otro queda anotado. Si no, ``dudoso``. Sin tamaño o sin colchón de esa
    marca y tamaño: ``sin_resolver``."""
    forma = forma_de_marca(marca)
    if not forma:
        return _pieza(SIN_RESOLVER, motivo='el nombre no dice la marca del colchón')
    de_la_marca = [c for c in colchones if forma in forma_de_marca(c.get('nombre') or '')]
    if not de_la_marca:
        return _pieza(SIN_RESOLVER, motivo=f'no hay un colchón de la marca «{_espacios(marca).upper()}» en el catálogo')
    if not tamano:
        return _pieza(SIN_RESOLVER, motivo='el nombre de la cama no dice el tamaño (Twin, Full, Queen o King)',
                      opciones=de_la_marca)
    del_tamano = [c for c in de_la_marca if c.get('tamano') == tamano]
    if not del_tamano:
        hay = [ETIQUETA_TAMANO[t] for t in TAMANOS if any(c.get('tamano') == t for c in de_la_marca)]
        return _pieza(SIN_RESOLVER, motivo=(
            f'no hay colchón «{_espacios(marca).upper()}» tamaño {ETIQUETA_TAMANO[tamano]}'
            + (f' (solo hay {", ".join(hay)})' if hay else '')))
    if len(del_tamano) == 1:
        return _pieza(CLARO, del_tamano[0], motivo='por marca y tamaño')
    elegida, regla = _desempatar(del_tamano)
    if elegida:
        return _pieza(CLARO, elegida, motivo='por marca y tamaño',
                      nota=f'hay otro colchón igual en el catálogo; se usa este porque {regla}',
                      otras=[c for c in del_tamano if c is not elegida])
    return _pieza(DUDOSO, opciones=del_tamano, motivo='hay más de un colchón de esa marca y tamaño')


# --- El combo entero ----------------------------------------------------------------------------

_PEOR = {CLARO: 0, DUDOSO: 1, SIN_RESOLVER: 2}


def resolver_combo(nombre, camas, colchones, precio=None):
    """Resuelve un combo por su nombre. Devuelve ``{'estado', 'motivo', 'analisis', 'cama', 'colchon',
    'cantidad_colchones', 'avisos_de_precio'}``; ``cama`` y ``colchon`` son los resultados de ``resolver_cama`` y
    ``resolver_colchon``. El estado del combo es el peor de sus piezas. ``avisos_de_precio`` dice si el precio del combo
    no tiene sentido frente a sus piezas (solo cuando las dos son claras)."""
    analisis = analizar_nombre(nombre)
    if not analisis['ok']:
        return {'estado': SIN_RESOLVER, 'motivo': analisis['problema'], 'analisis': analisis, 'cama': None,
                'colchon': None, 'cantidad_colchones': 1, 'avisos_de_precio': []}
    cama = resolver_cama(analisis['cama'], analisis['tamano'], camas)
    tamano = analisis['tamano'] or (cama['elegida'] or {}).get('tamano')
    colchon = resolver_colchon(analisis['marca'], tamano, colchones)
    estado = max((cama['estado'], colchon['estado']), key=_PEOR.get)
    motivos = []
    if cama['estado'] != CLARO:
        motivos.append(f'cama: {cama["motivo"]}')
    if colchon['estado'] != CLARO:
        motivos.append(f'colchón: {colchon["motivo"]}')
    return {'estado': estado, 'motivo': '; '.join(motivos), 'analisis': analisis, 'cama': cama, 'colchon': colchon,
            'cantidad_colchones': analisis['cantidad_colchones'],
            'avisos_de_precio': avisos_de_precio(precio, cama, colchon, analisis['cantidad_colchones'])}


def avisos_de_precio(precio, cama, colchon, cantidad_colchones=1):
    """Lo que no cuadra entre el precio del combo y el de sus piezas (solo con las dos piezas claras). Ver
    ``aviso_de_precio``."""
    if not precio or not cama['elegida'] or not colchon['elegida']:
        return []
    return aviso_de_precio(precio, [cama['elegida'].get('precio') or 0.0]
                           + [colchon['elegida'].get('precio') or 0.0] * cantidad_colchones)


def aviso_de_precio(precio, precios_de_piezas):
    """Avisa si el precio del combo no tiene sentido frente al de sus piezas: más barato que una sola de ellas, o más
    caro que todas juntas. Es para revisar el precio; no cambia nada. ``[]`` si todo cuadra."""
    if not precio or not precios_de_piezas:
        return []
    suma = round(sum(precios_de_piezas), 2)
    if precio < max(precios_de_piezas):
        return [f'el combo cuesta ${precio:,.2f}, menos que una sola de sus piezas (juntas suman ${suma:,.2f})']
    if precio > suma:
        return [f'el combo cuesta ${precio:,.2f}, más que sus piezas por separado (${suma:,.2f})']
    return []
