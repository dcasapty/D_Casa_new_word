"""Los pedidos de la página web entran sin vendedora (decisión de la dueña, 2026-10-17; models/pedido_web.py).

Vacía UNA vez el «Vendedor» de cada sitio web (en una base nueva Odoo pone al administrador): así los pedidos de la
web quedan sin vendedora y los ven todas. Si después un administrador lo vuelve a poner, se respeta.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sitios = env['website'].search([('salesperson_id', '!=', False)])
    if sitios:
        _logger.info("D'CASA pedidos web: se vacía el «Vendedor» de %s sitio(s) (antes, usuario id %s).",
                     len(sitios), sitios.mapped('salesperson_id').ids)
        sitios.salesperson_id = False
