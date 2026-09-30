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
