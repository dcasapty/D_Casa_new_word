"""Los pedidos de la página web entran SIN vendedora (decisión de la dueña, 2026-10-17).

Odoo les pone, al confirmarse o al quedar el pago pendiente, el «Vendedor» del sitio web (en una base nueva, el
administrador) o, si no hay, la vendedora de la ficha del cliente. Con «Cada vendedora ve solo sus documentos»
encendido eso los escondía de las vendedoras. Ahora:

* Un pedido de la web queda **sin vendedora**: lo ven todas para que alguien lo atienda (también si la ficha del
  cliente dice otra vendedora, y también cuando la tienda lo confirma sola o llega el pago en línea).
* **La vendedora que lo confirma se lo queda** (con el interruptor encendido o apagado). Si lo confirma Caja o
  Gerencia, sigue sin vendedora: lo ven todas y no cuenta para la meta de nadie.
* El «Vendedor» del sitio (*Ajustes › Sitio web*) viene vacío (la migración 19.0.1.15.0 lo vacía una vez). Si un
  administrador lo vuelve a poner, los pedidos web van a esa persona, como en Odoo: es la salida si algún día se quiere.
* El vendedor **del programa** (link ``/v/CÓDIGO``, ``sale.order.dcasa_vendedor_id`` de dcasa_socios) es otra cosa y
  no cambia: el carrito lo anota igual y su comisión sigue a la factura.
"""
from odoo import models


def toma_pedidos_web(usuario):
    """¿Quien confirma se queda el pedido web? Una vendedora (rol Vendedora sin Caja), o quien ve solo lo suyo."""
    if usuario._is_superuser() or not usuario._is_internal():
        return False
    if usuario._dcasa_solo_lo_suyo():
        return True
    return usuario.has_group('dcasa_base.group_vendedora') and not usuario.has_group('dcasa_base.group_caja')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _compute_user_id(self):
        web = self.filtered('website_id')
        super(SaleOrder, self - web)._compute_user_id()
        if not web or not self.env.context.get('force_user_recomputation'):
            return   # un carrito en borrador no recibe vendedora (como en Odoo): se queda como está
        quien = self.env.user
        toma = not self.env.su and toma_pedidos_web(quien)
        for orden in web.filtered(lambda o: not o.user_id):
            if toma:
                orden.user_id = quien
            elif orden.website_id.salesperson_id:
                orden.user_id = orden.website_id.salesperson_id
