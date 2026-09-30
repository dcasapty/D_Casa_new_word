"""Formato de números de Panamá (punto decimal) en bases ya instaladas."""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_base import _formato_panama


def migrate(cr, version):
    _formato_panama(api.Environment(cr, SUPERUSER_ID, {}))
