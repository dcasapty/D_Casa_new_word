"""Cantidades enteras y formato de Panamá en bases ya instaladas."""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_base import _configurar_interfaz


def migrate(cr, version):
    _configurar_interfaz(api.Environment(cr, SUPERUSER_ID, {}))
