"""Garantía, cambios y términos propuestos en bases ya instaladas (solo campos vacíos, una vez)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    api.Environment(cr, SUPERUSER_ID, {})['res.company']._dcasa_poner_textos_iniciales()
