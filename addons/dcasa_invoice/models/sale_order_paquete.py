from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_tiene_factura_publicada = fields.Boolean(
        string='Tiene factura publicada', compute='_compute_dcasa_tiene_factura_publicada',
        help='Para mostrar el botón «Imprimir documentos» solo cuando ya hay una factura de cliente publicada.')

    @api.depends('invoice_ids.state', 'invoice_ids.move_type')
    def _compute_dcasa_tiene_factura_publicada(self):
        for pedido in self:
            pedido.dcasa_tiene_factura_publicada = any(
                factura.move_type == 'out_invoice' and factura.state == 'posted' for factura in pedido.invoice_ids)

    def action_dcasa_imprimir_documentos(self):
        """Abre el cuadro «Imprimir documentos» con las facturas publicadas de estos pedidos."""
        facturas = self.invoice_ids.filtered(lambda f: f.move_type == 'out_invoice' and f.state == 'posted')
        sin_factura = len(self.filtered(lambda pedido: not pedido.dcasa_tiene_factura_publicada))
        return self.env['dcasa.impresion.paquete']._accion_dialogo(facturas.sorted('id'), sin_factura=sin_factura)
