"""Auditoría de UX: sitio en español, pagos que funcionan, entrega por cotizar y dirección de Panamá."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    api.Environment(cr, SUPERUSER_ID, {})['website']._dcasa_configurar_tienda()
