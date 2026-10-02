"""Caché en el borde del HTML de Odoo: quién puede recibir la página guardada y cuál se guarda.

El Worker (edge/src/tienda/paginas.ts) guarda la página que Odoo dibuja para un visitante anónimo
y se la sirve a los anónimos. Dos piezas de Odoo lo hacen seguro:

* **Cookie ``dcasa_personal``.** Odoo pone ``session_id`` a TODO visitante (incluso anónimo, ver
  ``Request._save_session``), así que esa cookie no distingue nada. Al final de cada respuesta se
  mira la sesión: si tiene usuario, carrito, lista de deseos, sesión de socio o cualquier dato que
  no esté en ``CLAVES_NEUTRAS``, se pone ``dcasa_personal=1``; si ya no (cerró sesión, expiró), se
  borra. Con esa cookie el borde no sirve nada guardado: la petición va a Odoo.
* **Certificado de página anónima.** El borde pide la página a guardar sin cookies y con la
  cabecera ``X-Dcasa-Borde: <TIENDA_FEED_TOKEN>``. Con el secreto correcto, Odoo no guarda la
  sesión ni pone cookies (ni ``session_id`` ni ``frontend_lang``) y, si de verdad la dibujó para el
  usuario público sin nada propio, responde ``X-Dcasa-Borde: anonimo``. Sin esa marca el borde no
  guarda la respuesta.
"""
from odoo import models
from odoo.http import get_session_max_inactivity, request

from .pendiente import token_valido

CABECERA_BORDE = 'X-Dcasa-Borde'
MARCA_ANONIMO = 'anonimo'
COOKIE_PERSONAL = 'dcasa_personal'

# Datos de sesión que NO hacen distinta la página pública: los de toda sesión de Odoo, los que
# website_sale calcula igual para cualquier anónimo (tarifa y posición fiscal por defecto), el
# código de padrino de un enlace de socio (solo se usa al crear el pedido) y la limpieza de
# dcasa_sesiones. Cualquier otra clave con valor (``uid``, ``pre_uid``, ``sale_order_id``,
# ``website_sale_cart_quantity``, ``wishlist_ids``, ``dcasa_socio``, la tarifa elegida, el modo
# lista/cuadrícula…) vuelve personal la sesión: lo desconocido, también.
CLAVES_NEUTRAS = frozenset({
    'context', 'create_time', 'db', 'debug', 'login', 'uid', 'session_token', '_trace',
    '_trace_disable', 'geoip', 'website_sale_current_pl', 'website_sale_pricelist_time',
    'fiscal_position_id', 'dcasa_padrino', 'gc_previous_sessions',
})


def sesion_personal(session):
    """¿La sesión tiene algo de alguien (y por tanto la página puede ser distinta para él)?"""
    if session.uid:
        return True
    return any(valor for clave, valor in session.items() if clave not in CLAVES_NEUTRAS)


def pedido_por_el_borde(httprequest):
    """¿La petición la hizo el borde para guardar la página (trae el secreto)?"""
    valor = httprequest.headers.get(CABECERA_BORDE)
    return bool(valor) and token_valido(valor)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        borde = pedido_por_el_borde(request.httprequest)
        if borde:
            request.session.can_save = False  # ni se guarda la sesión ni se manda session_id
        super()._post_dispatch(response)
        if borde:
            response.headers.remove('Set-Cookie')  # frontend_lang y cualquier otra
            if not sesion_personal(request.session) and request.env.user._is_public():
                response.headers[CABECERA_BORDE] = MARCA_ANONIMO
            return
        personal = sesion_personal(request.session)
        tiene = bool(request.httprequest.cookies.get(COOKIE_PERSONAL))
        if personal != tiene:
            # Sin valor y max_age=0 la borra (delete_cookie de werkzeug no acepta la fachada de Odoo).
            response.set_cookie(
                COOKIE_PERSONAL, '1' if personal else '',
                max_age=get_session_max_inactivity(request.env) if personal else 0,
                httponly=True, samesite='Lax', secure=request.httprequest.scheme == 'https')
