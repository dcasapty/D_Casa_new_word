"""La factura y el correo: la plantilla D'CASA, los datos que lee y el envío que pide Brian."""
from odoo import fields, models
from odoo.exceptions import UserError

from .correo import centavos


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_mail_template(self):
        """Con la clave de Resend, la factura de cliente sale con la plantilla D'CASA (también desde «Enviar»)."""
        if self and all(m.move_type == 'out_invoice' for m in self) and self.env['dcasa.correo']._hay_clave():
            return self.env.ref('dcasa_correo.plantilla_factura')
        return super()._get_mail_template()

    # ------------------------------------------------------------------
    # Ningún correo de D'CASA crea un enlace con access_token
    # ------------------------------------------------------------------

    def _portal_ensure_token(self):
        if self.env.context.get('dcasa_correo_sin_token'):
            return self.access_token or ''
        return super()._portal_ensure_token()

    def _get_share_url(self, redirect=False, signup_partner=False, pid=None, share_token=True):
        if self.env.context.get('dcasa_correo_sin_token'):
            return super()._get_share_url(redirect=redirect, signup_partner=False, pid=pid, share_token=False)
        return super()._get_share_url(redirect=redirect, signup_partner=signup_partner, pid=pid,
                                      share_token=share_token)

    # ------------------------------------------------------------------
    # Lo que leen las plantillas
    # ------------------------------------------------------------------

    def _dcasa_correo_destino(self):
        """La ficha a la que le llega esta factura por correo (vacía si no tiene un correo bien escrito)."""
        self.ensure_one()
        return self.env['dcasa.correo']._destino(self)

    def _dcasa_correo_valores(self):
        """Asunto, titular y cifras del correo de la factura. Las cifras son las de ``_dcasa_estado_abono`` (la misma
        fuente que el papel y «Mi cuenta») y los puntos, los del libro de Socios. Solo lee."""
        self.ensure_one()
        correo = self.env['dcasa.correo']
        move = self.sudo()
        estado = move._dcasa_estado_abono()
        moneda = move.currency_id
        numero = move.name or ''
        con_saldo = moneda.compare_amounts(estado['saldo'], 0) > 0 and moneda.compare_amounts(estado['pagado'], 0) > 0
        pagada = move._dcasa_is_paid() and not con_saldo
        if con_saldo:
            asunto = self.env._('Recibimos tu abono · Factura %s', numero)
            titular = self.env._('RECIBIMOS TU ABONO')
        elif pagada:
            asunto = self.env._('Tu factura %s está pagada', numero)
            titular = self.env._('¡TU COMPRA ESTÁ PAGADA!')
        else:
            asunto = self.env._("Tu factura %s de D'CASA", numero)
            titular = self.env._('TU FACTURA')
        puntos_compra = sum(move.dcasa_compra_ids.filtered(lambda c: not c.anulada_en).mapped('puntos'))
        saldo_puntos = move.commercial_partner_id.dcasa_saldo or 0
        return {
            'numero': numero,
            'asunto': asunto,
            'titular': titular,
            'nombre': correo._primer_nombre(move.partner_id),
            'con_saldo': con_saldo,
            'pagada': pagada,
            'total': correo._monto(estado['total'], moneda),
            'pagado': correo._monto(estado['pagado'], moneda),
            'saldo': correo._monto(estado['saldo'], moneda),
            'vence': correo._fecha(estado['vence']),
            'vencido': bool(estado['vencido']),
            'abonos': [{'fecha': a['fecha'], 'monto': correo._monto(a['monto'], moneda)}
                       for a in estado['abonos'] if not a['es_reverso']],
            'puntos_compra': correo._puntos(puntos_compra) if puntos_compra > 0 else '',
            'puntos_saldo': correo._puntos(saldo_puntos) if saldo_puntos > 0 else '',
            'enlaces': correo._enlaces(),
        }

    # ------------------------------------------------------------------
    # Brian: «mándale la factura por correo»
    # ------------------------------------------------------------------

    def _dcasa_correo_enviar_factura(self):
        """Encola el correo de esta factura (PDF nuevo, con lo pagado hasta hoy) y despierta la cola.

        Lanza ``UserError`` con el mismo texto que ve la persona si los correos están apagados o el cliente no tiene
        un correo bien escrito."""
        self.ensure_one()
        self.check_access('read')
        correo = self.env['dcasa.correo']
        if self.move_type != 'out_invoice' or self.state != 'posted':
            raise UserError(self.env._('Solo se manda por correo una factura de cliente publicada.'))
        motivo = correo._motivo_apagado()
        if motivo:
            raise UserError(motivo)
        if not correo._destino(self):
            cliente = self.partner_id.display_name
            raise UserError(self.env._('%s no tiene correo. Escríbelo en su ficha o envíasela por WhatsApp.', cliente))
        saldo = self.amount_residual
        tipo = 'abono' if self.currency_id.compare_amounts(saldo, 0) > 0 and self._dcasa_pagos() else 'factura'
        minuto = fields.Datetime.now().strftime('%Y%m%d%H%M')
        Envio = self.env['dcasa.correo.envio'].sudo()
        envio = Envio._crear_si_no_existe({
            'tipo': tipo, 'huella': f'manual:{self.id}:{minuto}', 'saldo_centavos': centavos(saldo),
            'move_id': self.id, 'partner_id': self.commercial_partner_id.id,
        })
        if not envio:
            raise UserError(self.env._('Ya la mandaste por correo hace un momento.'))
        self.env.ref('dcasa_correo.ir_cron_dcasa_correo_cola').sudo()._trigger()
        return envio
