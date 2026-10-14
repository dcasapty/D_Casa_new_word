"""«Vendido»: un pedido es una venta cuando ya está facturado por completo (pedido de la dueña, 2026-10-14).

Una cotización, un borrador o un pedido «por facturar» (un apartado que aún no se cobra ni se entrega) no es una venta.
Odoo ya dice cuándo un pedido está facturado por completo (``invoice_status = 'invoiced'``), pero cuenta también las
facturas que siguen en borrador. Aquí se exige además que no quede ninguna factura sin publicar.

El día de una venta es el de su **última factura publicada** (la fecha de la factura, ya en el día de Panamá): el
pedido que se apartó el lunes y se cobró y facturó el viernes se vendió el viernes, el mismo día que entra la plata a
la caja. Así «Vendido hoy», las barras de la semana, «lo más vendido» y la lista que abre «Ventas de hoy» cuentan lo
mismo, y el número de un día que ya pasó no cambia solo.
"""
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_fecha_venta = fields.Date(
        'Día de la venta', compute='_compute_dcasa_fecha_venta', store=True, index=True, copy=False,
        help='El día en que el pedido quedó facturado por completo: la fecha de su última factura publicada. '
             'Queda vacío mientras haya algo por facturar o una factura sin publicar.')

    @api.depends('state', 'invoice_status',
                 'order_line.invoice_lines.move_id.state',
                 'order_line.invoice_lines.move_id.invoice_date',
                 'order_line.invoice_lines.move_id.move_type')
    def _compute_dcasa_fecha_venta(self):
        for orden in self:
            orden.dcasa_fecha_venta = orden._dcasa_dia_de_venta()

    def _dcasa_dia_de_venta(self):
        """La fecha de la última factura publicada, o ``False`` si el pedido todavía no es una venta."""
        self.ensure_one()
        if self.state != 'sale' or self.invoice_status != 'invoiced':
            return False
        facturas = self.order_line.invoice_lines.move_id
        if not facturas or any(factura.state == 'draft' for factura in facturas):
            return False
        fechas = [factura.invoice_date for factura in facturas
                  if factura.state == 'posted' and factura.move_type == 'out_invoice' and factura.invoice_date]
        return max(fechas) if fechas else False

    @api.model
    def _dcasa_dominio_vendido(self, desde=None, hasta=None, vendedor=None):
        """Dominio de las ventas: pedidos confirmados, facturados por completo y con todas sus facturas publicadas.

        ``desde`` y ``hasta`` (fechas, ambas incluidas) acotan el día de la venta; ``vendedor`` es un usuario o un id
        y deja solo lo que esa persona vendió.
        """
        dominio = [('state', '=', 'sale'), ('invoice_status', '=', 'invoiced'), ('dcasa_fecha_venta', '!=', False)]
        if desde:
            dominio.append(('dcasa_fecha_venta', '>=', fields.Date.to_string(desde)))
        if hasta:
            dominio.append(('dcasa_fecha_venta', '<=', fields.Date.to_string(hasta)))
        if vendedor:
            dominio.append(('user_id', '=', getattr(vendedor, 'id', vendedor)))
        return dominio

    @api.model
    def _dcasa_accion_ventas_de_hoy(self):
        """Ventas › Hoy › Ventas de hoy: lo mismo que «Vendido hoy» del Inicio (solo lo facturado por completo)."""
        accion = super()._dcasa_accion_ventas_de_hoy()
        hoy = fields.Date.context_today(self.with_context(tz=self.env.user.tz or 'America/Panama'))
        accion['domain'] = self._dcasa_dominio_vendido(desde=hoy, hasta=hoy)
        accion['help'] = (
            '<p class="o_view_nocontent_smiling_face">Todavía no hay ventas facturadas hoy.</p>'
            '<p>Una venta cuenta cuando su factura ya está publicada.</p>')
        return accion
