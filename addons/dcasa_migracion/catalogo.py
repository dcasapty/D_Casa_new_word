"""Carga de productos y existencias del sistema anterior (productos.csv + inventario.csv).

No hay un segundo cargador: se reusa el de «Inventario del sistema anterior» (``dcasa_catalogo``) con sus reglas
confirmadas por la dueña: la llave es el código; mismo código = mismo producto (se actualizan existencias y NO nombre
ni fotos); código nuevo = producto nuevo; sin código, la llave es el nombre; existencias negativas entran en 0 y se
listan para conteo físico; «COMBO … + COLCHÓN» entra sin publicar; es idempotente.

Lo único que agrega esta capa: por defecto el precio y el costo de un producto que YA existe no se tocan (el catálogo
nuevo puede tener precios que la dueña ajustó después); se actualizan solo si se pide.
"""
from odoo.addons.dcasa_catalogo.inventario_anterior import _buscar, cargar_inventario_anterior
from odoo.tools import float_round

from . import reglas


def cargar_catalogo(env, texto_productos, texto_inventario=None, actualizar_precios=False):
    """Lee los dos archivos y aplica la carga. Devuelve ``(resumen, avisos)``.

    ``resumen`` es el de ``cargar_inventario_anterior`` (listas de llaves por grupo) y ``avisos`` el de
    ``reglas.filas_catalogo``. Sin ``texto_inventario`` no se toca ninguna existencia. No hace commit.
    """
    filas, avisos = reglas.filas_catalogo(texto_productos, texto_inventario)
    # Aquí se venden unidades enteras (camas, no cuartos de cama): una existencia con decimales se redondea y se avisa,
    # porque Odoo la guardaría redondeada y cada carga la «corregiría» de nuevo.
    unidad = env.ref('uom.product_uom_unit')
    for fila in filas:
        if fila['a_la_mano'] is not None:
            entera = float_round(fila['a_la_mano'], precision_rounding=unidad.rounding)
            if entera != fila['a_la_mano']:
                avisos['decimales'].append((fila['llave'], fila['a_la_mano']))
                fila['a_la_mano'] = entera
    if not actualizar_precios:
        for fila in filas:
            if _buscar(env, fila):
                fila['precio'] = None
                fila['costo'] = None
    return cargar_inventario_anterior(env, filas), avisos
