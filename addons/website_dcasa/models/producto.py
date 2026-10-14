"""Lo que el cliente ve de un producto en el sitio: el código público, nunca la referencia del proveedor.

La referencia interna (``default_code``) es de la casa; Odoo la deja salir por varios lados sin que se vea escrita en
la ficha: el nombre del producto lleva «[XHT022-T-W] …» y de ahí salen la dirección de la ficha, el nombre de cada foto
y los datos estructurados para Google. Aquí se cierran esos lados; el cliente ve el código público (``DC-K7M4PX``,
addons/dcasa_base/models/codigo_publico.py) y la dirección de la ficha es la de siempre pero sin el código.

Las direcciones viejas (``/shop/xht022-t-w-cama-…-5``) siguen funcionando: Odoo redirige (301) a la nueva.
"""
from odoo import api, models

PRODUCTOS = ('product.template', 'product.product')


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _slug(cls, value):
        """La dirección bonita de un producto sale de su nombre, sin el «[referencia]» con que Odoo lo antecede."""
        if getattr(value, '_name', None) in PRODUCTOS:
            value = value.with_context(display_default_code=False)
        return super()._slug(value)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _to_markup_data(self, website):
        """Datos estructurados para Google: el ``sku`` es el código público, no la referencia del proveedor."""
        datos = super()._to_markup_data(website)
        datos.pop('sku', None)
        if self.dcasa_codigo_publico:
            datos['sku'] = self.dcasa_codigo_publico
        return datos


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _get_website_sale_search_fields(self, search_in_description=True):
        """El cuadro de búsqueda de la tienda también encuentra el producto por su código público."""
        return super()._get_website_sale_search_fields(search_in_description) + ['dcasa_codigo_publico']
