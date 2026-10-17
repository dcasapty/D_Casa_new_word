"""Decisión de la dueña (2026-10-17): no hay pago contra entrega y las entregas son por zona.

«Pago al recibir o en tienda» pasa a llamarse «Pago en la tienda» con su mensaje nuevo (models/tienda.py), y las
copias por sitio de la portada dejan de prometer «pagas al recibir» y «llegamos a todo el país».
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['website']._dcasa_pagos()
    env['website']._dcasa_corregir_textos()
