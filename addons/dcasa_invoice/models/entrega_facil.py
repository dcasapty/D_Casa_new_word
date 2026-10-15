"""Reglas puras de la «nota de entrega fácil de leer» (sin base de datos, para probarlas solas).

La nota de entrega que va a bodega la leen personas con dislexia, autismo, otros idiomas o poca lectura: por eso cada
producto sale con su foto, su cantidad como número grande y como una fila de dibujitos (uno por pieza) y una casilla
para marcar. Aquí solo está lo que no depende de Odoo: cuántos dibujitos y cómo se escribe una cantidad.
"""

MAX_ICONOS = 10   # más piezas que esto no caben en una fila: se dibujan 10 y un «+» (el número grande dice el total)


def texto_cantidad(cantidad):
    """3.0 → '3'; 2.5 → '2.5' (sin ceros de más, igual que la nota de entrega de siempre)."""
    cantidad = cantidad or 0
    return str(int(cantidad)) if cantidad == int(cantidad) else f'{cantidad:g}'


def iconos_de_cantidad(cantidad):
    """(cuántos dibujitos, ¿hay más piezas de las dibujadas?).

    Uno por pieza hasta ``MAX_ICONOS``. Una cantidad con decimales (2.5 metros, por ejemplo) no se dibuja: no existe
    «media pieza» y un dibujito de más induciría al error; solo queda el número.
    """
    if not cantidad or cantidad < 0 or cantidad != int(cantidad):
        return 0, False
    piezas = int(cantidad)
    return min(piezas, MAX_ICONOS), piezas > MAX_ICONOS


def texto_unidad(es_la_unidad, nombre):
    """Lo que va junto al número: nada si la medida es la unidad de siempre (basta el número); si es otra (metros, por
    ejemplo), su nombre, para que «2» no se lea como dos piezas."""
    return '' if es_la_unidad else nombre


def total_de_piezas(lineas):
    """La suma de las piezas de las líneas. Una línea con decimales (metros, por ejemplo) no cuenta como piezas."""
    return sum(int(linea['cantidad']) for linea in lineas if iconos_de_cantidad(linea['cantidad']) != (0, False))
