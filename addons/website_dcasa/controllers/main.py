import json

from odoo import http
from odoo.addons.website_dcasa.models.black_weekend import RUTA as RUTA_BLACK_WEEKEND
from odoo.addons.website_dcasa.models.website import LATITUD, LONGITUD
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.fields import Domain
from odoo.http import request
from odoo.tools.json import scriptsafe as json_scriptsafe

# Nombre de la tienda en las migas de los datos estructurados (Odoo escribe «All Products»
# en duro, sin traducir). Igual que la miga visible de la ficha.
MIGA_TIENDA = 'Todos los productos'

# Las existencias arrancan «sin confirmar» (dcasa_catalogo vende sin stock y confirma por
# WhatsApp): decirle a Google «InStock» u «OutOfStock» sería inventarlo. Cuando haya conteo
# real de inventario, poner True y la ficha vuelve a publicar la disponibilidad de Odoo.
PUBLICAR_DISPONIBILIDAD = False

# Páginas legales: el cuerpo es una plantilla propia (views/legal_templates.xml) para que la tienda
# estática del borde (dcasa_tienda_borde) publique exactamente el mismo texto.
PAGINAS_LEGALES = {
    '/privacidad': {
        'titulo': 'Política de privacidad',
        'descripcion': "Qué datos guarda D'CASA Panamá, para qué los usa, con quién los comparte "
                       '(incluida la inteligencia artificial) y cómo ejercer tus derechos.',
        'actualizado': '1 de octubre de 2026',
        'cuerpo': 'website_dcasa.privacidad_cuerpo',
    },
    '/terminos': {
        'titulo': 'Términos y condiciones',
        'descripcion': "Cómo funcionan los precios, los pedidos y la atención de D'CASA Panamá en este sitio.",
        'actualizado': '1 de octubre de 2026',
        'cuerpo': 'website_dcasa.terminos_cuerpo',
    },
}


def _sin_disponibilidad(datos):
    """Quita ``availability`` de cualquier oferta del JSON-LD (también en ``hasVariant``)."""
    if isinstance(datos, list):
        return [_sin_disponibilidad(d) for d in datos]
    if isinstance(datos, dict):
        return {k: _sin_disponibilidad(v) for k, v in datos.items() if k != 'availability'}
    return datos


class DcasaCheckout(WebsiteSale):
    """Tienda para un cliente de Panamá.

    Dirección sin empresa ni VAT y con Panamá ya elegido; datos estructurados de la ficha sin
    disponibilidad inventada y con las migas en español.
    """

    def _prepare_product_values(self, product, category, **kwargs):
        valores = super()._prepare_product_values(product, category, **kwargs)
        if not PUBLICAR_DISPONIBILIDAD and valores.get('product_markup_data'):
            datos = json.loads(valores['product_markup_data'])
            valores['product_markup_data'] = json_scriptsafe.dumps(_sin_disponibilidad(datos), indent=2)
        return valores

    def _prepare_breadcrumb_markup_data(self, base_url, category, product_name):
        datos = super()._prepare_breadcrumb_markup_data(base_url, category, product_name)
        for miga in datos.get('itemListElement', []):
            if miga.get('position') == 1:
                miga['name'] = MIGA_TIENDA
        return datos

    def _prepare_address_form_values(self, *args, **kwargs):
        valores = super()._prepare_address_form_values(*args, **kwargs)
        valores['display_b2b_fields'] = False
        return valores

    def _get_default_country(self, order_sudo=False, **kwargs):
        pais = super()._get_default_country(order_sudo=order_sudo, **kwargs)
        return pais or request.website.company_id.country_id


def _sitemap_black_weekend(env, rule, qs):
    """/black-weekend entra al sitemap solo mientras la campaña está activa y tiene productos."""
    website = env['website'].get_current_website()
    if (not qs or qs.lower() in RUTA_BLACK_WEEKEND) and website._dcasa_black_weekend_activo() \
            and env['product.template'].search_count(website._dcasa_bw_dominio(), limit=1):
        yield {'loc': RUTA_BLACK_WEEKEND}


class DcasaTienda(http.Controller):

    @http.route('/dcasa/carrito/agregar', type='http', auth='public', website=True, methods=['POST'],
                sitemap=False)
    def agregar_al_carrito(self, product_template_id=None, product_id=None, **kwargs):
        """«Agregar» de un clic desde la portada.

        Es un formulario normal (sin JavaScript), así funciona en cualquier teléfono.
        Productos con variantes van a su ficha para elegir, salvo que el formulario ya traiga la
        variante (``product_id``, p. ej. el color destacado de Black Weekend) y lo único que se
        elige en ese producto sea esa variante.
        """
        website = request.website
        try:
            producto_id = int(product_template_id or 0)
            variante_id = int(product_id or 0)
        except ValueError:
            return request.redirect('/shop')
        if not 0 < producto_id < 2**31 or not 0 <= variante_id < 2**31:  # fuera del rango de un id
            return request.redirect('/shop')
        # Buscar (no leer) respeta las reglas de acceso: un visitante solo encuentra lo publicado.
        producto = request.env['product.template'].search(Domain.AND([
            website._dcasa_dominio_publicado(), [('id', '=', producto_id)],
        ]), limit=1)
        if not producto:
            return request.redirect('/shop')
        if variante_id:
            variante = request.env['product.product'].search(
                [('id', '=', variante_id), ('product_tmpl_id', '=', producto.id)], limit=1)
            directa = bool(variante) and website._dcasa_variante_directa(producto, variante)
        else:
            variante = producto.product_variant_id
            directa = website._dcasa_compra_directa(producto)
        permitido = bool(variante) and variante._is_add_to_cart_allowed()  # precio cero, acceso a la tienda
        if not (permitido and directa):
            # Hay que elegir algo (variante, combo...) o la tienda no lo deja comprar así: a la ficha.
            return request.redirect(producto.website_url)
        carrito = request.cart or website._create_cart()
        carrito._cart_add(product_id=variante.id, quantity=1)
        return request.redirect('/shop/cart')

    @http.route(RUTA_BLACK_WEEKEND, type='http', auth='public', website=True, sitemap=_sitemap_black_weekend)
    def black_weekend(self, **kwargs):
        """Productos de la campaña Black Weekend. Fuera de la ventana (o sin productos), no existe: 404."""
        website = request.website
        if not website._dcasa_black_weekend_activo():
            raise request.not_found()
        items = website._dcasa_bw_productos()
        if not items:
            raise request.not_found()
        return request.render('website_dcasa.pagina_black_weekend', {
            'items': items,
            'fechas': website._dcasa_bw_fechas(),
            'bw_descripcion': website._dcasa_bw_descripcion(items),
            'bw_json_ld': website._dcasa_bw_json_ld(items),
        })

    @http.route('/visitanos', type='http', auth='public', website=True, sitemap=True)
    def visitanos(self, **kwargs):
        """Página exclusiva de la tienda: dirección, mapa, cómo llegar y contacto."""
        return request.render('website_dcasa.pagina_visitanos', {'latitud': LATITUD, 'longitud': LONGITUD})

    @http.route('/privacidad', type='http', auth='public', website=True, sitemap=True)
    def privacidad(self, **kwargs):
        """Política de privacidad (Ley 81 de 2019), con el uso de inteligencia artificial."""
        return request.render('website_dcasa.pagina_legal', dict(PAGINAS_LEGALES['/privacidad']))

    @http.route('/terminos', type='http', auth='public', website=True, sitemap=True)
    def terminos(self, **kwargs):
        return request.render('website_dcasa.pagina_legal', dict(PAGINAS_LEGALES['/terminos']))

    @http.route('/whatsapp', type='http', auth='public', website=True, sitemap=False)
    def whatsapp(self, texto=None, **kwargs):
        """Enlace estable a WhatsApp para los bloques editables del sitio.

        El editor guarda el HTML tal cual: un ``wa.me/<número>`` escrito en un bloque quedaría
        congelado. ``/whatsapp`` usa siempre el número configurado en el sitio. Solo redirige a
        wa.me (o a /contactus si no hay número): no es una redirección abierta.
        """
        url = request.website._dcasa_whatsapp_url((texto or '')[:300])
        return request.redirect(url, code=302, local=url.startswith('/'))
