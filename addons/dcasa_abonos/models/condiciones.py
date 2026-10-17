"""La hoja «Condiciones de abono» sin base de datos: el texto inicial y cómo se lee lo que escribe la dueña.

El texto inicial es la hoja que la tienda ya entrega en papel («CONDICIONES DE ABONO — COPIA CLIENTE»), transcrita tal
cual, una condición por renglón y sin el número (la hoja las numera sola). La dueña lo cambia en Ajustes cuando quiera;
el sistema nunca calcula ni cobra las penalidades ni los recargos que la hoja menciona: solo las imprime.

Cada copia (cliente y empresa) tiene que caber en UNA hoja carta: ``ajuste_a_una_hoja`` calcula, antes de pintar, cuánto
hay que achicar la hoja cuando la factura trae muchos muebles o descripciones largas.
"""
import math
import re

TITULO_POR_DEFECTO = 'Condiciones de abono'

CONDICIONES_INICIALES = '\n'.join([
    'Deberá presentar la factura original para poder retirar la mercancía abonada.',
    'Los artículos abonados no podrán ser cambiados por ningún otro artículo.',
    'En el caso de no poder retirar su abono en el tiempo estipulado, la mercancía será colocada nuevamente a la '
    'venta y se le penalizará con el 10% del valor total de la factura.',
    'En caso que desista del abono realizado, deberá pagar una penalidad del 10% del monto total de la factura, y de '
    'haber un excedente se devolverá a través de una nota de crédito que deberá usarse en la misma sucursal donde se '
    'realizó el abono y en un periodo de tiempo no mayor a 3 meses.',
    'No podrá abonarse mercancía en ofertas, promociones o con descuentos.',
    'El atraso en el pago mayor al tiempo de vencimiento generará un recargo sobre el valor de la factura del 15%.',
    'No hay devolución de dinero.',
])

# «1)», «2. », «3 - », «4: » delante de un renglón: el número que alguien escribió a mano (la hoja numera sola). Con
# punto, guion o dos puntos tiene que seguir un espacio: «1.5 %» o «15-20 días» no son un número de renglón.
_NUMERO_DELANTE = re.compile(r'^\s*\d{1,2}\s*(?:\)\s*|[.:\-–]\s+)')
# Lo que queda colgando al quitar una referencia del proveedor: «()», «[]», « / » o « - » al final.
_RESTOS = (
    (re.compile(r'\(\s*\)|\[\s*\]'), ''),
    (re.compile(r'[ \t]{2,}'), ' '),
    (re.compile(r'[ \t]*[/\-–][ \t]*$', re.MULTILINE), ''),
    (re.compile(r'^[ \t]*[/\-–][ \t]*', re.MULTILINE), ''),
)
LARGO_MINIMO_REFERENCIA = 4


def lista_de_condiciones(texto):
    """Las condiciones, una por renglón: sin renglones vacíos ni el número que alguien les haya puesto delante."""
    condiciones = []
    for renglon in (texto or '').splitlines():
        limpio = _NUMERO_DELANTE.sub('', renglon).strip()
        if limpio:
            condiciones.append(limpio)
    return condiciones


def sin_referencia(descripcion, referencia):
    """La descripción para la copia del cliente, sin la referencia del proveedor si quedó escrita dentro.

    Solo se quita la referencia completa y suelta (no un pedazo de otra palabra) y solo si tiene al menos
    ``LARGO_MINIMO_REFERENCIA`` símbolos: una referencia «10» no le borra el «10» a «Sofá de 10 plazas».
    """
    texto = descripcion or ''
    referencia = (referencia or '').strip()
    if len(referencia) < LARGO_MINIMO_REFERENCIA or referencia.lower() not in texto.lower():
        return texto.strip()
    patron = re.compile(r'(?<![0-9A-Za-z])' + re.escape(referencia) + r'(?![0-9A-Za-z])', re.IGNORECASE)
    texto = patron.sub('', texto)
    for restos, cambio in _RESTOS:
        texto = restos.sub(cambio, texto)
    return '\n'.join(renglon.strip() for renglon in texto.splitlines()).strip()


# ---------------------------------------------------------------------------------------------------------------------
# Que cada copia quepa en UNA hoja
# ---------------------------------------------------------------------------------------------------------------------
# Medidas en puntos (1/72 de pulgada) tomadas del PDF real (wkhtmltopdf, hoja carta con el formato de las facturas:
# el cuerpo mide 616 entre los 38 mm de arriba y los 24 mm de abajo), redondeadas hacia el lado seguro. ``ALTO_FIJO``
# es todo lo que no son los muebles ni las condiciones: título y cliente (85), totales (60) y firmas (58). En la tabla
# achicada a la escala «e», el encabezado mide 8 + 10·e y cada fila 4 + 17·e, más 12·e por cada renglón de más
# (medido: una fila de un renglón mide 20 a escala 1, 15,4 a 0,7 y 13,4 a 0,6). Las letras por renglón son las de la
# columna más angosta (la copia de la empresa, que lleva además la referencia interna; caben unas 72) y en mayúsculas,
# que es como se escriben los muebles.
ALTO_DISPONIBLE = 600
ALTO_FIJO = 205
ALTO_ENCABEZADO_TABLA = (8, 10)
ALTO_FILA_MUEBLE = (4, 17)
ALTO_RENGLON_DE_MAS = 12
LETRAS_POR_RENGLON_MUEBLE = 60
ALTO_TITULO_CONDICIONES = 16
ALTO_ENTRE_CONDICIONES = 2
ALTO_RENGLON_CONDICION = 12
LETRAS_POR_RENGLON_CONDICION = 115
# Solo se achica la tabla de los muebles (las condiciones, los totales y las firmas siempre en su tamaño). Más chica que
# esto ya no se lee bien: en vez de achicarla más, la lista se corta y la última fila dice cuántos muebles más hay
# (están todos en la factura, que va en la hoja de al lado).
ESCALA_MINIMA = 0.6


def renglones(texto, letras):
    """Cuántos renglones ocupa un texto en una columna de ``letras`` letras (al menos uno)."""
    partes = (texto or '').split('\n')
    return max(1, sum(max(1, math.ceil(len(parte.strip()) / letras)) for parte in partes))


def alto_condiciones(condiciones):
    """Lo que ocupan las condiciones numeradas (con su título), en puntos."""
    if not condiciones:
        return 0
    return ALTO_TITULO_CONDICIONES + sum(
        ALTO_ENTRE_CONDICIONES + ALTO_RENGLON_CONDICION * renglones(condicion, LETRAS_POR_RENGLON_CONDICION)
        for condicion in condiciones)


def alto_tabla(descripciones, escala=1.0, fila_extra=False):
    """Lo que ocupa la tabla de los muebles achicada a ``escala`` (achicada caben más letras por renglón), con la fila
    de «y N muebles más» si va."""
    letras = LETRAS_POR_RENGLON_MUEBLE / escala
    fila = ALTO_FILA_MUEBLE[0] + ALTO_FILA_MUEBLE[1] * escala
    de_mas = ALTO_RENGLON_DE_MAS * escala
    filas = [fila + de_mas * (renglones(descripcion, letras) - 1) for descripcion in descripciones]
    if fila_extra:
        filas.append(fila)
    return ALTO_ENCABEZADO_TABLA[0] + ALTO_ENCABEZADO_TABLA[1] * escala + sum(filas)


def ajuste_a_una_hoja(descripciones, condiciones):
    """``(escala de la tabla de muebles, cuántos muebles se listan)`` para que una copia quepa en UNA hoja.

    Escala 1 si cabe tal cual; si no, la más grande con la que cabe (nunca menos de ``ESCALA_MINIMA``). Si ni así cabe,
    se listan los primeros muebles que quepan y la hoja agrega una fila con cuántos faltan. Si lo que no cabe son las
    condiciones mismas (un texto larguísimo), se listan todos los muebles a la escala mínima: es el texto el que hay que
    acortar en Ajustes.
    """
    descripciones = list(descripciones)
    total = len(descripciones)
    lugar = ALTO_DISPONIBLE - ALTO_FIJO - alto_condiciones(condiciones)
    minima = round(ESCALA_MINIMA * 100)
    for centesimas in range(100, minima - 1, -1):
        if alto_tabla(descripciones, centesimas / 100) <= lugar:
            return centesimas / 100, total
    for cuantos in range(total - 1, 0, -1):
        if alto_tabla(descripciones[:cuantos], ESCALA_MINIMA, fila_extra=True) <= lugar:
            return ESCALA_MINIMA, cuantos
    return ESCALA_MINIMA, total


# Con menos lugar que esto para la tabla, la dueña ve un aviso en Ajustes: con estas condiciones ya no caben ni cinco
# muebles sin achicar la lista.
MUEBLES_SIN_ACHICAR_MINIMOS = 5


def demasiado_largas(condiciones):
    """True si las condiciones dejan tan poco lugar que con pocos muebles la lista ya se achica o se corta."""
    lugar = ALTO_DISPONIBLE - ALTO_FIJO - alto_condiciones(condiciones)
    return lugar < alto_tabla([''] * MUEBLES_SIN_ACHICAR_MINIMOS)
