"""Inventario del sistema anterior (capturas del 2026-10-02): existencias, precios y costos por
código; productos nuevos para los códigos que no estaban. ``cargar_inventario_anterior`` es
idempotente y no toca nombres ni fotos de lo que ya existía.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_catalogo.inventario_anterior import cargar_inventario_anterior, leer_inventario_anterior


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cargar_inventario_anterior(env, leer_inventario_anterior())
