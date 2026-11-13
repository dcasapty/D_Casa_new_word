from odoo import api, fields, models
from odoo.addons.dcasa_base.disponibilidad import AGOTADO, DISPONIBLE, POCAS, etiqueta_existencias
from odoo.fields import Domain

# Lo que lee el cliente en la ficha de la tienda (nunca el número de existencias).
TEXTOS_DISPONIBILIDAD = {DISPONIBLE: 'Disponible', POCAS: 'Quedan pocas', AGOTADO: 'Agotado'}


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

    def _dcasa_disponibilidad(self, variante=None):
        """``disponible`` / ``pocas`` / ``agotado`` de este producto (o de una de sus medidas) para el cliente.

        Lo que dicen Juan y la ficha de la tienda: la regla de ``dcasa_base/disponibilidad.py`` con las unidades
        libres (en existencia menos lo reservado) de la medida elegida o, sin medida, de todas; el umbral de «pocas»
        es el del producto (5 si no se cambió). Nunca el número.
        """
        self.ensure_one()
        plantilla = self.sudo()
        if not plantilla.is_storable:
            return etiqueta_existencias(0, controla_inventario=False)
        variantes = variante.sudo() if variante else plantilla.product_variant_ids
        libres = sum(max(v.free_qty, 0.0) for v in variantes)
        return etiqueta_existencias(libres, umbral=plantilla.available_threshold)

    def _dcasa_disponibilidad_ficha(self, variante=None):
        """Lo que pinta la ficha de la tienda: ``{'estado': 'pocas', 'texto': 'Quedan pocas'}``."""
        estado = self._dcasa_disponibilidad(variante or None)
        return {'estado': estado, 'texto': TEXTOS_DISPONIBILIDAD[estado]}

    def _get_additionnal_combination_info(self, product_or_template, quantity, uom, date, website):
        """Al cambiar de medida (y al abrir la ficha) el JavaScript de Odoo pide esta información: lleva la etiqueta
        de la medida elegida y ``disponibilidad.js`` la repinta. Solo en ese pedido de la ficha (el que marca
        ``website_sale_stock``): el catálogo de Meta y Black Weekend usan esta misma función por cada variante y no
        necesitan contar existencias."""
        info = super()._get_additionnal_combination_info(product_or_template, quantity, uom, date, website)
        if website and self.env.context.get('website_sale_stock_get_quantity'):
            variante = product_or_template if product_or_template.is_product_variant else None
            plantilla = variante.product_tmpl_id if variante else product_or_template
            ficha = plantilla._dcasa_disponibilidad_ficha(variante)
            info.update(dcasa_disponibilidad=ficha['estado'], dcasa_disponibilidad_texto=ficha['texto'])
        return info


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
