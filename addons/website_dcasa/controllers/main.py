from odoo import http
from odoo.fields import Domain
from odoo.http import request


class DcasaTienda(http.Controller):

    @http.route('/dcasa/carrito/agregar', type='http', auth='public', website=True, methods=['POST'],
                sitemap=False)
    def agregar_al_carrito(self, product_template_id=None, **kwargs):
        """«Agregar» de un clic desde la portada.

        Es un formulario normal (sin JavaScript), así funciona en cualquier teléfono.
        Productos con variantes van a su ficha para elegir.
        """
        website = request.website
        try:
            producto_id = int(product_template_id or 0)
        except ValueError:
            return request.redirect('/shop')
        # Buscar (no leer) respeta las reglas de acceso: un visitante solo encuentra lo publicado.
        producto = request.env['product.template'].search(Domain.AND([
            website.sale_product_domain(), [('id', '=', producto_id), ('is_published', '=', True)],
        ]), limit=1)
        if not producto:
            return request.redirect('/shop')
        if not website._dcasa_compra_directa(producto):
            # Hay que elegir algo (variante, combo...) o la tienda no lo deja comprar así: a la ficha.
            return request.redirect(producto.website_url)
        carrito = request.cart or website._create_cart()
        carrito._cart_add(product_id=producto.product_variant_id.id, quantity=1)
        return request.redirect('/shop/cart')

    @http.route('/whatsapp', type='http', auth='public', website=True, sitemap=False)
    def whatsapp(self, texto=None, **kwargs):
        """Enlace estable a WhatsApp para los bloques editables del sitio.

        El editor guarda el HTML tal cual: un ``wa.me/<número>`` escrito en un bloque quedaría
        congelado. ``/whatsapp`` usa siempre el número configurado en el sitio. Solo redirige a
        wa.me (o a /contactus si no hay número): no es una redirección abierta.
        """
        url = request.website._dcasa_whatsapp_url((texto or '')[:300] or None)
        return request.redirect(url, code=302, local=url.startswith('/'))
