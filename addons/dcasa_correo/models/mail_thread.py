"""Lo que el layout D'CASA necesita al pintar un correo, y la marca del tipo de correo.

* ``_notify_by_email_prepare_rendering_context``: agrega ``dcasa`` (titular, enlaces, logo, WhatsApp, pie) solo cuando
  el correo usa ``dcasa_correo.layout_correo``.
* ``_notify_by_email_get_headers``: los envíos que abre D'CASA (p. ej. el asistente de la cotización) marcan su tipo
  con el contexto ``dcasa_correo_tipo``; solo una persona del equipo (o el sistema) puede marcarlo.
"""
from odoo import models

from . import politica
from .correo import LAYOUT

TIPOS_POR_CONTEXTO = ('cotizacion', 'factura', 'abono', 'documento')


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _notify_by_email_prepare_rendering_context(self, message, msg_vals=False, model_description=False,
                                                   force_email_company=False, force_email_lang=False,
                                                   force_record_name=False):
        contexto = super()._notify_by_email_prepare_rendering_context(
            message, msg_vals=msg_vals, model_description=model_description,
            force_email_company=force_email_company, force_email_lang=force_email_lang,
            force_record_name=force_record_name)
        valores = msg_vals or {}
        layout = valores['email_layout_xmlid'] if 'email_layout_xmlid' in valores else message.email_layout_xmlid
        if layout == LAYOUT:
            contexto['dcasa'] = self.env['dcasa.correo'].sudo()._contexto_layout(
                self[:1], message, contexto.get('company'))
        return contexto

    def _notify_by_email_get_headers(self, headers=None):
        headers = super()._notify_by_email_get_headers(headers=headers)
        tipo = self.env.context.get('dcasa_correo_tipo')
        if (tipo in TIPOS_POR_CONTEXTO and politica.CABECERA_CORREO not in headers
                and (self.env.su or self.env.user._is_internal())):
            headers[politica.CABECERA_CORREO] = tipo
        return headers
