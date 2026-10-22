"""Al llegar el panel de Bodega: el «Retiro en tienda (…)» de la tienda web es retiro (después lo decide Gerencia)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['delivery.carrier']._dcasa_marcar_retiro_inicial()
