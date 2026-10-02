"""Rutas de la tienda del borde: el feed del catálogo y el «Agregar al carrito» de las páginas estáticas."""
import json
from urllib.parse import urlsplit

from odoo import http
from odoo.addons.dcasa_tienda_borde.models.pendiente import token_configurado, token_valido
from odoo.fields import Domain
from odoo.http import request

CABECERA_TOKEN = 'X-Dcasa-Tienda-Token'


def _origen(url):
    partes = urlsplit(url or '')
    return f'{partes.scheme}://{partes.netloc}'.lower() if partes.scheme and partes.netloc else ''


def mismo_origen(httprequest):
    """¿El POST viene de una página de este mismo sitio?

    Sustituye al token CSRF en el «Agregar» de las páginas estáticas (que no pueden llevar un
    token atado a la sesión: son las mismas para todos). Se exige, en este orden:

    1. ``Origin`` (lo mandan todos los navegadores actuales en un POST) igual al del sitio;
    2. si no hay Origin: ``Sec-Fetch-Site: same-origin``;
    3. si tampoco: ``Referer`` del mismo origen.

    Sin ninguna de las tres, se rechaza. ``host_url`` ya viene corregido por proxy_mode con
    ``X-Forwarded-Host``/``X-Forwarded-Proto`` del Worker.
    """
    esperado = _origen(httprequest.host_url)
    origen = httprequest.headers.get('Origin')
    if origen and origen != 'null':
        return origen.rstrip('/').lower() == esperado
    sitio = httprequest.headers.get('Sec-Fetch-Site')
    if sitio:
        return sitio == 'same-origin'
    referer = httprequest.headers.get('Referer')
    return bool(referer) and _origen(referer) == esperado


class DcasaTiendaBorde(http.Controller):

    @http.route('/dcasa/tienda/feed', type='http', auth='public', website=True, methods=['GET'],
                sitemap=False)
    def feed(self, **kwargs):
        """Catálogo publicado para el Worker. Sin el secreto (cabecera) no existe: 404.

        El Worker la pide directo al contenedor; desde internet el borde la bloquea (edge/src/routing.ts).
        """
        if not token_configurado() or not token_valido(request.httprequest.headers.get(CABECERA_TOKEN)):
            return request.make_response('Not Found', status=404, headers=[('Content-Type', 'text/plain')])
        datos = request.website._dcasa_tienda_feed()
        return request.make_response(
            json.dumps(datos, ensure_ascii=False, default=str),
            headers=[
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Cache-Control', 'no-store'),
                ('X-Robots-Tag', 'noindex'),
            ],
        )

    @http.route('/dcasa/carrito/agregar-borde', type='http', auth='public', website=True, methods=['POST'],
                csrf=False, sitemap=False)
    def agregar_desde_borde(self, product_template_id=None, product_id=None, **kwargs):
        """«Agregar al carrito» de las páginas estáticas (formulario normal, sin JavaScript).

        ``csrf=False`` porque la página estática no tiene sesión; en su lugar, ``mismo_origen``.
        Agregar al carrito no gasta dinero ni revela nada; aun así, un sitio ajeno no puede
        llenarle el carrito a nadie (sin Origin/Referer propios: 403; y la cookie de sesión de
        Odoo es SameSite=Lax, que un POST de otro sitio no lleva).
        """
        if not mismo_origen(request.httprequest):
            return request.make_response('Forbidden', status=403, headers=[('Content-Type', 'text/plain')])
        website = request.website
        try:
            plantilla_id = int(product_template_id or 0)
            variante_id = int(product_id or 0)
        except ValueError:
            return request.redirect('/shop')
        if not (0 <= plantilla_id < 2**31 and 0 <= variante_id < 2**31) or not (plantilla_id or variante_id):
            return request.redirect('/shop')
        publicado = website._dcasa_dominio_publicado()
        if variante_id:
            # Buscar (no leer) respeta las reglas de acceso: el visitante solo encuentra lo publicado.
            variante = request.env['product.product'].search([('id', '=', variante_id)], limit=1)
            producto = variante.product_tmpl_id
            if not variante or not producto.filtered_domain(publicado):
                return request.redirect('/shop')
        else:
            producto = request.env['product.template'].search(
                Domain.AND([publicado, [('id', '=', plantilla_id)]]), limit=1)
            if not producto:
                return request.redirect('/shop')
            variante = producto.product_variant_id
        modo = website._dcasa_tienda_modo_compra(producto)
        valido = (modo == 'directa' and not variante_id) or (modo == 'variantes' and variante_id)
        if not (valido and variante._is_add_to_cart_allowed()):
            # Hay que elegir algo en la ficha de Odoo, o la tienda no deja comprarlo así.
            return request.redirect(producto.website_url)
        carrito = request.cart or website._create_cart()
        carrito._cart_add(product_id=variante.id, quantity=1)
        return request.redirect('/shop/cart')
