"""«Vendido»: un pedido es una venta cuando ya está facturado por completo (pedido de la dueña, 2026-10-14).

Una cotización, un borrador o un pedido «por facturar» (un apartado que aún no se cobra ni se entrega) no es una venta.
Odoo ya dice cuándo un pedido está facturado por completo (``invoice_status = 'invoiced'``), pero cuenta también las
facturas que siguen en borrador. Aquí se exige además que no quede ninguna factura sin publicar.

El día de una venta es el de su **última factura publicada** (la fecha de la factura, ya en el día de Panamá): el
pedido que se apartó el lunes y se cobró y facturó el viernes se vendió el viernes, el mismo día que entra la plata a
la caja. Así «Vendido hoy», las barras de la semana, «lo más vendido» y la lista que abre «Ventas de hoy» cuentan lo
mismo, y el número de un día que ya pasó no cambia solo.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.tools import float_round

ZONA_PANAMA = 'America/Panama'


def _dia_en_panama(momento):
    """El día de Panamá de un ``datetime`` guardado en UTC sin zona (como guarda Odoo)."""
    return pytz.utc.localize(momento).astimezone(pytz.timezone(ZONA_PANAMA)).date()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Pedido repetido (capturas de la dueña, 2026-10-16: S00062 y S00063 de la misma clienta, el mismo día, por el
    # mismo total y con 5 minutos de diferencia; uno quedó sin facturar y aparecía como venta de más en los pedidos).
    dcasa_posible_repetido = fields.Char(
        'Pedido que parece repetido', compute='_compute_dcasa_posible_repetido',
        help='Otros pedidos de este cliente, del mismo día y por el mismo total, que no están cancelados.')

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

    @api.depends('partner_id', 'amount_total', 'date_order', 'state')
    def _compute_dcasa_posible_repetido(self):
        for orden in self:
            orden.dcasa_posible_repetido = ', '.join(orden._dcasa_repetidos().mapped('name')) or False

    def _dcasa_repetidos(self):
        """Los otros pedidos que parecen la misma venta: mismo cliente (o su empresa), mismo día de Panamá y mismo
        total, sin cancelar. Se buscan con sudo (para avisar aunque sea de otra vendedora): solo sale su número."""
        self.ensure_one()
        if self.state == 'cancel' or not self.partner_id or not self.amount_total or not self.date_order:
            return self.browse()
        dia = _dia_en_panama(self.date_order)
        inicio = pytz.timezone(ZONA_PANAMA).localize(datetime.combine(dia, time.min)).astimezone(
            pytz.utc).replace(tzinfo=None)
        otros = self.sudo().search([
            ('id', '!=', self._origin.id or 0), ('state', '!=', 'cancel'), ('company_id', '=', self.company_id.id),
            ('partner_id.commercial_partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('date_order', '>=', inicio), ('date_order', '<', inicio + timedelta(days=1))])
        total = float_round(self.amount_total, precision_digits=2)
        return otros.filtered(lambda o: float_round(o.amount_total, precision_digits=2) == total)

    @api.model
    def _dcasa_pedidos_repetidos(self, desde):
        """Los pedidos CONFIRMADOS desde ``desde`` (fecha) que parecen repetidos entre sí: mismo cliente, mismo día de
        Panamá y mismo total. Para el aviso del Inicio de quien controla la tienda."""
        inicio = pytz.timezone(ZONA_PANAMA).localize(datetime.combine(desde, time.min)).astimezone(
            pytz.utc).replace(tzinfo=None)
        grupos = defaultdict(self.browse)
        # Una sola lectura con lo que hace falta (el Inicio no repite búsquedas de pedidos).
        confirmados = self.search_fetch([('state', '=', 'sale'), ('date_order', '>=', inicio)],
                                        ['partner_id', 'date_order', 'amount_total'])
        for orden in confirmados:
            clave = (orden.partner_id.commercial_partner_id.id, _dia_en_panama(orden.date_order),
                     float_round(orden.amount_total, precision_digits=2))
            grupos[clave] |= orden
        repetidos = self.browse()
        for pedidos in grupos.values():
            if len(pedidos) > 1:
                repetidos |= pedidos
        return repetidos

    @api.model
    def _dcasa_accion_ventas_de_hoy(self):
        """Ventas › Hoy › Ventas de hoy: lo mismo que «Vendido hoy» del Inicio (solo lo facturado por completo).

        Con el mismo criterio de «panel completo» del Inicio: Gerencia, administradores y contabilidad ven las ventas
        de toda la tienda; quien vende sin controlar (la Vendedora) ve solo las suyas, como su tarjeta del Inicio."""
        accion = super()._dcasa_accion_ventas_de_hoy()
        hoy = fields.Date.context_today(self.with_context(tz=self.env.user.tz or 'America/Panama'))
        propio = self.env['dcasa.tablero']._solo_lo_propio()
        accion['domain'] = self._dcasa_dominio_vendido(desde=hoy, hasta=hoy, vendedor=self.env.user if propio else None)
        accion['help'] = (
            '<p class="o_view_nocontent_smiling_face o_dcasa_ayuda">'
            + ('Todavía no hay ventas tuyas facturadas hoy.' if propio else 'Todavía no hay ventas facturadas hoy.')
            + '</p><p>Una venta cuenta cuando su factura ya está publicada.</p>')
        return accion


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # El día de la venta, también en la línea: es lo que permite agrupar y filtrar las estadísticas por semana o mes.
    dcasa_fecha_venta = fields.Date(
        'Día de la venta', related='order_id.dcasa_fecha_venta', store=True, index=True, readonly=True)
