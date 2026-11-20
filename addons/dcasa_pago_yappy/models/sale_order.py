"""Lo que el equipo ve de un pedido pagado en línea, sin buscar: cómo pagó, la entrega y de dónde llegó la compra (el
celular del cliente ya sale en «Sus datos»). El detalle de lo que compró (producto, modelo, cantidad, precio y
descuento) son las líneas del pedido; la API de Yappy no manda ese detalle, así que aquí se junta con el pago en un
solo bloque (``models/resumen.py``)."""
from odoo import api, fields, models

from . import resumen


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_pago_texto = fields.Text(
        'Cómo pagó', compute='_compute_dcasa_resumen_web',
        help='Cada pago en línea de este pedido: la forma (Yappy, tarjeta…), en qué estado está, de cuánto, cuándo y, '
             'en Yappy, la orden que se ve en el reporte de Yappy Comercial. El número de confirmación de Yappy es '
             'solo informativo: no está firmado.')
    dcasa_entrega_texto = fields.Char('Entrega', compute='_compute_dcasa_resumen_web')
    dcasa_origen_texto = fields.Char('Origen de la compra', compute='_compute_dcasa_resumen_web')

    @api.depends('transaction_ids', 'transaction_ids.state', 'partner_id', 'partner_shipping_id', 'carrier_id',
                 'website_id')
    def _compute_dcasa_resumen_web(self):
        for pedido in self:
            pagos = pedido.sudo().transaction_ids.sorted(lambda tx: tx.id, reverse=True)[:5]
            pedido.dcasa_pago_texto = '\n'.join(resumen.pago(self.env, tx) for tx in pagos) or False
            pedido.dcasa_entrega_texto = resumen.entrega(pedido) or False
            pedido.dcasa_origen_texto = resumen.origen(pedido) or False
