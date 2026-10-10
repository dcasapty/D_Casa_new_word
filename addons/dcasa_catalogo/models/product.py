from odoo import api, fields, models
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dcasa_medidas = fields.Char(
        string='Medidas',
        help='Tal como vienen impresas en la foto del proveedor, p. ej. «Ancho × Fondo × Alto: 80 × 40 × 120 cm». '
             'Se muestran en la ficha de la tienda.')
    dcasa_combo = fields.Char(
        string='Precio en combo o el par',
        help='Texto del Excel de precios, p. ej. «Combo con colchón $349.99» o «El par (-10%) $28.78». '
             'Se muestra en la ficha separado del precio.')
    # El «A la mano» de Odoo se calcula al vuelo y por eso la lista de productos no lo puede ordenar, agrupar ni sumar
    # por categoría. Este es el mismo número guardado en el producto: marketing ordena por mayor o menor stock, y
    # combinado con la categoría y el precio, elige qué empujar en una campaña. Se recalcula solo cuando cambia
    # una existencia (entrada, venta, ajuste) y vale 0 si el producto no controla inventario.
    dcasa_stock = fields.Float(
        string='Stock', compute='_compute_dcasa_stock', store=True, digits=(16, 0), aggregator='sum',
        help='Unidades en existencia (bodega y tienda) de todas sus medidas y colores. Se guarda en el producto para '
             'poder ordenar y filtrar la lista. Es el mismo número que «A la mano»; 0 si no controla inventario.')

    @api.depends('is_storable', 'product_variant_ids.active', 'product_variant_ids.stock_quant_ids.quantity',
                 'product_variant_ids.stock_quant_ids.location_id.usage')
    def _compute_dcasa_stock(self):
        controlados = self.filtered('is_storable')
        (self - controlados).dcasa_stock = 0.0
        if not controlados:
            return
        # Sin contexto ni usuario: lo que dice la existencia real, no lo que una pantalla filtró (bodega o ubicación).
        por_variante = {
            producto.id: cantidad
            for producto, cantidad in self.env['stock.quant'].sudo()._read_group(
                [('product_id.product_tmpl_id', 'in', controlados.ids), ('location_id.usage', '=', 'internal')],
                ['product_id'], ['quantity:sum'])}
        for plantilla in controlados:
            plantilla.dcasa_stock = sum(
                por_variante.get(variante.id, 0.0) for variante in plantilla.product_variant_ids)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _search_display_name(self, operator, value):
        """«colchón queen» encuentra el colchón en tamaño Queen: cada palabra puede estar en el
        nombre, la referencia o el tamaño (en Odoo, la frase entera tenía que estar en el nombre)."""
        palabras = value.split() if operator == 'ilike' and isinstance(value, str) else []
        if len(palabras) < 2:
            return super()._search_display_name(operator, value)
        buscar = super()._search_display_name
        return Domain.AND([
            Domain.OR([
                buscar('ilike', palabra),
                [('product_template_attribute_value_ids.name', 'ilike', palabra)],
            ])
            for palabra in palabras
        ])
