"""Pedido LTSC-07: crea los productos nuevos del catálogo y, solo en staging, las existencias de prueba.

``cargar_catalogo`` solo crea los códigos que faltan (lo que ya está no se toca); el código del
pedido que ya existía (Y0300300) entra como producto aparte, Y0300300-LTSC07.
``aplicar_stock_prueba`` no hace nada si ``dcasa_catalogo.stock_prueba`` es 0 o vacío
(producción); en staging pone esas unidades solo a productos sin existencias ni movimientos.
Las dos son idempotentes.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_catalogo.catalogo import aplicar_stock_prueba, cargar_catalogo


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cargar_catalogo(env)
    aplicar_stock_prueba(env)
