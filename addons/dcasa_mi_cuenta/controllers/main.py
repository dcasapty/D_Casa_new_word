"""«Mi cuenta» (/mi-cuenta): el panel del cliente, y los caminos de /socios y /my que ahora terminan aquí.

Quién entra:

* Con la sesión de socio (celular + PIN, ``dcasa_socios``): ``session['dcasa_socio'] = {id, huella}``. Si el PIN es
  temporal, se le manda a /socios/pin, como siempre.
* Con la cuenta de la tienda (usuario portal): su ficha es ``user.partner_id.commercial_partner_id``.

Todo se lee con ``sudo()`` y filtrando por esa ficha (models/mi_cuenta.py). Un pedido o una factura de otra persona
responde 404, igual que uno que no existe. A quien entra con PIN no se le enseñan cédula, dirección, teléfonos ni PDF
(los PDF traen datos personales): se le ofrece pedir la factura por WhatsApp. El usuario de la tienda sí tiene el
enlace al PDF del portal de Odoo (/my/...), que ya le dan las reglas del portal; nunca se crean ``access_token``.

Aquí no se toca la lógica del PIN ni del candado: las rutas de /socios se heredan y solo cambia a dónde llevan al
terminar.
"""
from urllib.parse import urlsplit

from odoo import http
from odoo.addons.dcasa_socios.controllers.main import SESSION_AVISO, SociosDcasa, socio_por_pin
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request

INICIO = '/mi-cuenta'
COMPRAS = '/mi-cuenta/compras'
PUNTOS = '/mi-cuenta/puntos'
DATOS = '/mi-cuenta/datos'
# Lo que pasaba antes al terminar en /socios: la cuenta del socio vivía en /socios/cuenta.
CUENTA_VIEJA = '/socios/cuenta'
TEXTO_OLVIDE = "Hola D'CASA, olvidé mi PIN de Mi cuenta. ¿Me ayudan a cambiarlo?"


def _destino(respuesta):
    """La ruta a la que redirige una respuesta, o '' si no es una redirección."""
    if getattr(respuesta, 'status_code', 200) in (301, 302, 303, 307, 308):
        return urlsplit(respuesta.headers.get('Location', '')).path
    return ''


def sesion_del_cliente():
    """(ficha, persona, tienda): la ficha comercial del cliente con sesión, la persona que entró (para saludar) y si
    entró con la cuenta de la tienda. Sin sesión: (vacío, vacío, False)."""
    Partner = request.env['res.partner'].sudo()
    usuario = request.env.user
    persona_tienda = Partner
    if usuario and not usuario._is_public():
        persona_tienda = usuario.partner_id.sudo()
    ficha_tienda = persona_tienda.commercial_partner_id
    socio = socio_por_pin()
    if socio:
        # Con las dos sesiones, manda la del PIN (como en /socios); los permisos de la tienda solo si es la misma ficha.
        misma = bool(ficha_tienda) and ficha_tienda == socio
        return socio, (persona_tienda if misma else socio), misma
    if ficha_tienda and ficha_tienda.active:
        return ficha_tienda, persona_tienda, True
    return Partner, Partner, False


class MiCuenta(http.Controller):

    # ------------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------------

    @staticmethod
    def _mc():
        return request.env['dcasa.mi.cuenta']

    def _mc_render(self, plantilla, valores=None):
        valores = dict(valores or {})
        valores.setdefault('aviso', request.session.pop(SESSION_AVISO, None))
        valores.setdefault('ficha', request.env['res.partner'])
        valores.setdefault('whatsapp', request.website._dcasa_whatsapp_url())
        respuesta = request.render(plantilla, valores)
        # Página de una persona: ni el navegador ni el borde la guardan, y no se indexa.
        respuesta.headers['Cache-Control'] = 'no-store'
        respuesta.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return respuesta

    def _mc_entrar(self, valores=None):
        """«Entra a tu cuenta»: celular + PIN (el mismo formulario de /socios), o el correo de la tienda."""
        valores = dict(valores or {})
        valores.setdefault('olvide', request.website._dcasa_whatsapp_url(TEXTO_OLVIDE))
        return self._mc_render('dcasa_mi_cuenta.entrar', valores)

    def _mc_con_sesion(self):
        """(ficha, persona, tienda, respuesta): ``respuesta`` es una redirección si hay que ir a otra parte antes."""
        ficha, persona, tienda = sesion_del_cliente()
        if not ficha:
            return ficha, persona, tienda, request.redirect(INICIO)
        if not tienda and ficha.dcasa_pin_temporal:
            return ficha, persona, tienda, request.redirect('/socios/pin')
        return ficha, persona, tienda, None

    def _mc_valores(self, ficha, persona, tienda, seccion, **extra):
        return dict(extra, ficha=ficha, tienda=tienda, seccion=seccion,
                    nombre=self._mc()._mc_primer_nombre(persona) or 'cliente')

    # ------------------------------------------------------------------------
    # Rutas
    # ------------------------------------------------------------------------

    @http.route(INICIO, type='http', auth='public', website=True, sitemap=False)
    def mi_cuenta(self, **kwargs):
        ficha, persona, tienda = sesion_del_cliente()
        if not ficha:
            return self._mc_entrar()
        if not tienda and ficha.dcasa_pin_temporal:
            return request.redirect('/socios/pin')
        datos = self._mc()._mc_inicio(ficha, request.website, request.httprequest.host_url, tienda)
        return self._mc_render('dcasa_mi_cuenta.inicio', self._mc_valores(ficha, persona, tienda, 'inicio', **datos))

    @http.route(COMPRAS, type='http', auth='public', website=True, sitemap=False)
    def compras(self, **kwargs):
        ficha, persona, tienda, salir = self._mc_con_sesion()
        if salir:
            return salir
        datos = self._mc()._mc_compras(ficha, request.website, tienda)
        return self._mc_render('dcasa_mi_cuenta.compras', self._mc_valores(ficha, persona, tienda, 'compras', **datos))

    @http.route(f'{COMPRAS}/<int:pedido_id>', type='http', auth='public', website=True, sitemap=False)
    def compra(self, pedido_id, **kwargs):
        ficha, persona, tienda, salir = self._mc_con_sesion()
        if salir:
            return salir
        pedido = self._mc()._mc_pedido(ficha, pedido_id)
        if not pedido:
            raise request.not_found()
        compra = self._mc()._mc_resumen_pedido(pedido, request.website, tienda)
        return self._mc_render('dcasa_mi_cuenta.detalle',
                               self._mc_valores(ficha, persona, tienda, 'compras', compra=compra))

    @http.route('/mi-cuenta/facturas/<int:factura_id>', type='http', auth='public', website=True, sitemap=False)
    def factura(self, factura_id, **kwargs):
        ficha, persona, tienda, salir = self._mc_con_sesion()
        if salir:
            return salir
        Mc = self._mc()
        factura = Mc._mc_factura(ficha, factura_id)
        if not factura:
            raise request.not_found()
        if not Mc._mc_es_suelta(factura):
            # Viene de un pedido: se ve en el pedido, si ese pedido es de esta ficha.
            pedido = factura.invoice_line_ids.sale_line_ids.order_id[:1]
            if Mc._mc_pedido(ficha, pedido.id):
                return request.redirect(f'{COMPRAS}/{pedido.id}')
            raise request.not_found()
        compra = Mc._mc_resumen_factura(factura, request.website, tienda)
        return self._mc_render('dcasa_mi_cuenta.detalle',
                               self._mc_valores(ficha, persona, tienda, 'compras', compra=compra))

    @http.route(PUNTOS, type='http', auth='public', website=True, sitemap=False)
    def puntos(self, **kwargs):
        ficha, persona, tienda, salir = self._mc_con_sesion()
        if salir:
            return salir
        puntos = self._mc()._mc_puntos(ficha, request.httprequest.host_url)
        valores = self._mc_valores(ficha, persona, tienda, 'puntos', puntos=puntos)
        return self._mc_render('dcasa_mi_cuenta.puntos', valores)

    @http.route(DATOS, type='http', auth='public', website=True, sitemap=False)
    def datos(self, **kwargs):
        ficha, persona, tienda, salir = self._mc_con_sesion()
        if salir:
            return salir
        datos = self._mc()._mc_datos(ficha, persona, tienda)
        return self._mc_render('dcasa_mi_cuenta.datos', self._mc_valores(ficha, persona, tienda, 'datos', datos=datos))


class SociosMiCuenta(SociosDcasa):
    """Las rutas de /socios, con su misma lógica (PIN, candado, Turnstile, registro), terminan en Mi cuenta."""

    @staticmethod
    def _a_mi_cuenta(respuesta, destino):
        """Si ``respuesta`` lleva a la cuenta vieja (/socios/cuenta), lleva a ``destino``; si no, la deja igual."""
        if _destino(respuesta) == CUENTA_VIEJA:
            return request.redirect(destino)
        return respuesta

    @http.route()
    def inicio(self, **kwargs):
        if self._socio():
            return request.redirect(PUNTOS)
        return super().inicio(**kwargs)

    @http.route()
    def entrar(self, celular='', pin='', **kwargs):
        respuesta = self._a_mi_cuenta(super().entrar(celular=celular, pin=pin, **kwargs), INICIO)
        if kwargs.get('origen') == 'mi-cuenta' and getattr(respuesta, 'qcontext', None) is not None:
            # El error (PIN equivocado, candado…) se enseña en la misma página «Entra a tu cuenta».
            respuesta.template = 'dcasa_mi_cuenta.entrar'
            respuesta.qcontext.setdefault('ficha', request.env['res.partner'])
            respuesta.qcontext.setdefault('whatsapp', request.website._dcasa_whatsapp_url())
            respuesta.qcontext.setdefault('olvide', request.website._dcasa_whatsapp_url(TEXTO_OLVIDE))
            respuesta.headers['Cache-Control'] = 'no-store'
        return respuesta

    @http.route()
    def salir(self, **kwargs):
        respuesta = super().salir(**kwargs)
        if '/web/session/logout' in respuesta.headers.get('Location', ''):
            # La sesión del socio era la de la tienda: se cierra la de la tienda y se vuelve a Mi cuenta.
            return request.redirect(f'/web/session/logout?redirect={INICIO}')
        return request.redirect(INICIO)

    @http.route()
    def registro(self, **datos):
        return self._a_mi_cuenta(super().registro(**datos), INICIO)

    @http.route()
    def activar(self, **datos):
        return self._a_mi_cuenta(super().activar(**datos), PUNTOS)

    @http.route()
    def cuenta(self, **kwargs):
        return request.redirect(PUNTOS)

    @http.route()
    def canjear(self, premio_id=None, volver='cuenta', **kwargs):
        return self._a_mi_cuenta(super().canjear(premio_id=premio_id, volver=volver, **kwargs), PUNTOS)

    @http.route()
    def cancelar_canje(self, codigo, volver='cuenta', **kwargs):
        return self._a_mi_cuenta(super().cancelar_canje(codigo, volver=volver, **kwargs), PUNTOS)

    @http.route()
    def cambiar_pin(self, **datos):
        return self._a_mi_cuenta(super().cambiar_pin(**datos), DATOS)


class PortalMiCuenta(CustomerPortal):
    """/my y /my/home: el cliente de la tienda (usuario portal) va a Mi cuenta; el equipo sigue igual."""

    @http.route()
    def home(self, **kw):
        if request.env.user.share:
            return request.redirect(INICIO)
        return super().home(**kw)
