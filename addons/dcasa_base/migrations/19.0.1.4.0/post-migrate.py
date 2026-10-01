"""ITBMS: los precios de D'CASA son sin ITBMS y el 7 % se suma (decisión de la dueña, 2026-10-01).

La empresa pasa a «impuesto que se suma» y el ITBMS 7 % de ``l10n_pa`` vuelve a ser el de
venta por defecto. Los productos del catálogo los corrige ``dcasa_catalogo`` (19.0.1.2.0),
que también archiva el «ITBMS 7% incluido» si queda sin uso.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_base import _configurar_ventas_panama


def migrate(cr, version):
    _configurar_ventas_panama(api.Environment(cr, SUPERUSER_ID, {}))
