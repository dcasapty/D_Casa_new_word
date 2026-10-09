"""La «vista pública» del catálogo para el asistente: funciones PURAS.

Lo que un cliente puede saber de un producto es lo mismo que ve en la tienda: nombre, código,
precio «+ ITBMS», medidas, combo, foto y una etiqueta de existencias (``disponible``, ``pocas`` o
``agotado``). **Nunca** el número de existencias, costos ni nada de inventario interno.

La búsqueda es por palabras, sin importar mayúsculas, acentos ni plural («colchón queen» encuentra
«COLCHON First Class» en tamaño Queen; «camas» encuentra «CAMA Queen Grey»), porque así escribe la gente
en WhatsApp.
"""
import re
import unicodedata

DISPONIBLE, POCAS, AGOTADO = 'disponible', 'pocas', 'agotado'
ETIQUETAS_EXISTENCIAS = (DISPONIBLE, POCAS, AGOTADO)
UMBRAL_POCAS_POR_DEFECTO = 5.0
LIMITE_POR_DEFECTO = 5
LIMITE_MAXIMO = 8


def normalizar(texto):
    """Minúsculas y sin acentos: «Colchón» → «colchon»."""
    texto = unicodedata.normalize('NFKD', str(texto or '').lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


def raiz(palabra):
    """Singular sencillo: «colchones» → «colchon», «camas» → «cama», «sofás» → «sofa»."""
    if len(palabra) > 5 and palabra.endswith('ones'):
        return palabra[:-2]
    if len(palabra) > 3 and palabra.endswith('s'):
        return palabra[:-1]
    return palabra


def palabras(consulta):
    return [raiz(p) for p in re.findall(r'[a-z0-9]+', normalizar(consulta)) if len(p) > 1 or p.isdigit()]


def puntuar(consulta, nombre, codigo, extra=''):
    """0 si no coincide; mayor es mejor. TODAS las palabras de la consulta deben aparecer.

    ``nombre``: nombre del producto; ``codigo``: referencias (puede traer varias, separadas por
    espacio); ``extra``: categorías, tamaños y colores. El código exacto gana a todo.
    """
    buscadas = palabras(consulta)
    if not buscadas:
        return 0
    n_nombre, n_codigo, n_extra = normalizar(nombre), normalizar(codigo), normalizar(extra)
    if normalizar(consulta).strip() in n_codigo.split() and n_codigo.strip():
        return 1000
    puntos = 0
    for palabra in buscadas:
        if palabra in n_nombre:
            puntos += 10 + (5 if re.search(rf'\b{re.escape(palabra)}', n_nombre) else 0)
        elif palabra in n_codigo:
            puntos += 8
        elif palabra in n_extra:
            puntos += 4
        else:
            return 0
    return puntos


def limite_seguro(valor, defecto=LIMITE_POR_DEFECTO, maximo=LIMITE_MAXIMO):
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        return defecto
    return min(max(valor, 1), maximo)


def etiqueta_existencias(libres, umbral=UMBRAL_POCAS_POR_DEFECTO, controla_inventario=True):
    """``disponible`` / ``pocas`` / ``agotado`` a partir de las unidades libres. Nunca devuelve el número.

    Sin control de inventario no hay cifra que dar: se muestra como la tienda, «disponible».
    """
    if not controla_inventario:
        return DISPONIBLE
    libres = float(libres or 0)
    if libres <= 0:
        return AGOTADO
    if libres <= float(umbral if umbral is not None else UMBRAL_POCAS_POR_DEFECTO):
        return POCAS
    return DISPONIBLE


def precio_texto(precio, mas_itbms=True):
    """349.99 → «$349.99 + ITBMS» (el precio de D'CASA es sin ITBMS: el 7 % se suma en el carrito)."""
    base = f'${float(precio or 0):,.2f}'
    return f'{base} + ITBMS' if mas_itbms else base


def recortar(texto, largo=600):
    texto = re.sub(r'\s+', ' ', str(texto or '')).strip()
    return texto if len(texto) <= largo else texto[:largo - 1].rstrip() + '…'
