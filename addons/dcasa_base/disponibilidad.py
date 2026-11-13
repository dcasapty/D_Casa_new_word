"""Disponibilidad que se le dice al cliente: «disponible», «pocas» o «agotado». La regla vive solo aquí.

La usan Juan (el asistente de los clientes), la ficha de la tienda en línea, el catálogo de Meta y el Escáner: un mismo
mueble dice lo mismo en todos lados. **Nunca** se da el número de existencias, solo la etiqueta.

* ``agotado``: no queda ninguna unidad libre (0 o menos).
* ``pocas``: quedan entre 1 y ``umbral`` (5 por defecto; el «umbral de disponibilidad» del producto, si tiene uno,
  decisión 4 de PRIORIDADES del 2026-10-16).
* ``disponible``: más que eso, o el producto no controla inventario (un combo, un servicio): no hay cifra que dar y
  no se puede agotar.

Cuántas unidades cuentan como libres lo decide quien llama (Juan y la tienda: las libres de sus medidas; el Escáner:
lo que hay en bodega y tienda; Meta: el stock guardado en el producto). La etiqueta, siempre esta función.

Solo biblioteca estándar: se prueba sin base.
"""

DISPONIBLE, POCAS, AGOTADO = 'disponible', 'pocas', 'agotado'
ETIQUETAS_EXISTENCIAS = (DISPONIBLE, POCAS, AGOTADO)
UMBRAL_POCAS = 5.0


def etiqueta_existencias(libres, umbral=UMBRAL_POCAS, controla_inventario=True):
    """``disponible`` / ``pocas`` / ``agotado`` a partir de las unidades libres. Nunca devuelve el número.

    Sin control de inventario no hay cifra que dar: se dice «disponible», como en la tienda.
    """
    if not controla_inventario:
        return DISPONIBLE
    libres = float(libres or 0)
    if libres <= 0:
        return AGOTADO
    if libres <= float(umbral if umbral is not None else UMBRAL_POCAS):
        return POCAS
    return DISPONIBLE
