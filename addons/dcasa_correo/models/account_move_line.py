"""El gancho del pago: «el botón pagado» le manda al cliente su factura (o su abono) por correo.

Cubre todas las rutas que concilian un cobro con una factura de cliente: el asistente «Pagar», ``registrar_pago`` de
Brian (``_create_payments``), la conciliación del banco y cada abono. Dentro de la transacción del pago solo se escribe
la fila de la cola (``dcasa.correo.envio``) y se despierta el cron: ni HTTP ni PDF. Todo va en un savepoint: si algo
falla, el pago sigue igual y queda el error en el log (mismo patrón que la comisión de vendedores).
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)
CLAVE = 'dcasa_correo_antes'


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _reconcile_pre_hook(self):
        data = super()._reconcile_pre_hook()
        if self.env.context.get('dcasa_sin_correo_auto'):
            return data
        try:   # solo lee (sin savepoint: no adelanta ninguna escritura del pago)
            facturas = self.move_id.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
            data[CLAVE] = {m.id: m.amount_residual for m in facturas}
        except Exception:  # noqa: BLE001 - el correo nunca hace fallar un pago
            _logger.exception('DCASA_CORREO no se pudo leer el saldo antes del pago')
        return data

    def _reconcile_post_hook(self, data):
        res = super()._reconcile_post_hook(data)   # primero lo de Odoo (y los puntos de Socios)
        antes = data.get(CLAVE)
        if antes and not self.env.context.get('dcasa_sin_correo_auto'):
            try:
                with self.env.cr.savepoint():
                    self.env['dcasa.correo.envio'].sudo()._encolar_pagos(antes, self)
            except Exception:  # noqa: BLE001 - el correo nunca hace fallar un pago
                _logger.exception('DCASA_CORREO no se pudo encolar el correo del pago')
        return res
