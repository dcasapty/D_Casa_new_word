"""Los ganchos de la comisión web en la factura. **Nunca hacen fallar un cobro ni una factura**: todo corre dentro de un
savepoint y con el error al registro; el barrido de cada noche anota lo que se haya quedado atrás."""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _invoice_paid_hook(self):
        resultado = super()._invoice_paid_hook()
        Venta = self.env['dcasa.web.venta'].sudo()
        for move in self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica):
            try:
                with self.env.cr.savepoint():
                    Venta._registrar(move)
            except Exception:  # noqa: BLE001 — un cobro nunca falla por la comisión
                _logger.exception('Comisión web: no se pudo anotar la factura %s', move.name)
        return resultado

    def _post(self, soft=True):
        publicados = super()._post(soft=soft)
        # Una nota de crédito de una venta del sitio resta en el libro en cuanto se publica.
        for nota in publicados.filtered(lambda m: m.move_type == 'out_refund' and m.reversed_entry_id):
            try:
                with self.env.cr.savepoint():
                    self.env['dcasa.web.venta'].sudo().search([('move_id', '=', nota.reversed_entry_id.id)
                                                               ])._reconciliar()
            except Exception:  # noqa: BLE001 — publicar una nota nunca falla por la comisión
                _logger.exception('Comisión web: no se pudo restar la nota %s', nota.name)
        return publicados
