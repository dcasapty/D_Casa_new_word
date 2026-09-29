import re
from urllib.parse import quote

from odoo import fields, models

DEFAULT_WHATSAPP_MESSAGE = "Hola D'CASA, quiero información"


class Website(models.Model):
    _inherit = 'website'

    dcasa_whatsapp_number = fields.Char(
        string='WhatsApp de ventas',
        help='Número con código de país, p. ej. +507 6026-1919. Lo usan los botones de WhatsApp del sitio. '
             'Si está vacío se usa el teléfono de la empresa.',
    )

    def _dcasa_whatsapp_digits(self):
        self.ensure_one()
        number = self.dcasa_whatsapp_number or self.company_id.phone or ''
        return re.sub(r'\D', '', number)

    def _dcasa_whatsapp_url(self, message=None):
        """Link wa.me con mensaje precargado; '/contactus' si no hay número."""
        self.ensure_one()
        digits = self._dcasa_whatsapp_digits()
        if not digits:
            return '/contactus'
        return f'https://wa.me/{digits}?text={quote(message or DEFAULT_WHATSAPP_MESSAGE)}'
