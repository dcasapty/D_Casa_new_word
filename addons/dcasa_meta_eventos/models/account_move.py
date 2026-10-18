"""Compras pagadas hacia la cola de Meta (Purchase de la Conversions API).

El cobro manda: en ``_invoice_paid_hook`` solo se INSERTA una fila, dentro de un savepoint, y cualquier error queda en
el registro sin relanzarse (el mismo patrón de dcasa_socios/models/account_move_vend.py). Nunca hay HTTP dentro de la
transacción del cobro: el envío lo hace un cron después. Un pago parcial no llama al enganche (Odoo lo llama cuando la
factura queda pagada o «en proceso de pago»).
"""
import logging
from collections import OrderedDict

from odoo import models

_logger = logging.getLogger(__name__)

TIPOS_PRODUCTO = ('consu', 'combo')  # sin servicios, descuentos, anticipos ni envíos


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        for move in self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica
                                  and m.payment_state in ('paid', 'in_payment')):
            try:
                # Meta nunca hace fallar un cobro: si algo se tuerce, el error queda en el registro.
                with self.env.cr.savepoint():
                    self.env['dcasa.meta.evento'].sudo()._dcasa_encolar_compra(move)
            except Exception:
                _logger.exception('Meta: no se pudo encolar la compra de la factura %s', move.id)
        return res

    def _dcasa_meta_cancelar(self, motivo):
        try:
            with self.env.cr.savepoint():
                self.env['dcasa.meta.evento']._dcasa_cancelar_pendientes(self, motivo)
        except Exception:
            _logger.exception('Meta: no se pudo cancelar lo pendiente de las facturas %s', self.ids)

    def button_draft(self):
        self.check_access('write')  # antes de tocar la cola con sudo (método público por RPC)
        self.filtered(lambda m: m.move_type == 'out_invoice')._dcasa_meta_cancelar(
            self.env._('La factura volvió a borrador'))
        return super().button_draft()

    def button_cancel(self):
        self.check_access('write')
        self.filtered(lambda m: m.move_type == 'out_invoice')._dcasa_meta_cancelar(
            self.env._('Se canceló la factura'))
        return super().button_cancel()

    # ------------------------------------------------------------------
    # Lo que se reporta de la factura
    # ------------------------------------------------------------------

    def _dcasa_meta_pedido_web(self):
        """El pedido de la tienda en línea de esta factura (``sale.order`` con sitio web), o vacío."""
        self.ensure_one()
        return self.sudo().invoice_line_ids.sale_line_ids.order_id.filtered('website_id')[:1]

    def _dcasa_meta_custom_data(self):
        """``custom_data`` del Purchase: valor SIN ITBMS (criterio contable vigente) y los productos vendibles.

        ``content_ids`` = id de la variante (``product.product``), el mismo del feed y del píxel (contrato 2.1).
        """
        self.ensure_one()
        moneda = self.currency_id
        productos = OrderedDict()
        for linea in self.sudo().invoice_line_ids:
            producto = linea.product_id
            if (linea.display_type != 'product' or not producto or producto.type not in TIPOS_PRODUCTO
                    or linea.is_downpayment or linea.quantity <= 0):
                continue
            dato = productos.setdefault(producto.id, {'cantidad': 0.0, 'subtotal': 0.0})
            dato['cantidad'] += linea.quantity
            dato['subtotal'] += linea.price_subtotal
        contents = []
        for producto_id, dato in productos.items():
            cantidad = dato['cantidad']
            contents.append({
                'id': str(producto_id),
                'quantity': int(cantidad) if float(cantidad).is_integer() else cantidad,
                'item_price': moneda.round(dato['subtotal'] / cantidad),
            })
        return {
            'currency': moneda.name,
            'value': moneda.round(self.amount_untaxed),
            'content_type': 'product',
            'content_ids': [c['id'] for c in contents],
            'contents': contents,
            'num_items': int(sum(dato['cantidad'] for dato in productos.values())),
            'order_id': self.name,
        }
