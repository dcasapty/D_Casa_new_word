"""Ganancia de cada venta: lo que se cobró sin ITBMS menos lo que costó la mercancía (pedido de la dueña, 2026-10-16).

Reglas (mejor práctica contable, decididas el 2026-10-16):

* La ganancia se mide **sin ITBMS**: el ITBMS se cobra por cuenta de la DGI, no es ingreso. Tampoco entra al costo: el
  que se paga al comprar es crédito fiscal. Por eso se parte de ``price_subtotal`` (ya sin ITBMS y con los descuentos)
  y del costo del producto sin ITBMS.
* El costo se **guarda en la línea** al armar la cotización y se vuelve a tomar al **confirmar la venta**: si después el
  producto cambia de costo, las ventas ya hechas no se mueven.
* Cuentan las líneas de **mercancía** y las líneas **negativas** que no son mercancía (el descuento global, el de
  importe fijo, un premio): rebajan lo cobrado. Los servicios positivos (flete, armado) no tienen costo cargado y no
  entran, ni en lo cobrado ni en el costo, para no inflar el porcentaje.
* Un pedido con alguna mercancía **sin costo cargado** no inventa ganancia: queda fuera de la suma y se cuenta aparte
  («N ventas sin costo»).
* Solo la ven Gerencia y los administradores (``GRUPOS_UTILIDAD``): los costos son sensibles. No se instala
  ``sale_margin`` porque muestra el costo a todo el personal.

Las ventas hechas antes de esta versión toman el costo del producto **de hoy** al actualizar el módulo.
"""
from odoo import api, fields, models

GRUPOS_UTILIDAD = 'sales_team.group_sale_manager,base.group_system'


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_costo_unitario = fields.Float(
        'Costo unitario (sin ITBMS)', compute='_compute_dcasa_costo_unitario', store=True, copy=False,
        precompute=True, digits='Product Price', groups=GRUPOS_UTILIDAD,
        help='El costo del producto cuando se armó o se confirmó la venta, en la unidad de la línea.')
    dcasa_es_ganancia = fields.Boolean(
        'Cuenta en la ganancia', compute='_compute_dcasa_ganancia', store=True, groups=GRUPOS_UTILIDAD,
        help='Mercancía, o línea negativa que rebaja lo cobrado (descuento global o de importe fijo, premio).')
    dcasa_sin_costo = fields.Boolean(
        'Mercancía sin costo', compute='_compute_dcasa_ganancia', store=True, groups=GRUPOS_UTILIDAD,
        help='Es mercancía y su producto no tiene costo cargado: la venta no cuenta en la ganancia.')
    dcasa_venta_neta = fields.Float(
        'Venta neta (sin ITBMS)', compute='_compute_dcasa_ganancia', store=True, digits='Product Price',
        groups=GRUPOS_UTILIDAD, help='Lo cobrado por esta línea sin ITBMS, si cuenta en la ganancia.')
    dcasa_utilidad = fields.Float(
        'Ganancia', compute='_compute_dcasa_ganancia', store=True, digits='Product Price', groups=GRUPOS_UTILIDAD,
        help='Venta neta menos costo. En una línea negativa es la propia rebaja.')

    def _dcasa_costo_actual(self):
        """El costo de hoy del producto, en la unidad y la moneda de la línea (cero si no hay producto)."""
        self.ensure_one()
        if not self.product_id:
            return 0.0
        linea = self.with_company(self.company_id)
        costo = linea.product_id.uom_id._compute_price(linea.product_id.standard_price, linea.product_uom_id)
        return linea._convert_to_sol_currency(costo, linea.product_id.cost_currency_id)

    @api.depends('product_id', 'company_id', 'currency_id', 'product_uom_id')
    def _compute_dcasa_costo_unitario(self):
        for linea in self.sudo():
            linea.dcasa_costo_unitario = linea._dcasa_costo_actual()

    @api.depends('price_subtotal', 'product_uom_qty', 'dcasa_costo_unitario', 'product_type', 'display_type',
                 'is_downpayment')
    def _compute_dcasa_ganancia(self):
        for linea in self.sudo():
            es_mercancia = bool(linea.product_id) and linea.product_type == 'consu' \
                and not linea.display_type and not linea.is_downpayment
            rebaja = bool(linea.product_id) and linea.product_type != 'consu' and not linea.display_type \
                and not linea.is_downpayment and linea.price_subtotal < 0
            linea.dcasa_es_ganancia = es_mercancia or rebaja
            linea.dcasa_sin_costo = es_mercancia and linea.dcasa_costo_unitario <= 0
            linea.dcasa_venta_neta = linea.price_subtotal if (es_mercancia or rebaja) else 0.0
            if es_mercancia and not linea.dcasa_sin_costo:
                linea.dcasa_utilidad = linea.price_subtotal - linea.dcasa_costo_unitario * linea.product_uom_qty
            elif rebaja:
                linea.dcasa_utilidad = linea.price_subtotal
            else:
                linea.dcasa_utilidad = 0.0

    def _dcasa_fijar_costo(self):
        """Vuelve a tomar el costo del producto: al confirmar la venta queda el de ese momento."""
        for linea in self.sudo():
            linea.write({'dcasa_costo_unitario': linea._dcasa_costo_actual()})
        return True


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_sin_costo = fields.Boolean(
        'Con mercancía sin costo', compute='_compute_dcasa_utilidad', store=True, groups=GRUPOS_UTILIDAD,
        help='Alguna mercancía del pedido no tiene costo cargado: no cuenta en la ganancia.')
    dcasa_venta_neta = fields.Float(
        'Venta neta (sin ITBMS)', compute='_compute_dcasa_utilidad', store=True, digits='Product Price',
        groups=GRUPOS_UTILIDAD)
    dcasa_utilidad = fields.Float(
        'Ganancia', compute='_compute_dcasa_utilidad', store=True, digits='Product Price', groups=GRUPOS_UTILIDAD)
    dcasa_utilidad_pct = fields.Float(
        'Ganancia (%)', compute='_compute_dcasa_utilidad', store=True, digits=(16, 1), groups=GRUPOS_UTILIDAD,
        help='Ganancia sobre la venta neta. Vacío (0) si el pedido tiene mercancía sin costo.')

    @api.depends('order_line.dcasa_sin_costo', 'order_line.dcasa_venta_neta', 'order_line.dcasa_utilidad')
    def _compute_dcasa_utilidad(self):
        for orden in self.sudo():
            lineas = orden.order_line
            orden.dcasa_sin_costo = any(lineas.mapped('dcasa_sin_costo'))
            orden.dcasa_venta_neta = sum(lineas.mapped('dcasa_venta_neta'))
            orden.dcasa_utilidad = sum(lineas.mapped('dcasa_utilidad'))
            neta = orden.dcasa_venta_neta
            orden.dcasa_utilidad_pct = 0.0 if (orden.dcasa_sin_costo or not neta) else orden.dcasa_utilidad / neta * 100

    def action_confirm(self):
        # El costo de la venta es el de este momento, no el de cuando se armó la cotización.
        self.order_line._dcasa_fijar_costo()
        return super().action_confirm()
