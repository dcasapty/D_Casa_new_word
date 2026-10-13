"""«No volver a preguntar en este dispositivo»: no vale para el personal.

Odoo deja marcar esa casilla en el paso del código y durante 90 días no vuelve a pedir el código en ese navegador.
Pedido de la dueña: el personal usa SIEMPRE el código de la app (Google Authenticator). Aquí el dispositivo de confianza
nunca se acepta para un usuario interno (la casilla tampoco se muestra: views/templates.xml). Clientes y socios no
cambian.
"""
from odoo import models


class AuthTotpDevice(models.Model):
    _inherit = 'auth_totp.device'

    def _check_credentials_for_uid(self, *, scope, key, uid):
        usuario = self.env['res.users'].sudo().browse(uid)
        if usuario.exists() and usuario._is_internal():
            return False
        return super()._check_credentials_for_uid(scope=scope, key=key, uid=uid)
