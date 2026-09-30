"""Menú corto (Catálogo · Socios D'CASA · Visítanos) en bases ya instaladas."""
from odoo import SUPERUSER_ID, api

MENUS_VIEJOS = ['menu_salas', 'menu_recamaras', 'menu_colchones', 'menu_comedores', 'menu_socios']


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in MENUS_VIEJOS:
        menu = env.ref(f'website_dcasa.{xmlid}', raise_if_not_found=False)
        if menu:
            menu.unlink()
    env['website']._dcasa_armar_menu_principal()
