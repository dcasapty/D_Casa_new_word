"""Tafi y Crediviva, las financieras que le pagan a la tienda por el cliente (decisión de la gerencia C1, 2026-10-17).

Se crean una sola vez y sin pisar lo que exista (``dcasa_base.crear_diarios_financiamiento``). La cuenta contable de
cada una la revisa la contadora.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_base import crear_diarios_financiamiento


def migrate(cr, version):
    crear_diarios_financiamiento(api.Environment(cr, SUPERUSER_ID, {}))
