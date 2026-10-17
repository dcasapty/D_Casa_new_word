"""«Enviar por correo» en el diálogo de la cotización del panel de Conversaciones (hereda; no edita ese módulo).

Las mismas reglas que «Enviar el PDF»: solo el equipo de ventas (``_para_panel``), solo cotizaciones abiertas del
cliente de la conversación, y la oportunidad pasa a «Propuesta» igual que al mandarla por el chat.

El estado del botón (``{puede, motivo, destino}``) se pide aparte, con ``correo_de_cotizacion``, en vez de agregarlo a
la respuesta de ``cotizaciones_abiertas``: esa respuesta es un contrato de dcasa_conversaciones (sus pruebas la comparan
entera) y este módulo no la cambia.
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_conversaciones.models.conversacion_panel import _entero
from odoo.exceptions import UserError

ANTIDOBLE_CLIC = timedelta(minutes=2)


class DcasaConversacionCorreo(models.Model):
    _inherit = 'dcasa.conversacion'

    @api.model
    def _dcasa_correo_estado_panel(self, conv, orden):
        """``{puede, motivo, destino}`` para el botón «Enviar por correo» (deshabilitado con su motivo)."""
        correo = self.env['dcasa.correo']
        apagado = correo._motivo_apagado()
        if apagado:
            return {'puede': False, 'motivo': apagado, 'destino': ''}
        if not conv.partner_id:
            return {'puede': False, 'motivo': self.env._('Esta conversación todavía no tiene un cliente.'),
                    'destino': ''}
        destino = correo._destino(orden) if orden else correo._destino(conv.partner_id)
        if not destino:
            cliente = (orden.partner_id if orden else conv.partner_id).display_name
            return {'puede': False, 'destino': '', 'motivo': self.env._(
                '%s no tiene correo. Escríbelo en su ficha o envíasela por WhatsApp.', cliente)}
        return {'puede': True, 'motivo': '', 'destino': destino.email_normalized or ''}

    @api.model
    def correo_de_cotizacion(self, conversacion_id, orden_id=None):
        """Si «Enviar por correo» se puede usar ahora: ``{puede, motivo, destino}`` (sin ``orden_id``, la cotización
        abierta más reciente del cliente)."""
        conv = self._para_panel(conversacion_id)
        orden = self.env['sale.order']
        if conv.partner_id:
            abiertas = self._cotizaciones_abiertas(conv)
            if orden_id is None:
                orden = abiertas[:1]
            else:
                orden_id = _entero(orden_id, 'orden_id', minimo=1)
                orden = abiertas.filtered(lambda o: o.id == orden_id)
        return self._dcasa_correo_estado_panel(conv, orden)

    @api.model
    def enviar_cotizacion_correo(self, conversacion_id, orden_id=None):
        """Manda por correo la cotización (con su PDF y la marca D'CASA). Sin ``orden_id``, la abierta más reciente."""
        conv = self._para_panel(conversacion_id, escritura=True)
        abiertas = self._cotizaciones_abiertas(conv)
        if orden_id is None:
            orden = abiertas[:1]
        else:
            orden_id = _entero(orden_id, 'orden_id', minimo=1)
            orden = abiertas.filtered(lambda o: o.id == orden_id)
        if not orden:
            raise UserError(self.env._(
                'Este cliente no tiene una cotización abierta. Crea una con productos del catálogo.'))
        hace_poco = fields.Datetime.now() - ANTIDOBLE_CLIC
        if self.env['dcasa.correo.envio'].sudo().search_count([
                ('tipo', '=', 'cotizacion'), ('order_id', '=', orden.id), ('create_date', '>=', hace_poco)], limit=1):
            raise UserError(self.env._('Ya se la enviaste por correo hace un momento.'))
        envio = orden._dcasa_correo_enviar_cotizacion()
        orden.message_post(body=self.env._('Enviada por correo por %(quien)s a %(correo)s.',
                                           quien=self.env.user.name, correo=envio.correo),
                           subtype_xmlid='mail.mt_note')
        conv._aviso(self.env._('%(quien)s envió la cotización %(n)s por correo.', quien=self.env.user.name,
                               n=orden.name))
        lead = orden.sudo().opportunity_id or conv._ligar_cotizacion(orden)
        if lead:
            lead._dcasa_al_cotizar(orden)
        return {'cotizacion': self._orden_como_dict(orden), 'correo': {'destino': envio.correo}}
