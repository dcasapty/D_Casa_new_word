"""Puerta B (2026-10-16): no se publica una factura de cliente si le falta el celular o el correo, o están mal escritos.

Ahí le llegan su factura y cómo ver sus puntos. Solo para el equipo y sin ``sudo`` (ver ``contacto.py``); no aplica a
las notas de crédito, a las facturas del sistema anterior (``dcasa_historica``) ni a nada que no sea una factura de
cliente. **«Pagar» nunca se bloquea:** el pago publica su propio asiento, no la factura.
"""
from odoo import models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        Partner = self.env['res.partner']
        if Partner._dcasa_exige_contacto():
            for factura in self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica):
                mensaje = Partner._dcasa_mensaje_faltantes(factura.partner_id, 'factura')
                if mensaje:
                    raise UserError(mensaje)
        return super()._post(soft=soft)
