"""El nombre de un producto tal como lo ve el cliente (formato título; la regla está en ``dcasa_base/nombres.py``).

* ``_dcasa_nombre_cliente()`` en productos y líneas: lo usan la tienda, Mi cuenta, Juan, los correos y los PDF.
* Con ``dcasa_para_cliente`` en el contexto, el ``display_name`` de un producto sale en formato título: así se arma un
  documento que imprime el producto tal cual (la nota de entrega, ``stock.picking._dcasa_para_imprimir``). Sin la
  clave, todo igual: las pantallas internas siguen en MAYÚSCULAS y lo que se guarda (el nombre de una línea) también.
"""
from odoo import api, models

from ..nombres import nombre_para_cliente

CLAVE_CLIENTE = 'dcasa_para_cliente'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.depends_context(CLAVE_CLIENTE)
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get(CLAVE_CLIENTE):
            for plantilla in self:
                plantilla.display_name = nombre_para_cliente(plantilla.display_name)

    def _dcasa_nombre_cliente(self):
        """«CAMA QUEEN TAPIZADA» → «Cama Queen Tapizada» (sin código)."""
        self.ensure_one()
        return nombre_para_cliente(self.name or '')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.depends_context(CLAVE_CLIENTE)
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get(CLAVE_CLIENTE):
            for producto in self:
                producto.display_name = nombre_para_cliente(producto.display_name)

    def _dcasa_nombre_cliente(self):
        """«CAMA TAPIZADA (King)» → «Cama Tapizada (King)»: con la medida o el color, sin la referencia."""
        self.ensure_one()
        return nombre_para_cliente(self.with_context(display_default_code=False).display_name or '')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _dcasa_nombre_cliente(self):
        """La descripción de la línea (varias líneas) en formato título."""
        self.ensure_one()
        return nombre_para_cliente(self.name or '')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _dcasa_nombre_cliente(self):
        self.ensure_one()
        return nombre_para_cliente(self.name or '')
