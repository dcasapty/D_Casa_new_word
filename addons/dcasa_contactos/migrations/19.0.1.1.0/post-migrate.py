"""Una sola vez: los fijos de 7 números guardados en «Celular» pasan a «Teléfono fijo» (models/mover_fijos.py)."""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_contactos.models.mover_fijos import pasar_fijos_del_celular


def migrate(cr, version):
    pasar_fijos_del_celular(api.Environment(cr, SUPERUSER_ID, {}))
