"""Nombres de productos: por dentro en MAYÚSCULAS, para el cliente en formato título. La regla vive solo aquí.

Decisión de la dueña (F5, 2026-10-22): «Lo que ve el cliente: "Cama Queen Tapizada", y solo por dentro queden en
MAYÚSCULAS». El nombre se GUARDA en mayúsculas (``nombre_en_mayusculas``, al crear o cambiar un producto) y las
pantallas internas lo muestran así; todo lo que ve el cliente (la tienda, Mi cuenta, Juan, los correos, los PDF que se
le entregan y el catálogo de Meta) pasa por ``nombre_para_cliente``:

* Cada palabra en mayúsculas queda con la primera letra mayúscula y el resto en minúscula, con sus tildes y su Ñ
  («BAÚL» → «Baúl», «MUÑECA» → «Muñeca»); los tamaños también («KING» → «King», «QUEEN» → «Queen»).
* Las preposiciones, artículos y conjunciones van en minúscula, salvo al empezar: «CAMA DE METAL CON BAÚL» →
  «Cama de Metal con Baúl».
* Se dejan como están: los códigos y todo lo que lleva números («DR-1024», «4/6», «3/4», «[DC-K7M4PX]»), la marca
  («D'CASA»), las siglas cortas («MDF», «PVC», «TV», «LED»…) y las palabras cortas con guion o barra que parecen
  código («A/C»). Las medidas pierden la mayúscula de la unidad: «160 X 200 CM» → «160 x 200 cm», «1.5M» → «1.5m».
* Una palabra que ya trae minúsculas no se toca (alguien la escribió así), y una línea escrita en minúsculas con alguna
  palabra en MAYÚSCULAS para resaltarla («Incluye luz NEÓN») se deja como está: la regla es para los nombres que
  vienen en mayúsculas.

Solo biblioteca estándar: se usa desde los modelos, las plantillas, Juan y el catálogo de Meta, y se prueba sin base.
"""
import re

MARCA = "D'CASA"
_MARCAS = frozenset({"D'CASA", 'D’CASA'})

# Siglas que se leen letra por letra o así se conocen. Las palabras sin vocales («MDF», «XL») ya se respetan solas.
SIGLAS = frozenset({'LED', 'USB', 'PU', 'UV', 'ABS', 'EVA', 'OLED', 'ITBMS', 'USA'})

# Preposiciones, artículos y conjunciones: en minúscula salvo al empezar.
MINUSCULAS = frozenset({
    'a', 'al', 'ante', 'bajo', 'con', 'contra', 'de', 'del', 'desde', 'e', 'el', 'en', 'entre', 'hacia', 'hasta',
    'la', 'las', 'lo', 'los', 'o', 'para', 'por', 'según', 'sin', 'sobre', 'tras', 'u', 'un', 'una', 'unas', 'unos',
    'y',
})

UNIDADES = frozenset({'cm', 'mm', 'm', 'mt', 'mts', 'kg', 'kgs', 'lb', 'lbs', 'pulg', 'cc', 'ml', 'lt', 'lts'})

_VOCALES = frozenset('AEIOUYÁÉÍÓÚÜ')
# Lo que va delante y detrás de una palabra: comillas, paréntesis, comas, puntos… (no los corchetes de un código).
_BORDES = re.compile(r'^([^\w\[]*)(.*?)([^\w\]]*)$', re.DOTALL)
_NUMERO = re.compile(r'^\d+(?:[.,]\d+)?$')
# «1.5M», «200CM», «160X200», «160X200CM»: medidas pegadas a su unidad.
_MEDIDA = re.compile(r'^\d+(?:[.,]\d+)?(?:[xX]\d+(?:[.,]\d+)?)*(?P<unidad>[A-Za-z]+)?$')
# Lo que, suelto, empieza otra parte del nombre: la palabra que sigue va con mayúscula aunque sea «de».
_SEPARADORES = frozenset({'-', '–', '—', '|', '·', '/', '+'})
_FIN_DE_PARTE = (':', '.', ';', '!', '?')


def nombre_en_mayusculas(texto):
    """Cómo se GUARDA: «Sofá  seccional milán» → «SOFÁ SECCIONAL MILÁN». Lo que no es texto vuelve igual."""
    if not isinstance(texto, str):
        return texto
    return ' '.join(texto.split()).upper()


def _letras(texto):
    return [c for c in texto if c.isalpha()]


def _es_mayuscula(nucleo):
    letras = _letras(nucleo)
    return bool(letras) and not any(c.islower() for c in letras)


def _es_marca(nucleo):
    return nucleo.upper() in _MARCAS


def _es_numerico(token):
    """«160», «1.5», «200CM», «2M»: lo que puede ir antes o después de una «X» de medidas."""
    nucleo = _BORDES.match(token).group(2) if token else ''
    return bool(nucleo) and nucleo[0].isdigit()


def _cuenta(nucleo):
    """Para decidir si la línea viene en mayúsculas: 'M' (palabra en mayúsculas), 'm' (con minúsculas) o None."""
    letras = _letras(nucleo)
    if len(letras) < 2 or any(c.isdigit() for c in nucleo) or '[' in nucleo or _es_marca(nucleo):
        return None
    if any(c.islower() for c in letras):
        return 'm'
    if nucleo in SIGLAS or not (set(letras) & _VOCALES):
        return None
    return 'M'


def _capital(palabra):
    """«BAÚL» → «Baúl», «ÑANDÚ» → «Ñandú»."""
    return palabra[:1].upper() + palabra[1:].lower()


def _palabra(nucleo, inicio, anterior, siguiente):
    """Una palabra en mayúsculas (sin lo que la rodea) tal como la ve el cliente."""
    if '[' in nucleo or ']' in nucleo or _es_marca(nucleo) or nucleo in SIGLAS:
        return nucleo
    if any(c.isdigit() for c in nucleo):
        medida = _MEDIDA.match(nucleo)
        if medida and (not medida.group('unidad') or medida.group('unidad').lower() in UNIDADES):
            return nucleo.lower()   # «1.5M» → «1.5m», «160X200CM» → «160x200cm»
        return nucleo               # un código: «DR-1024», «4/6», «2X»
    minuscula = nucleo.lower()
    if minuscula in UNIDADES and _es_numerico(anterior):
        return minuscula            # «200 CM» → «200 cm»
    if minuscula == 'x' and _es_numerico(anterior) and _es_numerico(siguiente):
        return 'x'                  # «160 X 200» → «160 x 200»
    if not inicio and minuscula in MINUSCULAS and not (len(nucleo) == 1 and anterior.lower() == 'en'):
        return minuscula            # «de», «con», «y»… («SOFÁ EN U» deja la U)
    if len(_letras(nucleo)) == 1 or not (set(_letras(nucleo)) & _VOCALES):
        return nucleo               # «L», «MDF», «XL»: letra suelta o sigla
    if re.search(r"[-/'’]", nucleo):
        partes = re.split(r"([-/'’])", nucleo)
        if all(len(p) <= 3 for p in partes[::2]):
            return nucleo           # «A/C», «TV-LED»: parece código
        return ''.join(p if i % 2 else _capital(p) for i, p in enumerate(partes))   # «SOFÁ-CAMA» → «Sofá-Cama»
    return _capital(nucleo)


def _linea_para_cliente(linea):
    partes = re.split(r'(\s+)', linea)
    tokens = [(i, p) for i, p in enumerate(partes) if p and not p.isspace()]
    cuentas = [_cuenta(_BORDES.match(p).group(2)) for _i, p in tokens]
    mayusculas, minusculas = cuentas.count('M'), cuentas.count('m')
    if not mayusculas or mayusculas < minusculas:
        return linea
    inicio = True
    for n, (i, token) in enumerate(tokens):
        antes, nucleo, despues = _BORDES.match(token).groups()
        anterior = tokens[n - 1][1] if n else ''
        siguiente = tokens[n + 1][1] if n + 1 < len(tokens) else ''
        if _es_mayuscula(nucleo):
            partes[i] = antes + _palabra(nucleo, inicio, anterior, siguiente) + despues
        if token in _SEPARADORES or (despues and despues.rstrip(')»"\'').endswith(_FIN_DE_PARTE)):
            inicio = True
        elif _letras(nucleo):
            inicio = False
    return ''.join(partes)


def nombre_para_cliente(texto):
    """Cómo lo VE el cliente: «CAMA DE METAL CON BAÚL QUEEN» → «Cama de Metal con Baúl Queen».

    Línea por línea (una descripción de varias líneas conserva sus saltos). Lo que no es texto vuelve igual.
    """
    if not isinstance(texto, str) or not texto:
        return texto
    return '\n'.join(_linea_para_cliente(linea) for linea in texto.split('\n'))
