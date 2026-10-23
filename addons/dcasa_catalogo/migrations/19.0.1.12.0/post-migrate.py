"""Los precios en combo que aprobó la dueña (2026-10-23): Imperial Full, Imperial Twin, Dulces Sueños Queen y
First Class King (ver ``PRECIOS_COMBO_APROBADOS`` en models/combo_armable.py). Solo donde el colchón sigue a su precio
normal y Gerencia todavía no puso uno; lo que no se cargó queda dicho en el registro para que Gerencia lo ponga a mano.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    resultado = env['product.product']._dcasa_cargar_precios_combo_aprobados()
    _logger.warning('Precios en combo aprobados por la dueña: %s', resultado)
