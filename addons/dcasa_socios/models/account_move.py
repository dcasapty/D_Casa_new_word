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

    def _dcasa_socios_factura(self):
        """Lo que la factura impresa dice del programa. Solo lectura del libro y de las reglas.

        Devuelve un dict (o None si no hay nada que decir):
        socio, codigo, compra (la compra activa que dio puntos), por_ganar (si aún no se
        pagó), saldo (suma del libro), canjes (premios cobrados en el pedido), padrino_codigo
        (para invitar a quien no es socio), web (dominio público).
        """
        self.ensure_one()
        ficha = self.sudo().commercial_partner_id
        if ficha._is_public():
            return None
        compra = self.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)[:1]
        canjes = self.sudo().invoice_line_ids.sale_line_ids.dcasa_canje_id
        pedidos = self.sudo().invoice_line_ids.sale_line_ids.order_id
        padrino = ficha.dcasa_referido_por_id or pedidos.dcasa_referido_por_id[:1]
        return {
            'socio': bool(ficha.dcasa_socio_codigo),
            'codigo': ficha.dcasa_socio_codigo or '',
            'compra': compra,
            'por_ganar': 0 if compra else self._dcasa_puntos_por_ganar(),
            'saldo': ficha.dcasa_saldo,
            'canjes': canjes,
            'padrino_codigo': padrino.dcasa_socio_codigo or '',
            'web': self.company_id._dcasa_url_publica_corta(),
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _dcasa_es_premio(self):
        self.ensure_one()
        premio = self.env.ref('dcasa_socios.product_premio_canje', raise_if_not_found=False)
        return bool(self.sudo().sale_line_ids.dcasa_canje_id) or bool(premio and self.product_id == premio)

    def _dcasa_etiqueta(self):
        """La línea con que se cobró un premio se imprime identificada como tal."""
        if self._dcasa_es_premio():
            return "Premio Socios D'CASA"
        return super()._dcasa_etiqueta()

    def _dcasa_va_aparte(self):
        """El premio es un descuento, no un servicio que se cobra: se queda entre los muebles."""
        if self._dcasa_es_premio():
            return False
        return super()._dcasa_va_aparte()
