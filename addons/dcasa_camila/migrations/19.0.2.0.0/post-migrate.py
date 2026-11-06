"""Camila etapa 2: las campañas que salieron en la etapa 1 (sin registro de a quién) cuentan para el tope de 15 días
POR CLIENTE. Se anotan los correos que hoy tienen permiso, con la fecha de envío de cada una (revisión adversarial
del 2026-11-06)."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    filas = env['dcasa.camila']._registrar_enviadas_sin_registro()
    _logger.info('DCASA_CAMILA migración: %s filas de registro para las campañas de la etapa 1', filas)
