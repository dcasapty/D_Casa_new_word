"""Dirección real de la tienda (confirmada por la dueña, 2026-10-03).

Los datos de la empresa son ``noupdate``: en una base existente solo se cambia la
dirección si todavía es la vieja, para no pisar lo que alguien ya editó en Ajustes.
"""
from odoo import SUPERUSER_ID, api

VIEJA = 'Avenida Las Américas, Urbanización Santa Clara'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    empresa = env.ref('base.main_company', raise_if_not_found=False)
    if empresa and (empresa.street or '').strip() == VIEJA:
        empresa.write({
            'street': 'Frente al Parque Libertadores',
            'street2': 'Diagonal a la Discoteca Seven',
        })
