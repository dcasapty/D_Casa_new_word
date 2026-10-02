"""888K: la foto real de la dueña (2026-10-02) reemplaza la miniatura sacada del Excel LTSC-07.

``cambiar_fotos_del_excel`` es idempotente y no pisa una foto subida a mano en Odoo.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_catalogo.catalogo import cambiar_fotos_del_excel


def migrate(cr, version):
    cambiar_fotos_del_excel(api.Environment(cr, SUPERUSER_ID, {}))
