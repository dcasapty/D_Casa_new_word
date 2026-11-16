"""El envío que Andrés suma al carrito de la tienda (A2) no se pierde cuando el visitante cambia el carrito.

Andrés calcula el envío con la tabla de envíos y, con el «sí» del visitante, la página le pide a Odoo que lo ponga en el
carrito (``POST /dcasa/brian/v1/carrito/envio``): la misma línea que pone ``dcasa_envios`` para Juan
(``sale.order._dcasa_envio_poner``, con el transportista «Entrega a domicilio: te cotizamos por WhatsApp» y el precio de
la calculadora) y, si aplica, la de la promoción.

La tienda de Odoo, después de cada cambio del carrito (``_cart_add`` y ``_cart_update_line_quantity``, también los del
chat), vuelve a pedirle el precio al transportista del pedido (``_verify_cart_after_update``) y se lo pone a TODAS las
líneas de envío. El de «Entrega a domicilio» tiene precio fijo $0 («por cotizar»): sin esto, la primera cantidad que
cambiara dejaría el envío en $0 (y la promoción en $0, que dcasa_envios quita con una nota). Aquí, mientras el
transportista sea ese, la tienda no le cambia el precio a las líneas que puso el sistema (``_dcasa_envio_del_sistema``):
la promoción la sigue cuidando dcasa_envios con la compra que queda (``_dcasa_promocion_sincronizar``: la quita si
ya no cumple) y, si la compra AHORA la cumple, se suma aquí (``_dcasa_promocion_por_la_compra``).

Lo demás sigue como en Odoo: si el carrito queda sin productos que se entregan, el envío sale; al pagar
(``/shop/checkout`` y ``/shop/payment``), elegir la entrega vuelve a poner la del transportista, como hasta hoy
(«te cotizamos por WhatsApp»). La marca del contexto es un objeto, no ``True``: un contexto que llega por RPC es JSON y
nunca la puede traer.
"""
from odoo import models
from odoo.addons.dcasa_envios.motor.texto import dinero

CONSERVAR_ENVIO = 'dcasa_brian_tienda_conservar_envio'
CONSERVAR = object()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _verify_cart_after_update(self):
        transportista = self._dcasa_envio_transportista()
        if not (transportista and self.carrier_id == transportista
                and self.order_line.filtered(lambda linea: linea._dcasa_envio_del_sistema())):
            return super()._verify_cart_after_update()
        resultado = super(SaleOrder, self.with_context(**{CONSERVAR_ENVIO: CONSERVAR}))._verify_cart_after_update()
        self._dcasa_promocion_por_la_compra()
        return resultado

    def _dcasa_promocion_por_la_compra(self):
        """Si el carrito cambió y AHORA la compra cumple la promoción de envío de hoy (p. ej. subió la cantidad y pasó
        el mínimo), se suma, como la habría sumado ``_dcasa_envio_poner``. Si deja de cumplirla, la quita dcasa_envios
        (``_dcasa_promocion_sincronizar``, al cambiar las líneas). Solo con el envío a domicilio que puso el sistema."""
        self.ensure_one()
        if self.state not in ('draft', 'sent') or self.locked or self.order_line.filtered('dcasa_promocion_envio_id'):
            return
        envios = self.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id and not linea.display_type)
        if len(envios) != 1 or not envios._dcasa_envio_a_domicilio_del_sistema():
            return
        resultado, terminos = self._dcasa_promocion_calcular(envios)
        if terminos:
            self._dcasa_promocion_crear(envios, resultado, terminos)
            self._dcasa_promocion_nota(self.env._('La promoción de envío se sumó porque la compra del carrito ahora la '
                                                  'cumple: −%s.', dinero(resultado['ahorro'])))


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def write(self, vals):
        # Solo el precio que la tienda le pone a las líneas de envío al revisar el carrito (ver arriba).
        if self.env.context.get(CONSERVAR_ENVIO) is CONSERVAR and set(vals) == {'price_unit'}:
            resto = self.filtered(lambda linea: not linea._dcasa_envio_del_sistema())
            return super(SaleOrderLine, resto).write(vals) if resto else True
        return super().write(vals)
