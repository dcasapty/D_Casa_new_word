"""Auditoría de UX: nombres que distinguen cada mueble, medidas, combo y Muebles de TV."""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_catalogo.catalogo import actualizar_catalogo


def migrate(cr, version):
    actualizar_catalogo(api.Environment(cr, SUPERUSER_ID, {}))
