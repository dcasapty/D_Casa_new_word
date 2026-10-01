"""Auditoría de UX: impuesto de venta, formas de cobro e interfaz en español en bases ya instaladas."""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_base import _configurar_interfaz, _configurar_ventas_panama


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _configurar_ventas_panama(env)
    _configurar_interfaz(env)
