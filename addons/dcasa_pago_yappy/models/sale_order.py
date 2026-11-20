"""Lo que el equipo ve de un pedido pagado en línea, sin buscar: cómo pagó, la entrega y de dónde llegó la compra (el
celular del cliente ya sale en «Sus datos»). El detalle de lo que compró (producto, modelo, cantidad, precio y
descuento) son las líneas del pedido; la API de Yappy no manda ese detalle, así que aquí se junta con el pago en un
solo bloque (``models/resumen.py``)."""
from odoo import api, fields, models

from . import resumen
from .payment_transaction import ESPERA_DEL_AVISO


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

    def _dcasa_apartado_reclamado(self):
        """Un cobro de Yappy abierto (mandado a Yappy hace menos de 15 minutos y sin aviso todavía) cuenta como pedido
        reclamado: el apartado que vence por la noche no lo anula mientras la clienta está aprobando en su app. Sin
        esto la anulación podía cruzarse con el pago y el dinero entraba a un pedido anulado (que ahora va a revisión,
        pero lo mejor es no llegar ahí)."""
        if super()._dcasa_apartado_reclamado():
            return True
        desde = fields.Datetime.now() - ESPERA_DEL_AVISO
        return bool(self.sudo().transaction_ids.filtered(
            lambda tx: tx.provider_code == 'yappy' and tx.state in ('draft', 'pending') and tx.dcasa_yappy_orden
            and tx.dcasa_yappy_iniciada and tx.dcasa_yappy_iniciada >= desde))
