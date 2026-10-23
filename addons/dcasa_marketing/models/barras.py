"""El Escáner también abre las fotos del producto en grande: su tarjeta trae el producto (la plantilla) de la foto."""
from odoo import models


class DcasaBarras(models.AbstractModel):
    _inherit = 'dcasa.barras'

    def _ficha_de(self, producto):
        ficha = super()._ficha_de(producto)
        ficha['plantilla_id'] = producto.product_tmpl_id.id
        return ficha
