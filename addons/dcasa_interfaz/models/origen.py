"""De dónde salió una cotización o una factura (pedido de la dueña, 2026-11-03): «las facturas creadas por Juan
deberían, en el Inicio o en todo lado, decir que son por el chatbot; si viene de la web, también tiene que decirlo».

* **Web:** el pedido nació en la tienda en línea (``website_id``).
* **Chatbot:** la armó Juan, el asistente de los clientes (``dcasa_conversaciones`` agrega ese caso: su usuario técnico
  es quien la creó).
* **Vendedora:** todo lo demás (Ventas, el chat de Conversaciones, el Punto de Venta).

La factura hereda el origen de su pedido; si junta pedidos de varios orígenes, gana el del chatbot y después la web (lo
que se quiere medir). Una factura sin pedido (hecha a mano en Contabilidad) es de una vendedora.
"""
from odoo import api, fields, models

ORIGENES = [('chatbot', 'Chatbot'), ('web', 'Web'), ('vendedora', 'Vendedora')]
PRIORIDAD = ('chatbot', 'web', 'vendedora')


class SaleOrderOrigen(models.Model):
    _inherit = 'sale.order'

    dcasa_origen = fields.Selection(
        ORIGENES, string='Origen', compute='_compute_dcasa_origen', store=True, index=True, copy=False,
        help='De dónde salió: del chatbot (la armó Juan), de la página web o de una vendedora.')

    @api.depends('website_id', 'create_uid')
    def _compute_dcasa_origen(self):
        for orden in self:
            orden.dcasa_origen = 'web' if orden.website_id else 'vendedora'


class AccountMoveOrigen(models.Model):
    _inherit = 'account.move'

    dcasa_origen = fields.Selection(
        ORIGENES, string='Origen', compute='_compute_dcasa_origen', store=True, index=True, copy=False,
        help='El de su pedido: del chatbot (la cotización la armó Juan), de la página web o de una vendedora.')

    @api.depends('invoice_line_ids.sale_line_ids.order_id.dcasa_origen')
    def _compute_dcasa_origen(self):
        for factura in self:
            if not factura.is_sale_document(include_receipts=True):
                factura.dcasa_origen = False
                continue
            origenes = set(factura.invoice_line_ids.sale_line_ids.order_id.mapped('dcasa_origen'))
            factura.dcasa_origen = next((o for o in PRIORIDAD if o in origenes), 'vendedora')
