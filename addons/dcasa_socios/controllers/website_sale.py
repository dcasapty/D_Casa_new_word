"""El carrito de la tienda web enseña el paso «Usar mis puntos»."""

from odoo.addons.website_sale.controllers.cart import Cart
from odoo.http import request

from .main import SESSION_AVISO, socio_por_pin


class CartSocios(Cart):

    def _cart_values(self, **post):
        valores = super()._cart_values(**post)
        orden = request.cart
        if not orden:
            return valores
        # Un premio que venció o que ya no cabe sale antes de pintar el carrito.
        aviso = orden._dcasa_limpiar_premios_web()
        valores.update(orden._dcasa_valores_puntos_web())
        valores['dcasa_aviso'] = request.session.pop(SESSION_AVISO, None)
        if aviso and not valores['dcasa_aviso']:
            valores['dcasa_aviso'] = {'texto': aviso, 'tipo': 'info'}
        # Socio con sesión por PIN pero sin cuenta de la tienda: se le dice cómo usar sus puntos.
        valores['dcasa_socio_pin'] = socio_por_pin() if not valores['dcasa_socio'] else request.env['res.partner']
        return valores
