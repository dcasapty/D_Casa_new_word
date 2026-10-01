"""ITBMS: los precios del Excel son sin ITBMS y el 7 % se suma (decisión de la dueña, 2026-10-01).

Los productos del catálogo cambian del «ITBMS 7% incluido» al ITBMS que se suma, sin tocar
su precio; la tienda muestra «$39.99 + ITBMS» y el impuesto incluido se archiva si queda
sin uso.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_catalogo.catalogo import pasar_a_itbms_que_se_suma


def migrate(cr, version):
    pasar_a_itbms_que_se_suma(api.Environment(cr, SUPERUSER_ID, {}))
