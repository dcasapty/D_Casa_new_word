"""«Enviar» de la factura (el asistente de Odoo con la casilla de correo), con la marca D'CASA.

* Sin la clave de Resend: todo es nativo, como antes.
* Con la clave: plantilla y layout de D'CASA; el correo va marcado como factura o abono y sin ``access_token``.
* Con los correos a clientes apagados (o en staging): no se crea ningún correo; queda una nota en la factura y el
  asistente lo avisa.
* Si la factura ya tiene pagos, el PDF guardado se aparta (no se borra) para que salga uno nuevo con el saldo de hoy.
"""
from odoo import api, fields, models
from odoo.tools import format_date

from .correo import LAYOUT, correo_valido


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _dcasa_correo(self):
        return self.env['dcasa.correo'].sudo()

    @api.model
    def _get_mail_layout(self):
        if self._dcasa_correo()._hay_clave():
            return LAYOUT
        return super()._get_mail_layout()

    @api.model
    def _send_mail(self, move, mail_template, **kwargs):
        if self._dcasa_correo()._hay_clave():
            if move.move_type == 'out_invoice':
                tipo = 'abono' if move._dcasa_es_abono() else 'factura'
            else:
                tipo = 'documento'
            kwargs['mail_headers'] = {**(kwargs.get('mail_headers') or {}), 'X-Dcasa-Correo': tipo}
            move = move.with_context(dcasa_correo_sin_token=True)
        return super()._send_mail(move, mail_template, **kwargs)

    @api.model
    def _send_mails(self, moves_data):
        correo = self._dcasa_correo()
        if not correo._hay_clave():
            return super()._send_mails(moves_data)
        motivo = correo._motivo_apagado()
        if not motivo:
            return super()._send_mails(moves_data)
        nota = self.env._('No se envió por correo: %s', motivo[:1].lower() + motivo[1:])
        for move in moves_data:
            move.message_post(body=nota, message_type='comment', subtype_xmlid='mail.mt_note')
        return None

    @api.model
    def _get_alerts(self, moves, moves_data):
        alerts = super()._get_alerts(moves, moves_data)
        correo = self._dcasa_correo()
        if not correo._hay_clave():
            return alerts
        por_correo = moves.filtered(lambda m: 'email' in (moves_data[m].get('sending_methods') or ()))
        if not por_correo:
            return alerts
        motivo = correo._motivo_apagado()
        if motivo:
            alerts['dcasa_correo_apagado'] = {
                'level': 'warning',
                'message': self.env._('%s Si dejas marcada la casilla de correo, no se envía: queda una nota en la '
                                      'factura. Envíasela por WhatsApp.', motivo),
            }
        mal_escritos = por_correo.filtered(lambda m: m.partner_id.email and not correo_valido(m.partner_id.email))
        if mal_escritos:
            alerts['dcasa_correo_mal_escrito'] = {
                'level': 'warning',
                'message': self.env._('El correo de %s parece mal escrito: corrígelo en su ficha antes de enviar.',
                                      ', '.join(mal_escritos.partner_id.mapped('display_name'))),
            }
        return alerts

    @api.model
    def _dcasa_apartar_pdf_viejo(self, moves, custom_settings):
        """Si la factura ya tiene pagos, el PDF que Odoo guardó (sin esos pagos) se aparta y se arma uno nuevo.

        Se hace como el propio Odoo al «desprender» un PDF de factura: queda en la base con otro nombre."""
        apartados = []
        hoy = format_date(self.env, fields.Date.context_today(self), date_format='dd/MM/yyyy')
        for move in moves.filtered(lambda m: m.move_type == 'out_invoice' and m.invoice_pdf_report_id):
            if not move._dcasa_mostrar_pagos():
                continue
            viejo = move.invoice_pdf_report_id.sudo()
            nombre, punto, extension = (viejo.name or 'factura.pdf').rpartition('.')
            if not punto:
                nombre, extension = viejo.name or 'factura', 'pdf'
            viejo.write({'res_field': False, 'name': f'{nombre} (anterior {hoy}).{extension}'})
            move.invalidate_recordset(['invoice_pdf_report_id', 'invoice_pdf_report_file'])
            apartados.append(viejo.id)
        widget = custom_settings.get('mail_attachments_widget')
        if apartados and widget:
            custom_settings['mail_attachments_widget'] = [
                adjunto for adjunto in widget if adjunto.get('id') not in apartados]
        return apartados

    @api.model
    def _generate_and_send_invoices(self, moves, from_cron=False, allow_raising=True, allow_fallback_pdf=False,
                                    **custom_settings):
        if self._dcasa_correo()._hay_clave():
            self._dcasa_apartar_pdf_viejo(moves, custom_settings)
        return super()._generate_and_send_invoices(
            moves, from_cron=from_cron, allow_raising=allow_raising, allow_fallback_pdf=allow_fallback_pdf,
            **custom_settings)
