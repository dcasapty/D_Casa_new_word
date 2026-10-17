"""Decisión de la dueña (2026-10-17): al interior todavía no se entrega.

La barra de arriba, la portada, el pie y la descripción para Google dejan de prometer «Entrega a todo Panamá»: dicen
«Entregas en Panamá Oeste, Panamá y Colón». Las copias por sitio de la portada se corrigen igual (TEXTOS_CORREGIDOS);
la descripción de la portada la pone _dcasa_seo_portada en cada actualización.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['website']._dcasa_corregir_textos()
