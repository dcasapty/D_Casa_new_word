import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def action_create_payments(self):
        """Al terminar el asistente de «Pagar»: si la factura de un cliente quedó pagada por completo o en abono
        (algo pagado y algo por pagar), ofrece el cuadro pequeño «Imprimir documentos». En un abono la factura
        sale como ABONO con su saldo y la nota de entrega viene sin marcar (se imprime al terminar de pagar).

        Solo es el botón del asistente (la persona frente a la pantalla). Los cobros por código (Brian, Juan,
        integraciones) llaman a ``_create_payments`` y no pasan por aquí. Desde la factura Odoo pone
        ``dont_redirect_to_payments`` (el asistente se cierra y se queda en la factura): ahí también se ofrece.
        Si el interruptor de la empresa está apagado, todo es como antes. El pago y sus asientos son los de Odoo:
        aquí solo se ofrece imprimir. Un fallo del ofrecimiento nunca deshace ni estorba el pago.
        """
        accion = super().action_create_payments()
        if self.env.context.get('dcasa_sin_oferta_impresion'):
            return accion
        try:
            with self.env.cr.savepoint():
                oferta = self._dcasa_oferta_impresion(accion)
        except Exception:  # noqa: BLE001 - el pago ya está hecho: lo demás no puede estorbarlo
            _logger.exception('DCASA_PAQUETE no se pudo ofrecer imprimir los documentos tras el pago')
            return accion
        return oferta or accion

    def _dcasa_oferta_impresion(self, accion_pago):
        """La acción del cuadro «Imprimir documentos» si corresponde ofrecerlo; si no, ``None``."""
        self.ensure_one()
        if not self.company_id.dcasa_ofrecer_impresion_pago:
            return None
        # Pagadas por completo o en abono: cada abono también lleva su papel.
        facturas = self.line_ids.move_id.filtered(
            lambda factura: factura.move_type == 'out_invoice' and factura.state == 'posted'
            and (factura._dcasa_is_paid() or factura._dcasa_es_abono()))
        if not facturas:
            return None
        # Con ``dont_redirect_to_payments`` Odoo no devuelve acción: al cerrar el cuadro se queda en la factura.
        accion_pago = accion_pago if isinstance(accion_pago, dict) else {}
        if accion_pago.get('res_id'):
            ids_pagos = [accion_pago['res_id']]
        else:
            ids_pagos = [id_ for _campo, _op, ids in accion_pago.get('domain', []) for id_ in ids]
        return self.env['dcasa.impresion.paquete']._accion_dialogo(
            facturas, self.env['account.payment'].browse(ids_pagos), tras_pago=True)
