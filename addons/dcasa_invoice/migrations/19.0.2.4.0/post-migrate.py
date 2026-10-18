"""El plazo del abono pasa de «un mes» a 30 días continuos (decisión de la gerencia A3, 2026-10-17).

Una base que ya tenga ``dcasa_invoice.abono_meses`` lo pasa a ``dcasa_invoice.abono_dias`` (1 mes → 30 días; 0 sigue
sin vencer) y lo borra: ver ``account.move._dcasa_migrar_plazo_abono``.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    api.Environment(cr, SUPERUSER_ID, {})['account.move']._dcasa_migrar_plazo_abono()
