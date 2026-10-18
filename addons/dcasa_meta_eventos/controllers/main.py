"""Checkout, confirmación y carrito: lo justo para Meta, y solo con consentimiento.

* Checkout y confirmación: con «Ventas de la web» encendido y con el consentimiento A (aviso de cookies aceptado) o
  la casilla B de esa compra, se guardan en el pedido ``_fbp``, ``_fbc`` (llegan en las cookies: el borde las
  reenvía), la IP (``proxy_mode``), el navegador y la página. Sin consentimiento no se toma nada, y si la persona lo
  retiró después (Preferencias de cookies › Solo las necesarias) se borra lo que se había tomado.
* Nada de esto hace fallar el checkout, el carrito ni la confirmación: un fallo de Meta queda en el registro (sin
  datos de la persona) y la página sigue.
* El píxel recibe los ids de las líneas en un ``<script type="application/json" id="dcasa-meta-datos">``
  (InitiateCheckout y AddPaymentInfo). Nunca ``Purchase``: lo reporta el servidor cuando la factura queda pagada.
* Carrito de Odoo: al seguimiento nativo (``tracking_info``) se le suma el id de la variante, sin tocar sus claves.
* ``/dcasa/meta/consentimiento-compra``: la casilla B del checkout (desmarcada de fábrica).
* ``/cookie-policy`` lleva a la política de D'CASA (``/privacidad#cookies``): al encender el aviso de cookies (lo
  enciende el píxel) Odoo publica esa página con su texto genérico (Google Analytics, anuncios de Google, chat en vivo),
  que no describe a D'CASA, y su JS le pone un enlace «Política de cookies» en el pie.
"""
import functools
import json
import logging
import re
from urllib.parse import unquote

from odoo import fields, http
from odoo.addons.website_sale.controllers.cart import Cart
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request, route
from odoo.tools.json import scriptsafe as json_scriptsafe

from ..models import meta_api
from ..models.meta_evento import leer_config

_logger = logging.getLogger(__name__)

COOKIE_AVISO = 'website_cookies_bar'
RE_COOKIE_AVISO = re.compile(r'(?:^|;)\s*website_cookies_bar=([^;]*)')
RUTA_CHECKOUT = '/shop/checkout'


def cookie_del_aviso():
    """El texto de la cookie del aviso (``{"required": true, "optional": …}``), tal como la escribe Odoo.

    Werkzeug 3.1 descarta las cookies sin comillas que llevan comillas dentro (justo esta); la 3.0 de la imagen no.
    Si no viene en las cookies ya leídas, se busca en la cabecera tal cual llegó.
    """
    valor = request.httprequest.cookies.get(COOKIE_AVISO)
    if valor is None:
        encontrado = RE_COOKIE_AVISO.search(request.httprequest.headers.get('Cookie') or '')
        valor = encontrado.group(1).strip() if encontrado else None
    return valor


def consentimiento_navegador():
    """¿Quien visita aceptó las cookies opcionales en el aviso del sitio (consentimiento A)?

    No se usa ``_is_allowed_cookie('optional')`` de Odoo: con el aviso apagado da «sí» a todos.
    """
    if not request.website.cookies_bar:
        return False
    texto = cookie_del_aviso() or '{}'
    for intento in (texto, unquote(texto)):
        try:
            valor = json.loads(intento)
        except ValueError:
            continue
        return isinstance(valor, dict) and valor.get('optional') is True
    return False


def url_de_la_pagina(ruta=None):
    """La dirección pública de la página (para ``event_source_url``), sin parámetros."""
    base = request.website._dcasa_url_publica() or request.httprequest.host_url.rstrip('/')
    return base + (ruta or request.httprequest.path)


def sin_fallar(que, defecto):
    """Decorador: lo de Meta nunca hace fallar una página de la tienda. El error queda en el registro, limpio (sin
    IP, correos, cookies de Meta ni el token: ``meta_api.limpiar_error``), y se devuelve ``defecto``."""
    def decorador(funcion):
        @functools.wraps(funcion)
        def envuelta(*args, **kwargs):
            try:
                with request.env.cr.savepoint():
                    return funcion(*args, **kwargs)
            except Exception as error:  # noqa: BLE001 — Meta nunca frena una venta
                _logger.warning('Meta: no se pudo %s; la página sigue sin eso: %s', que,
                                meta_api.limpiar_error(f'{type(error).__name__}: {error}'))
                return defecto
        return envuelta
    return decorador


@sin_fallar('tomar los datos del navegador del pedido', False)
def capturar_navegador(pedido, ruta=None):
    """Guarda en el pedido los datos del navegador para el Purchase, solo con «Ventas de la web» y consentimiento.

    Sin consentimiento (nunca lo dio, o lo retiró después en «Preferencias de cookies») borra lo que se hubiera
    tomado antes en ese pedido: así no sale con la compra.
    """
    if not pedido or not leer_config(request.env)['capi_web']:
        return False
    pedido = pedido.sudo()
    if not (consentimiento_navegador() or pedido.dcasa_meta_consentimiento_compra):
        if pedido.dcasa_meta_consentimiento_navegador:
            pedido._dcasa_meta_limpiar_navegador()
        return False
    galletas = request.httprequest.cookies
    pedido._dcasa_meta_guardar_navegador(
        galletas.get('_fbp'), galletas.get('_fbc'), request.httprequest.user_agent.string,
        request.httprequest.remote_addr, url_de_la_pagina(ruta))
    return True


@sin_fallar('preparar los datos del píxel del pedido', None)
def datos_del_pixel(pedido, evento):
    """JSON (seguro dentro de <script>) de los ids del pedido para el píxel, o ``None`` con el píxel apagado."""
    if not pedido or not request.website._dcasa_meta_pixel_html():
        return None
    return json_scriptsafe.dumps(pedido.sudo()._dcasa_meta_datos_pagina(evento))


class DcasaMetaCheckout(WebsiteSale):

    @route()
    def shop_checkout(self, try_skip_step=None, **query_params):
        respuesta = super().shop_checkout(try_skip_step=try_skip_step, **query_params)
        capturar_navegador(request.cart)
        return respuesta

    def _prepare_checkout_page_values(self, order_sudo, **kwargs):
        valores = super()._prepare_checkout_page_values(order_sudo, **kwargs)
        casilla = bool(order_sudo) and leer_config(request.env)['capi_web']
        valores['dcasa_meta_casilla'] = casilla
        valores['dcasa_meta_casilla_marcada'] = bool(casilla and order_sudo.sudo().dcasa_meta_consentimiento_compra)
        valores['dcasa_meta_datos'] = datos_del_pixel(order_sudo, 'InitiateCheckout')
        return valores

    @route()
    def shop_payment_confirmation(self, **post):
        respuesta = super().shop_payment_confirmation(**post)
        pedido_id = request.session.get('sale_last_order_id')
        if pedido_id:
            capturar_navegador(request.env['sale.order'].sudo().browse(pedido_id).exists())
        return respuesta

    def _prepare_shop_payment_confirmation_values(self, order):
        valores = super()._prepare_shop_payment_confirmation_values(order)
        valores['dcasa_meta_datos'] = datos_del_pixel(order, 'AddPaymentInfo')
        return valores


class DcasaMetaCarrito(Cart):

    def _get_tracking_information(self, order_sudo, line_ids):
        """El seguimiento nativo del carrito + ``dcasa_meta_id`` (id de la variante), sin tocar las claves de Odoo."""
        informacion = super()._get_tracking_information(order_sudo, line_ids)
        self._dcasa_meta_marcar_ids(informacion, order_sudo, line_ids)
        return informacion

    @staticmethod
    @sin_fallar('agregar el id de la variante al carrito', None)
    def _dcasa_meta_marcar_ids(informacion, order_sudo, line_ids):
        if not request.website._dcasa_meta_pixel_html():
            return
        lineas = order_sudo.order_line.filtered(lambda linea: linea.id in line_ids)
        for dato, linea in zip(informacion, lineas, strict=False):
            dato['dcasa_meta_id'] = str(linea.product_id.id)


class DcasaMetaConsentimiento(http.Controller):

    @http.route('/dcasa/meta/consentimiento-compra', type='jsonrpc', auth='public', website=True,
                methods=['POST'], sitemap=False)
    def consentimiento_compra(self, acepta=False, **kwargs):
        """La casilla B del checkout. Vale para ESTA compra; en la ficha solo si es la de quien compra.

        * Con sesión: la ficha comercial del pedido tiene que ser la de quien entró.
        * Sin sesión: solo si la ficha del pedido es nueva de este carrito (no una ficha que ya existía: así nadie
          marca el consentimiento de otra persona escribiendo su celular o su correo).
        Desmarcarla quita el consentimiento de la compra (y el de la ficha, si es de este carrito y lo dio en la web),
        y los datos del navegador si no aceptó las cookies.
        """
        pedido = request.cart
        if not pedido or not leer_config(request.env)['capi_web']:
            return {'ok': False}
        pedido = pedido.sudo()
        acepta = acepta is True
        pedido.write({'dcasa_meta_consentimiento_compra': fields.Datetime.now() if acepta else False})
        ficha = self._dcasa_ficha_de_quien_compra(pedido)
        if acepta:
            capturar_navegador(pedido, RUTA_CHECKOUT)
            if ficha:
                ficha.sudo()._dcasa_meta_registrar_consentimiento('web', request.env.user)
        else:
            if not consentimiento_navegador():
                pedido._dcasa_meta_limpiar_navegador()
            if ficha and ficha.sudo().dcasa_meta_consentimiento_origen == 'web':
                ficha.sudo()._dcasa_meta_retirar_consentimiento(limpiar_navegador=False)
        return {'ok': True, 'ficha': bool(ficha)}

    @staticmethod
    def _dcasa_ficha_de_quien_compra(pedido):
        """La ficha comercial del pedido si es, sin duda, la de quien está comprando; si no, vacío."""
        partner = pedido.partner_id
        comercial = partner.commercial_partner_id
        usuario = request.env.user
        if not usuario._is_public():
            return comercial if usuario.partner_id.commercial_partner_id == comercial else False
        if (partner == comercial and partner.create_date and pedido.create_date
                and partner.create_date >= pedido.create_date):
            return comercial
        return False


class DcasaPoliticaDeCookies(http.Controller):

    @http.route('/cookie-policy', type='http', auth='public', website=True, sitemap=False)
    def politica_de_cookies(self, **kwargs):
        """La política de cookies de D'CASA es la sección «Cookies» de su política de privacidad, no el texto genérico
        que Odoo publica al encender el aviso."""
        return request.redirect('/privacidad#cookies', code=301)
