"""«Visítanos» pasa de un ancla de la portada (/#visitanos) a su propia página (/visitanos)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['website.menu'].search([('url', '=', '/#visitanos')]).write({'url': '/visitanos'})
