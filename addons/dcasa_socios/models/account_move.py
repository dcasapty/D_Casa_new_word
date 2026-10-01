from odoo import fields, models

from . import reglas as R


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_compra_ids = fields.One2many('dcasa.compra', 'move_id', string='Compra con puntos')

    # ------------------------------------------------------------------------
    # La factura pagada suma puntos — sin volver a teclear la venta
    # ------------------------------------------------------------------------

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        Compra = self.env['dcasa.compra'].sudo()
        for move in self.filtered(lambda m: m.move_type == 'out_invoice' and m.payment_state in ('paid', 'in_payment')):
            Compra._registrar_desde_factura(move)
        return res

    # ------------------------------------------------------------------------
    # Y si la factura se deshace, sus puntos también
    # ------------------------------------------------------------------------

    def _dcasa_anular_compras(self, motivo):
        compras = self.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)
        if compras:
            compras._anular(motivo, self.env.user.login)

    def button_draft(self):
        self.check_access('write')  # antes de anular puntos con sudo (método público por RPC)
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            move._dcasa_anular_compras(self.env._('La factura %s volvió a borrador.', move.name))
        return super().button_draft()

    def button_cancel(self):
        self.check_access('write')  # antes de anular puntos con sudo (método público por RPC)
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            move._dcasa_anular_compras(self.env._('Se canceló la factura %s.', move.name))
        return super().button_cancel()

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        # Nota de crédito sobre una factura que dio puntos: total anula, parcial descuenta.
        for nota in posted.filtered(lambda m: m.move_type == 'out_refund' and m.reversed_entry_id):
            original = nota.reversed_entry_id
            compras = original.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)
            if not compras:
                continue
            devuelto = R.a_centavos(abs(nota.amount_total_signed))
            if devuelto >= compras.monto_centavos:
                compras._anular(self.env._('Nota de crédito %s', nota.name), self.env.user.login)
            else:
                compras._devolucion_parcial(nota, self.env.user.login)
        return posted

    # ------------------------------------------------------------------------
    # Lo que se imprime en la factura
    # ------------------------------------------------------------------------

    def _dcasa_puntos_por_ganar(self):
        """Cuántos puntos da esta factura al pagarse (para imprimirlo antes del pago)."""
        self.ensure_one()
        monto = R.a_centavos(self.amount_total_signed)
        if self.move_type != 'out_invoice' or monto <= 0:
            return 0
        try:
            return R.puntos_de_compra(monto, R.cargar_reglas())
        except R.FaltaConfigurar:
            return 0
