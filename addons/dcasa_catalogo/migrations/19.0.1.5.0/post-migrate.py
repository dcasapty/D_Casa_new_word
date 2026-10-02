"""HK-BF-022-N-K-1-W pasa a «Cama tapizada Queen – blanco» (la dueña, 2026-10-02).

``corregir_nombres`` es idempotente y respeta un nombre que la dueña ya haya cambiado en Odoo.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_catalogo.catalogo import corregir_nombres


def migrate(cr, version):
    corregir_nombres(api.Environment(cr, SUPERUSER_ID, {}))
