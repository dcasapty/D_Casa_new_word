from odoo import http
from odoo.addons.website_dcasa.models.website import LATITUD, LONGITUD
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.fields import Domain
from odoo.http import request


class DcasaCheckout(WebsiteSale):
    """Dirección para un cliente de Panamá: sin empresa ni VAT, y Panamá ya elegido."""

    def _prepare_address_form_values(self, *args, **kwargs):
        valores = super()._prepare_address_form_values(*args, **kwargs)
        valores['display_b2b_fields'] = False
        return valores

    def _get_default_country(self, order_sudo=False, **kwargs):
        pais = super()._get_default_country(order_sudo=order_sudo, **kwargs)
        return pais or request.website.company_id.country_id


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
        if not 0 < producto_id < 2**31:  # fuera del rango de un id de PostgreSQL
            return request.redirect('/shop')
        # Buscar (no leer) respeta las reglas de acceso: un visitante solo encuentra lo publicado.
        producto = request.env['product.template'].search(Domain.AND([
            website._dcasa_dominio_publicado(), [('id', '=', producto_id)],
        ]), limit=1)
        if not producto:
            return request.redirect('/shop')
        permitido = producto.product_variant_id._is_add_to_cart_allowed()  # precio cero, acceso a la tienda
        if not (permitido and website._dcasa_compra_directa(producto)):
            # Hay que elegir algo (variante, combo...) o la tienda no lo deja comprar así: a la ficha.
            return request.redirect(producto.website_url)
        carrito = request.cart or website._create_cart()
        carrito._cart_add(product_id=producto.product_variant_id.id, quantity=1)
        return request.redirect('/shop/cart')

    @http.route('/visitanos', type='http', auth='public', website=True, sitemap=True)
    def visitanos(self, **kwargs):
        """Página exclusiva de la tienda: dirección, mapa, cómo llegar y contacto."""
        return request.render('website_dcasa.pagina_visitanos', {'latitud': LATITUD, 'longitud': LONGITUD})

    @http.route('/whatsapp', type='http', auth='public', website=True, sitemap=False)
    def whatsapp(self, texto=None, **kwargs):
        """Enlace estable a WhatsApp para los bloques editables del sitio.

        El editor guarda el HTML tal cual: un ``wa.me/<número>`` escrito en un bloque quedaría
        congelado. ``/whatsapp`` usa siempre el número configurado en el sitio. Solo redirige a
        wa.me (o a /contactus si no hay número): no es una redirección abierta.
        """
        url = request.website._dcasa_whatsapp_url((texto or '')[:300])
        return request.redirect(url, code=302, local=url.startswith('/'))
