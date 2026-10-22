"""Comprobante de pago de la planilla (G4): el PDF con la marca y su envío por correo a cada colaborador.

* El PDF (``report/nomina_reportes.xml``) sale de cualquier planilla; si no está confirmada lleva la marca «BORRADOR».
* El correo solo se manda de una planilla **confirmada o pagada** y respeta el interruptor de los correos de D'CASA
  (``dcasa_correo``: sin clave de Resend, apagado, en staging o en un servidor que no dice que es producción, no sale
  nada y la pantalla dice por qué). Va a su correo personal (o, si no tiene, al de trabajo) con la cabecera
  ``X-Dcasa-Correo: nomina``: la política de ``dcasa_correo`` lo deja salir solo con el interruptor encendido.
* Quien no tiene correo bien escrito en su ficha queda en la lista del aviso: el comprobante se imprime.
"""
from markupsafe import Markup, escape

from odoo import fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_normalize, format_date

GRUPO = 'dcasa_nomina.group_nomina'
AZUL = '#1340B1'


class DcasaNominaLinea(models.Model):
    _inherit = 'dcasa.nomina.linea'

    def _correo_del_colaborador(self):
        """El correo personal del colaborador o, si no tiene uno bien escrito, el de trabajo. ``False`` si ninguno."""
        self.ensure_one()
        empleado = self.empleado_id.sudo()
        for correo in (empleado.private_email, empleado.work_email):
            normal = email_normalize(correo or '', strict=True)
            if normal:
                return normal
        return False

    def _motivo_correo_apagado(self):
        """Por qué no sale correo (el interruptor de ``dcasa_correo``), o ``''`` si sale o si ese módulo no está."""
        correo = self.env.get('dcasa.correo')
        return correo.sudo()._motivo_apagado() if correo is not None else ''

    def _cuerpo_correo_comprobante(self):
        self.ensure_one()
        planilla = self.planilla_id
        nombre = (self.empleado_id.name or '').split()[0] if self.empleado_id.name else ''
        neto = f'{self.currency_id.symbol or "$"}{self.neto:,.2f}'
        texto = self.env._(
            'Hola %(nombre)s: te mandamos tu comprobante de pago de la %(planilla)s (pago del %(pago)s). '
            'Lo que recibes: %(neto)s. El detalle va en el PDF adjunto.',
            nombre=nombre, planilla=planilla.name.lower() if planilla.name else '',
            pago=format_date(self.env, planilla.fecha_pago, date_format='dd/MM/yyyy'), neto=neto)
        empresa = self.company_id.name or ''
        return Markup(
            '<div style="font-family:Inter,Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#1B2233;'
            'max-width:560px;">'
            '<h1 style="margin:0 0 12px 0;font-family:Anton,Impact,Arial,sans-serif;font-weight:normal;font-size:24px;'
            'text-transform:uppercase;color:%s;">%s</h1><p style="margin:0 0 12px 0;">%s</p>'
            '<p style="margin:0;color:#6B6B6B;font-size:13px;">%s · %s</p></div>'
        ) % (AZUL, escape(self.env._('Tu comprobante de pago')), escape(texto), escape(empresa),
             escape(self.env._('Este correo es personal: no lo reenvíes.')))

    def action_enviar_comprobante(self):
        """Botón «Enviar» de la línea: su comprobante a su correo."""
        if not self.env.su and not self.env.user.has_group(GRUPO):
            raise AccessError(self.env._('Solo quien administra la nómina envía comprobantes de pago.'))
        self.check_access('write')
        return self._enviar_comprobantes()

    def _enviar_comprobantes(self):
        """Arma un correo por colaborador con su PDF y lo deja en la cola. Devuelve el aviso para la pantalla."""
        sin_confirmar = self.filtered(lambda ln: ln.planilla_id.estado not in ('confirmada', 'pagada'))
        if sin_confirmar:
            raise UserError(self.env._(
                'Solo se envía el comprobante de una planilla confirmada (antes, los números todavía pueden cambiar). '
                'Puedes imprimirlo con «Comprobante».'))
        motivo = self._motivo_correo_apagado()
        if motivo:
            raise UserError(self.env._(
                'No se envió ningún comprobante: %s Puedes imprimirlos con «Comprobante» y entregarlos en mano.',
                motivo))
        reporte = self.env.ref('dcasa_nomina.accion_comprobante_pago').sudo()
        correo_dcasa = self.env.get('dcasa.correo')
        remitente = (correo_dcasa.sudo()._remitente_formateado() if correo_dcasa is not None
                     else self.env.company.email_formatted)
        enviados, sin_correo = self.browse(), self.browse()
        for linea in self:
            destino = linea._correo_del_colaborador()
            if not destino:
                sin_correo |= linea
                continue
            pdf, _tipo = self.env['ir.actions.report'].sudo()._render_qweb_pdf(reporte.report_name, [linea.id])
            nombre_pdf = f'Comprobante - {linea.empleado_id.name} - {linea.planilla_id.name}.pdf'
            adjunto = self.env['ir.attachment'].sudo().create({
                'name': nombre_pdf, 'raw': pdf, 'mimetype': 'application/pdf',
                'res_model': linea._name, 'res_id': linea.id})
            self.env['mail.mail'].sudo().create({
                'subject': self.env._('Tu comprobante de pago · %s', linea.planilla_id.name),
                'body_html': linea._cuerpo_correo_comprobante(),
                'email_to': destino,
                'email_from': remitente,
                'headers': repr({'X-Dcasa-Correo': 'nomina'}),
                'attachment_ids': [(4, adjunto.id)],
                'auto_delete': True,
            })
            linea.sudo().write({'comprobante_enviado_el': fields.Datetime.now(), 'comprobante_enviado_a': destino})
            enviados |= linea
        for planilla in enviados.planilla_id:
            suyas = enviados.filtered(lambda ln, p=planilla: ln.planilla_id == p)
            nombres = ', '.join(suyas.mapped('empleado_id.name'))
            planilla.message_post(body=self.env._('Comprobantes de pago enviados por correo a: %s.', nombres))
        if enviados:
            cron = self.env.ref('mail.ir_cron_mail_scheduler_action', raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        partes = []
        if enviados:
            partes.append(self.env._('Se enviaron %s comprobante(s) por correo.', len(enviados)))
        if sin_correo:
            partes.append(self.env._(
                'Sin correo en su ficha (imprímelo y entrégalo en mano, o escribe su correo en su ficha): %s.',
                ', '.join(sin_correo.mapped('empleado_id.name'))))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': self.env._('Comprobantes de pago'), 'message': ' '.join(partes),
                       'type': 'warning' if sin_correo else 'success', 'sticky': bool(sin_correo),
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }


class DcasaNominaPlanilla(models.Model):
    _inherit = 'dcasa.nomina.planilla'

    def action_enviar_comprobantes(self):
        """«Enviar comprobantes por correo»: a cada colaborador de la planilla, su comprobante."""
        if not self.env.su and not self.env.user.has_group(GRUPO):
            raise AccessError(self.env._('Solo quien administra la nómina envía comprobantes de pago.'))
        self.check_access('write')
        return self.linea_ids._enviar_comprobantes()
