"""Volver a la tienda a mitad de un cobro de Yappy: la clienta aprobó (o está aprobando) en su app, refrescó o cerró
la pestaña y vuelve. Con un cobro abierto Odoo suelta el carrito de la sesión (``_get_and_cache_current_cart``) y la
clienta caía en la tienda con el carrito vacío, sin ver que su cobro sigue en marcha ni que «Mis pedidos» no lo lista.
Aquí se le muestra la pantalla de estado de ese cobro (``/payment/status``).

Solo con **la transacción de Yappy de la propia sesión** (la que esa sesión viene pagando: la guarda Odoo al crearla),
todavía ``pending`` y mandada a Yappy hace menos de 5 minutos (lo que dura su solicitud), y solo si la sesión no tiene
un carrito con cosas (quien ya sigue comprando otra cosa no se redirige). Nunca se mira ni se enseña nada de otra
sesión."""
from datetime import timedelta

from odoo import fields, http
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
from odoo.addons.website_sale.controllers.cart import Cart
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request

CODIGO = 'yappy'
RUTA_DE_ESTADO = '/payment/status'
# Lo que dura la solicitud en la app de Yappy (pasado eso, el aviso ya llegó o el cobro tiene su pendiente para Caja).
VIGENCIA_DE_LA_SOLICITUD = timedelta(minutes=5)


def _redireccion_al_cobro_en_marcha():
    """Un ``redirect`` a la pantalla de estado si esta sesión tiene un cobro de Yappy en marcha y ningún carrito con
    cosas; si no, ``None``."""
    id_de_la_transaccion = request.session.get(PaymentPostProcessing.MONITORED_TX_ID_KEY)
    if not id_de_la_transaccion:
        return None
    tx = request.env['payment.transaction'].sudo().browse(id_de_la_transaccion).exists()
    if not tx or tx.provider_code != CODIGO or tx.state != 'pending' or not tx.dcasa_yappy_iniciada:
        return None
    if tx.dcasa_yappy_iniciada < fields.Datetime.now() - VIGENCIA_DE_LA_SOLICITUD:
        return None
    carrito = request.cart
    if carrito and carrito.order_line:
        return None
    return request.redirect(RUTA_DE_ESTADO)


class DcasaYappyCarrito(Cart):

    @http.route()
    def cart(self, *args, **kwargs):
        return _redireccion_al_cobro_en_marcha() or super().cart(*args, **kwargs)


class DcasaYappyPago(WebsiteSale):

    @http.route()
    def shop_payment(self, **post):
        return _redireccion_al_cobro_en_marcha() or super().shop_payment(**post)
