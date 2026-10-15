"""El código público (DC-K7M4PX) en lugar de la referencia del proveedor, en lo que ve el cliente.

Solo cuando la empresa enciende «Mostrar el código público de los productos…» (res.company); apagado, NADA de esto
actúa y Odoo se comporta exactamente como siempre. La referencia interna (``default_code``, la del proveedor) sigue
siendo la de la casa: sirve para pedir, contar y encontrar el producto, pero el cliente no la ve.

Dos caminos:

* El nombre de la línea que Odoo guarda en una cotización o factura NUEVA («[IM-2001] Colchón…»): sin la referencia
  (``display_default_code=False``, la manera estándar de Odoo). Lo ya guardado no se reescribe: al imprimir se limpia
  igual (``lineas.codigo_y_descripcion``).
* Un documento que imprime el nombre del producto tal cual (la nota de entrega): su ``o`` se arma con
  ``dcasa_codigo_publico=True`` y el nombre sale «[DC-K7M4PX] Colchón…» (ver ``stock.picking._dcasa_para_imprimir``).
"""
from odoo import api, models

CLAVE_CONTEXTO = 'dcasa_codigo_publico'


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.depends_context(CLAVE_CONTEXTO)
    def _compute_display_name(self):
        """Con ``dcasa_codigo_publico`` en el contexto: «[DC-K7M4PX] Nombre» (y sin código público, solo «Nombre»).

        El contexto trae también ``display_default_code=False``: Odoo arma el nombre sin la referencia del proveedor y
        aquí solo se le antepone el código público.
        """
        super()._compute_display_name()
        if not self.env.context.get(CLAVE_CONTEXTO):
            return
        for producto in self:
            codigo = producto.dcasa_codigo_publico
            if codigo:
                producto.display_name = f'[{codigo}] {producto.display_name}'

    def get_product_multiline_description_sale(self):
        """El nombre de la línea de una cotización: sin la referencia del proveedor si la empresa lo pide."""
        if self.env.company.dcasa_mostrar_codigo_publico:
            return super(ProductProduct, self.with_context(display_default_code=False)
                         ).get_product_multiline_description_sale()
        return super().get_product_multiline_description_sale()
