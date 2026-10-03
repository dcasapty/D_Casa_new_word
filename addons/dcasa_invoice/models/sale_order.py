from odoo import models

from . import lineas


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _dcasa_nota(self):
        """Términos de la cotización con los enlaces al sitio público, nunca a localhost."""
        self.ensure_one()
        return self.company_id._dcasa_sin_enlaces_locales(self.note)

    @staticmethod
    def _dcasa_fecha(fecha):
        return fecha.strftime('%d/%m/%Y') if fecha else ''

    def _dcasa_titulo(self, proforma=False):
        self.ensure_one()
        if proforma:
            return 'Factura proforma'
        return 'Cotización' if self.state in ('draft', 'sent') else 'Pedido'

    def _dcasa_entrega(self):
        """La dirección de entrega, solo si no es la misma del cliente."""
        self.ensure_one()
        entrega = self.partner_shipping_id
        return entrega if entrega and entrega != self.partner_id else self.env['res.partner']

    def _dcasa_facturar_a(self):
        """A quién se factura, solo si no es el cliente."""
        self.ensure_one()
        factura = self.partner_invoice_id
        return factura if factura and factura != self.partner_id else self.env['res.partner']

    def _dcasa_datos(self, proforma=False):
        """[(etiqueta, valor)] de la columna de datos; solo lo que tiene valor."""
        self.ensure_one()
        cotizacion = self.state in ('draft', 'sent') and not proforma
        datos = [
            ('Fecha', self._dcasa_fecha(self.date_order)),
            ('Válida hasta', self._dcasa_fecha(self.validity_date) if cotizacion else ''),
            ('Fecha de entrega', self._dcasa_fecha(self.commitment_date)),
            ('Tu referencia', self.client_order_ref),
            ('Vendedora', self.user_id.name),
            ('Condiciones', self.payment_term_id.name),
        ]
        return [(etiqueta, valor) for etiqueta, valor in datos if valor]

    def _dcasa_lineas(self, lineas_a_imprimir):
        return lineas.separar(lineas_a_imprimir, lambda linea: not linea.display_type)

    def _dcasa_titulo_servicios(self, servicios):
        return lineas.titulo_servicios(servicios)

    def _dcasa_total_descuento(self):
        self.ensure_one()
        return lineas.total_descuento(self.order_line.filtered(lambda linea: not linea.display_type),
                                      self.currency_id, 'product_uom_qty')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _dcasa_codigo(self):
        self.ensure_one()
        return lineas.codigo_y_descripcion(self.name, self.product_id.default_code)[0]

    def _dcasa_descripcion(self):
        self.ensure_one()
        return lineas.codigo_y_descripcion(self.name, self.product_id.default_code)[1]

    def _dcasa_etiqueta(self):
        """Distintivo corto junto a la descripción; otros módulos lo llenan."""
        self.ensure_one()
        return ''
