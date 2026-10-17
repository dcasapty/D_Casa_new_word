"""El correo sale por Resend en vez de SMTP, solo cuando el servidor tiene la clave (``RESEND_API_KEY``).

Sin clave, o si alguien configura un servidor de correo propio en Odoo, todo es exactamente como antes.
"""
from odoo import models


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    def _connect__(self, host=None, port=None, user=None, password=None, encryption=None,  # noqa: PLW3201
                   smtp_from=None, ssl_certificate=None, ssl_private_key=None, smtp_debug=False, mail_server_id=None,
                   allow_archived=False):
        correo = self.env['dcasa.correo'].sudo()
        if self._disable_send() or host or mail_server_id or not correo._hay_clave():
            return super()._connect__(
                host=host, port=port, user=user, password=password, encryption=encryption, smtp_from=smtp_from,
                ssl_certificate=ssl_certificate, ssl_private_key=ssl_private_key, smtp_debug=smtp_debug,
                mail_server_id=mail_server_id, allow_archived=allow_archived)
        return correo._sesion()
