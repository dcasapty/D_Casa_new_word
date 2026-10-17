import json

from odoo import http
from odoo.addons.account.controllers.terms import TermsController
from odoo.addons.dcasa_base.models.codigo_publico import normalizar_codigo_publico
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

# Páginas legales: el cuerpo es una plantilla propia (views/legal_templates.xml); título y
# descripción, aquí.
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

    def _validate_address_values(self, address_values, partner_sudo, address_type, use_delivery_as_billing,
                                 required_fields, **kwargs):
        """Además de lo de Odoo: el celular bien escrito y el correo sin errores de dedo («¿quisiste decir…?»). Ahí le
        llegan su factura y cómo ver sus puntos (dcasa_contactos, 2026-10-16)."""
        invalidos, faltantes, mensajes = super()._validate_address_values(
            address_values, partner_sudo, address_type, use_delivery_as_billing, required_fields, **kwargs)
        Partner = request.env['res.partner'].sudo()
        errores = Partner._dcasa_errores_de_contacto(address_values.get('phone'), address_values.get('email'))
        for campo, mensaje in errores.items():
            if campo not in invalidos:
                invalidos.add(campo)
                mensajes.append(mensaje)
        # Sin cuenta, un celular, correo o RUC que ya es de una ficha no crea otra (una persona, una ficha) ni cae en
        # la de esa persona (revisión adversarial, 2026-10-17). Se avisa en el formulario, sin decir de quién es; si no,
        # el candado de dcasa_contactos fallaba al crear y «Confirmar» no avanzaba sin decir nada.
        cart = request.cart
        if not partner_sudo and cart and cart._is_anonymous_cart():
            for campo, etiqueta in (('phone', 'celular'), ('email', 'correo'), ('vat', 'ruc')):
                valor = address_values.get(campo)
                if not valor or campo in invalidos:
                    continue
                ficha = Partner._dcasa_buscar_ficha(**{etiqueta: valor})
                if ficha:
                    invalidos.add(campo)
                    mensajes.append(Partner._dcasa_mensaje_duplicado(etiqueta, valor, ficha))
        return invalidos, faltantes, mensajes

    # Sin ``_create_new_address`` propio (revisión adversarial, 2026-10-17): colgar la dirección de un visitante sin
    # cuenta de la ficha que ya tenía ese celular, correo o RUC le daba en el checkout las direcciones, los teléfonos y
    # los correos de ESA persona (Odoo enseña y deja usar todas las de la ficha comercial), le dejaba editarlas y le
    # ponía la compra en su «Mi cuenta». Un dato escrito en la tienda no prueba quién es la persona.
    # Ver tests/test_privacidad_checkout.py.


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

    @http.route('/codigo/<string:codigo>', type='http', auth='public', website=True, sitemap=False)
    def producto_por_codigo(self, codigo, **kwargs):
        """Lo que abre el QR de un producto: ``/codigo/DC-K7M4PX`` lleva a su ficha en la tienda.

        Solo productos publicados. Un código que no existe, que se regeneró o de un producto que no está en la
        tienda lleva a la tienda, sin decir cuál de los tres es. Solo redirige a una dirección propia."""
        normal = normalizar_codigo_publico(codigo)
        producto = request.env['product.template'].search(Domain.AND([
            request.website._dcasa_dominio_publicado(), [('dcasa_codigo_publico', '=', normal)],
        ]), limit=1) if normal else None
        return request.redirect(producto.website_url if producto else '/shop', code=302)

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


class TerminosDcasa(TermsController):
    """/terms de Odoo es una plantilla con términos inventados (en inglés: «payable within 21 days… interest») y la
    factura y el portal la enlazan. Lleva a los términos reales de D'CASA (/terminos)."""

    @http.route('/terms', type='http', auth='public', website=True, sitemap=False)
    def terms_conditions(self, **kwargs):
        return request.redirect('/terminos', code=301, local=True)
