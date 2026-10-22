"""Favicon del sitio: estrictamente el logo (pedido de la dueña, 2026-10-22; scripts/iconos_de_la_marca.py).

``data/website_data.xml`` es ``noupdate``: en una base que ya tenía el módulo, el favicon nuevo se pone aquí una vez.
"""
import base64

from odoo import SUPERUSER_ID, api
from odoo.tools.misc import file_open


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    website = env.ref('website.default_website', raise_if_not_found=False)
    if website:
        with file_open('website_dcasa/static/src/img/favicon.png', 'rb') as archivo:
            website.favicon = base64.b64encode(archivo.read())
