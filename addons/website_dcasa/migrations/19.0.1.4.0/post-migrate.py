"""Auditoría v2.4 en bases ya instaladas.

- El número de WhatsApp sale de la descripción de Google (se configura en el sitio).
- El menú dice «Catálogo» en todos los idiomas (la traducción de Odoo decía «Tienda»).

Los ajustes van en ``noupdate`` en data/website_data.xml; aquí se aplican una sola vez.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    portada = env.ref('website.homepage_page', raise_if_not_found=False)
    if portada and portada.website_meta_description:
        portada.website_meta_description = portada.website_meta_description.replace(
            'Escríbenos por WhatsApp: +507 6026-1919.', 'Escríbenos por WhatsApp.')
    env['website']._dcasa_armar_menu_principal()
