from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _dcasa_entregas(self):
        """Las entregas de salida (no canceladas) de los pedidos de los que salió esta factura.

        Funciona con varias facturas a la vez. Si quien mira no puede leer ventas o inventario (p. ej. un lector
        contable), no hay entregas: así el paquete se arma igual con la factura y su copia.
        """
        if not (self.env['sale.order'].has_access('read') and self.env['stock.picking'].has_access('read')):
            return self.env['stock.picking']
        pedidos = self.line_ids.sale_line_ids.order_id
        return pedidos.picking_ids.filtered(
            lambda entrega: entrega.picking_type_code == 'outgoing' and entrega.state != 'cancel')

    def action_dcasa_imprimir_documentos(self):
        """Abre el cuadro pequeño «Imprimir documentos» con las facturas elegidas (o la factura abierta)."""
        return self.env['dcasa.impresion.paquete']._accion_dialogo(self)
