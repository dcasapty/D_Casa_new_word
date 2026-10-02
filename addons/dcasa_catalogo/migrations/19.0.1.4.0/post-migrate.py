"""Black Weekend: marca los 12 productos del pedido LTSC-07 que eligió la dueña (por código).

``marcar_black_weekend`` es idempotente: solo escribe lo que falte (marca, orden y, en 908K, la
variante negra como destacada). La ventana de la campaña (fechas, hora de Panamá) son parámetros
de website_dcasa; aquí no se toca ningún precio.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_catalogo.catalogo import marcar_black_weekend


def migrate(cr, version):
    marcar_black_weekend(api.Environment(cr, SUPERUSER_ID, {}))
