"""La tienda y Mi cuenta muestran los nombres de los productos en formato título (F5, decisión de la dueña 2026-10-22).

Por dentro el nombre se guarda y se ve en MAYÚSCULAS; en el sitio el cliente lee «Cama Queen Tapizada». La regla está
en ``dcasa_base/nombres.py``; aquí se engancha en lo que pinta el sitio:

* Todo ``t-field`` del nombre de un producto o de una línea de pedido o factura en una página del sitio (la tarjeta
  de /shop, la ficha y su miga de pan, el portal del pedido): ``ir.qweb._get_field``. Con el editor abierto se deja
  el nombre tal cual, para que lo que se edite sea el nombre guardado.
* El carrito y el pago (``name_short``, ``_get_line_header``), el buscador del sitio, el título para compartir
  (``og:title``) y los datos para Google (models/producto.py); las plantillas que pintan ``producto.name`` con
  ``t-out`` usan ``_dcasa_nombre_cliente()`` (views/nombres_cliente_templates.xml).
"""
from odoo import models
from odoo.addons.dcasa_base.nombres import nombre_para_cliente
from odoo.http import request

# (modelo, campo) que el sitio pinta con t-field y que el cliente lee como el nombre de lo que compra.
CAMPOS_NOMBRE = frozenset({
    ('product.template', 'name'), ('product.product', 'name'),
    ('sale.order.line', 'name'), ('account.move.line', 'name'),
})


def pagina_del_cliente():
    """Una página del sitio o del portal (no el backend, ni un correo, ni un PDF armado desde una pantalla interna)."""
    return bool(request) and bool(getattr(request, 'is_frontend', False))


class IrQweb(models.AbstractModel):
    _inherit = 'ir.qweb'

    def _get_field(self, record, field_name, expression, tagName, field_options, values):
        atributos, contenido, forzar = super()._get_field(
            record, field_name, expression, tagName, field_options, values)
        if (contenido and (record._name, field_name) in CAMPOS_NOMBRE
                and not field_options.get('inherit_branding') and not field_options.get('translate')
                and pagina_del_cliente()):
            valor = record[field_name]
            if isinstance(valor, str) and valor:
                modelo = 'ir.qweb.field.' + field_options.get('type', '')
                conversor = self.env[modelo] if modelo in self.env else self.env['ir.qweb.field']
                contenido = conversor.value_to_html(nombre_para_cliente(valor), field_options)
        return atributos, contenido, forzar


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _compute_name_short(self):
        """El nombre corto del carrito y del pago («Cama Tapizada (King)»): solo lo usa el sitio."""
        super()._compute_name_short()
        for linea in self:
            linea.name_short = nombre_para_cliente(linea.name_short)

    def _get_line_header(self):
        return nombre_para_cliente(super()._get_line_header())
