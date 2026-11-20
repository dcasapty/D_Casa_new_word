"""Los ganchos de la comisión web en la factura. **Nunca hacen fallar un cobro ni una factura**: todo corre dentro de un
savepoint y con el error al registro; el barrido de cada noche anota lo que se haya quedado atrás."""
import logging

from odoo import models

from .venta import CONCURRENCIA

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _invoice_paid_hook(self):
        resultado = super()._invoice_paid_hook()
        Venta = self.env['dcasa.web.venta'].sudo()
        # Lo pendiente de OTROS se escribe aquí, fuera del ``try``: ``savepoint()`` lo vacía antes de abrirse y, si
        # chocara dentro, el gancho se tragaría un error que no es suyo y dejaría rota la transacción del cobro.
        self.env.flush_all()
        for move in self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica):
            try:
                with self.env.cr.savepoint():
                    Venta._registrar(move)
            except CONCURRENCIA:
                raise      # Odoo repite el cobro con una foto nueva de la base
            except Exception:  # noqa: BLE001 — un cobro nunca falla por la comisión
                _logger.exception('Comisión web: no se pudo anotar la factura %s', move.name)
        return resultado

    def _post(self, soft=True):
        publicados = super()._post(soft=soft)
        # Una nota de crédito de una venta del sitio resta en el libro en cuanto se publica.
        notas = publicados.filtered(lambda m: m.move_type == 'out_refund' and m.reversed_entry_id)
        if notas:
            self.env.flush_all()
        for nota in notas:
            try:
                with self.env.cr.savepoint():
                    self.env['dcasa.web.venta'].sudo().search([('move_id', '=', nota.reversed_entry_id.id)
                                                               ])._reconciliar()
            except CONCURRENCIA:
                raise
            except Exception:  # noqa: BLE001 — publicar una nota nunca falla por la comisión
                _logger.exception('Comisión web: no se pudo restar la nota %s', nota.name)
        return publicados

    def _dcasa_comision_al_dia(self, ventas=None):
        """Compara con la verdad las ventas del sitio de estas facturas (una factura vuelta a borrador, anulada o
        borrada ya no está cobrada: se reversa en el acto, sin esperar el barrido de la noche). Nunca falla."""
        ventas = self.env['dcasa.web.venta'].sudo().search([('move_id', 'in', self.ids)]) if ventas is None else ventas
        if not ventas:
            return
        self.env.flush_all()
        try:
            with self.env.cr.savepoint():
                ventas.invalidate_recordset()
                ventas._reconciliar()
        except CONCURRENCIA:
            raise
        except Exception:  # noqa: BLE001 — pasar una factura a borrador o anularla nunca falla por la comisión
            _logger.exception('Comisión web: no se pudo reversar lo anotado de %s', self.mapped('name'))

    def button_draft(self):
        resultado = super().button_draft()
        self._dcasa_comision_al_dia()
        return resultado

    def button_cancel(self):
        resultado = super().button_cancel()
        self._dcasa_comision_al_dia()
        return resultado

    def unlink(self):
        ventas = self.env['dcasa.web.venta'].sudo().search([('move_id', 'in', self.ids)])
        nombres = self.mapped('name')
        resultado = super().unlink()
        if ventas:
            self.env.flush_all()
            try:
                with self.env.cr.savepoint():
                    ventas.invalidate_recordset()
                    ventas._reconciliar()
            except CONCURRENCIA:
                raise
            except Exception:  # noqa: BLE001
                _logger.exception('Comisión web: no se pudo reversar lo anotado de las facturas borradas %s', nombres)
        return resultado
