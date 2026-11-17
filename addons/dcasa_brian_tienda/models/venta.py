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

Solo mientras valgan las reglas con que se sumó (``_dcasa_envio_sumado_vale``): si Gerencia apaga «Juan cotiza
envíos», la tarifa vuelve a revisión o el lugar se archiva o queda sin precio, en el siguiente cambio del carrito (o
al enseñarlo o armar su PDF) vuelve la entrega de Odoo.

Lo demás sigue como en Odoo: si el carrito queda sin productos que se entregan, el envío sale; al pagar, la tienda
vuelve a poner la entrega del transportista («te cotizamos por WhatsApp», $0) en ``/shop/payment`` siempre y en
``/shop/checkout`` solo si el monto del envío no es el del transportista (con el envío gratis por la promoción, el
monto ya es $0 y se queda hasta ``/shop/payment``). Si el visitante vuelve al chat, la de «te cotizamos» en $0 se
cambia por el envío al volver a sumarlo (``_dcasa_quitar_entrega_por_cotizar``).

La marca del contexto es un objeto, no ``True``: un contexto que llega por RPC es JSON y nunca la puede traer.
"""
from odoo import models
from odoo.addons.dcasa_envios.motor.texto import dinero

CONSERVAR_ENVIO = 'dcasa_brian_tienda_conservar_envio'
CONSERVAR = object()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _verify_cart_after_update(self):
        if not self._dcasa_envio_sumado_en_el_carrito():
            return super()._verify_cart_after_update()
        if not self._dcasa_envio_sumado_vale():
            # Gerencia apagó «Juan cotiza envíos», la tarifa volvió a revisión o el lugar ya no tiene precio para el
            # cliente: lo que se sumó no se conserva; Odoo pone su entrega («te cotizamos por WhatsApp»).
            self._set_delivery_method(self.carrier_id)
            return super()._verify_cart_after_update()
        resultado = super(SaleOrder, self.with_context(**{CONSERVAR_ENVIO: CONSERVAR}))._verify_cart_after_update()
        self._dcasa_promocion_por_la_compra()
        return resultado

    def _dcasa_envio_sumado_en_el_carrito(self):
        """¿Este carrito tiene el envío que sumó el sistema, con el transportista «te cotizamos por WhatsApp»?"""
        self.ensure_one()
        transportista = self._dcasa_envio_transportista()
        return bool(transportista and self.carrier_id == transportista
                    and self.order_line.filtered(lambda linea: linea._dcasa_envio_del_sistema()))

    def _dcasa_envio_sumado_vale(self):
        """Las mismas reglas con que se sumó (``POST /dcasa/brian/v1/carrito/envio``): «Juan cotiza envíos» encendido,
        la tarifa aprobada y el lugar activo, revisado y con un precio claro para el cliente."""
        self.ensure_one()
        herramientas = self.env['brian.herramientas'].sudo()
        if herramientas._j_envios_encendidos():
            return False
        lugar = self.order_line.filtered('dcasa_envio_lugar_id')[:1].dcasa_envio_lugar_id.sudo()
        if not lugar or not lugar.active:
            return False
        return not herramientas._j_envio_sin_precio_para_el_cliente(herramientas._j_envio_tarjeta(lugar))

    def _dcasa_revisar_envio_sumado(self):
        """Antes de enseñar el carrito o armar su PDF: si el envío sumado ya no vale (ver arriba), se cambia por la
        entrega de Odoo, para que nunca salga un precio que hoy no se daría."""
        for orden in self:
            if orden.state == 'draft' and orden._dcasa_envio_sumado_en_el_carrito() \
                    and not orden._dcasa_envio_sumado_vale():
                orden._set_delivery_method(orden.carrier_id)

    def _dcasa_quitar_entrega_por_cotizar(self):
        """Quita la línea de «Entrega a domicilio: te cotizamos por WhatsApp» en $0 que pone la tienda al elegir la
        entrega en el pago, si es la única de envío: así se puede sumar el envío calculado. Una línea de envío que puso
        una persona (con precio, o de otro producto) no se toca."""
        self.ensure_one()
        transportista = self._dcasa_envio_transportista()
        envios = self.order_line.filtered(lambda linea: not linea.display_type and linea._dcasa_es_envio())
        de_la_tienda = envios.filtered(lambda linea: linea.is_delivery and not linea._dcasa_envio_del_sistema()
                                       and transportista and linea.product_id == transportista.product_id
                                       and self.currency_id.is_zero(linea.price_unit) and not linea.qty_invoiced)
        if envios and envios == de_la_tienda:
            de_la_tienda.sudo().unlink()

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
