"""Sitio v2.1 en bases que ya tenían el módulo: favicon de D'CASA y cabecera fija.

Van en ``noupdate`` en ``data/website_data.xml`` (para respetar lo que se cambie desde el
editor), así que en una base existente se aplican aquí una sola vez.
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
    estandar = env.ref('website.header_visibility_standard', raise_if_not_found=False)
    fija = env.ref('website.header_visibility_fixed', raise_if_not_found=False)
    if estandar and fija:
        estandar.active = False
        fija.active = True
