"""La cotización por correo: el botón «Enviar» de la venta y el que usan el panel de Conversaciones y Brian.

``action_quotation_sent`` (marcar como enviada) no se toca: lo usan Juan, el panel y WhatsApp.
"""
from odoo import models
from odoo.exceptions import UserError

from .correo import LAYOUT

INFORME_COTIZACION = 'sale.action_report_saleorder'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _dcasa_correo_exigir(self):
        """Lanza ``UserError`` (con el texto que ve la vendedora) si esta cotización no puede salir por correo."""
        correo = self.env['dcasa.correo']
        if correo._motivo_apagado():
            raise UserError(self.env._(
                'Los correos a clientes están apagados. Envíasela por WhatsApp o pídele a Gerencia que los encienda.'))
        for orden in self:
            if not correo._destino(orden):
                raise UserError(self.env._(
                    '%s no tiene correo. Escríbelo en su ficha o envíasela por WhatsApp.',
                    orden.partner_id.display_name))

    def action_quotation_send(self):
        """El botón nativo «Enviar»: sin la clave de Resend, igual que siempre. Con la clave, revisa el interruptor y
        el correo del cliente antes de abrir el asistente, que sale con el layout D'CASA y sin ``access_token``."""
        if not self.env['dcasa.correo']._hay_clave():
            return super().action_quotation_send()
        self._dcasa_correo_exigir()
        accion = super().action_quotation_send()
        if isinstance(accion, dict) and accion.get('res_model') == 'mail.compose.message':
            contexto = dict(accion.get('context') or {})
            contexto.update({
                'default_email_layout_xmlid': LAYOUT,
                'dcasa_correo_sin_token': True,
                'dcasa_correo_tipo': 'cotizacion' if all(o.state in ('draft', 'sent') for o in self) else 'documento',
            })
            accion['context'] = contexto
        return accion

    def _find_mail_template(self):
        self.ensure_one()
        if (self.env['dcasa.correo']._hay_clave() and not self.env.context.get('proforma')
                and self.state in ('draft', 'sent')):
            return self.env.ref('dcasa_correo.plantilla_cotizacion', raise_if_not_found=False) \
                or super()._find_mail_template()
        return super()._find_mail_template()

    def _portal_ensure_token(self):
        if self.env.context.get('dcasa_correo_sin_token'):
            return self.access_token or ''
        return super()._portal_ensure_token()

    def _get_share_url(self, redirect=False, signup_partner=False, pid=None, share_token=True):
        if self.env.context.get('dcasa_correo_sin_token'):
            return super()._get_share_url(redirect=redirect, signup_partner=False, pid=pid, share_token=False)
        return super()._get_share_url(redirect=redirect, signup_partner=signup_partner, pid=pid,
                                      share_token=share_token)

    def _dcasa_correo_valores(self):
        """Lo que lee la plantilla de la cotización."""
        self.ensure_one()
        correo = self.env['dcasa.correo']
        orden = self.sudo()
        return {
            'numero': orden.name or '',
            'nombre': correo._primer_nombre(orden.partner_id),
            'total': correo._monto(orden.amount_total, orden.currency_id),
            'con_itbms': orden.currency_id.compare_amounts(orden.amount_tax, 0) > 0,
            'valida_hasta': correo._fecha(orden.validity_date),
            'enlaces': correo._enlaces(),
        }

    def _dcasa_correo_enviar_cotizacion(self):
        """Manda esta cotización por correo con su PDF (panel de Conversaciones y Brian). La deja en el chatter, la
        cola de Odoo la manda por Resend; si estaba en borrador, pasa a «Enviada». Devuelve el envío registrado."""
        self.ensure_one()
        self.check_access('write')
        if self.state not in ('draft', 'sent'):
            raise UserError(self.env._('La venta %s ya está confirmada: lo que se manda por correo es la factura.',
                                       self.name))
        self._dcasa_correo_exigir()
        correo = self.env['dcasa.correo']
        destino = correo._destino(self)
        informe = self.env['ir.actions.report'].with_context(force_report_rendering=True)
        pdf, tipo = informe._render_qweb_pdf(INFORME_COTIZACION, [self.id])
        if tipo != 'pdf' or not pdf or not pdf.startswith(b'%PDF'):
            raise UserError(self.env._('No pude armar el PDF de la cotización. Ábrela en Odoo y descárgala.'))
        numero = (self.name or '').replace('/', '-')
        mensaje = correo._postear(self, self.env.ref('dcasa_correo.plantilla_cotizacion'), destino,
                                  [(f'Cotizacion {numero}.pdf', pdf)], tipo='cotizacion')
        envio = self.env['dcasa.correo.envio'].sudo().create({
            'tipo': 'cotizacion', 'huella': f'cotizacion:{self.id}:{mensaje.id}', 'order_id': self.id,
            'partner_id': self.partner_id.commercial_partner_id.id, 'estado': 'enviado', 'message_id': mensaje.id,
            'correo': destino.email_normalized,
        })
        if self.state == 'draft':
            self.action_quotation_sent()
        correo._disparar_cola()
        return envio
