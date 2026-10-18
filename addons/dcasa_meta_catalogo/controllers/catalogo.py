"""``GET /dcasa/meta/catalogo.csv?feed=<id>&token=<token>``: el catálogo que Meta lee de forma programada.

* Sin la capa del sitio (``website=True`` pondría la cookie ``frontend_lang``) y sin sesión (``save_session=False``):
  la respuesta no lleva ``Set-Cookie``.
* El token se compara en tiempo constante (``_find_and_check_feed_access`` del feed de Google de Odoo). Sin feed o con
  uno que no existe: 404; token malo: 403; un feed que no es de Meta: 404; apagado: 404.
* Sin dirección pública https del sitio (``web.base.url`` local): 503 con un texto claro; nunca se le dan a Meta
  enlaces de la máquina.
* ``Cache-Control: no-store``: el borde no la guarda (tampoco está en su caché de páginas) y la caché que cuenta es la
  de Odoo (``product.feed._dcasa_meta_servir``). Sin gzip: no está verificado que Meta lo acepte; Cloudflare ya
  comprime en el camino.
"""
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from odoo import http
from odoo.addons.website_sale.controllers.product_feed import ProductFeed
from odoo.exceptions import LockError
from odoo.http import request

RUTA = '/dcasa/meta/catalogo.csv'
CABECERAS_COMUNES = [
    ('Cache-Control', 'no-store'),
    ('X-Robots-Tag', 'noindex, nofollow'),
    ('X-Content-Type-Options', 'nosniff'),
]


def _texto(mensaje, status, *extra):
    return request.make_response(mensaje, status=status, headers=[
        ('Content-Type', 'text/plain; charset=utf-8'), *CABECERAS_COMUNES, *extra])


class DcasaMetaCatalogo(http.Controller):

    @http.route(RUTA, type='http', auth='public', methods=['GET', 'HEAD'], save_session=False, sitemap=False,
                readonly=False)
    def catalogo(self, feed='', token='', **kwargs):
        if not isinstance(feed, str) or not feed.isdigit() or not 0 < int(feed) < 2 ** 31:
            return _texto('No existe ese catálogo.', 404)
        try:
            feed_sudo = ProductFeed()._find_and_check_feed_access(feed, token if isinstance(token, str) else '')
        except (BadRequest, NotFound):
            return _texto('No existe ese catálogo.', 404)
        except Forbidden:
            return _texto('La dirección del catálogo no es válida.', 403)
        if feed_sudo.target != 'meta':
            return _texto('No existe ese catálogo.', 404)
        if not feed_sudo.dcasa_activo:
            return _texto('El catálogo para Meta está apagado.', 404)
        if not feed_sudo._dcasa_meta_base():
            return _texto(
                'El catálogo todavía no tiene dirección pública: falta fijar web.base.url con el dominio https del '
                'sitio.', 503, ('Retry-After', '3600'))
        try:
            contenido = feed_sudo._dcasa_meta_servir()
        except LockError:
            return _texto('El catálogo se está preparando. Vuelve a intentar en un minuto.', 503,
                          ('Retry-After', '60'))
        return request.make_response(contenido, headers=[
            ('Content-Type', 'text/csv; charset=utf-8'),
            ('Content-Disposition', 'inline; filename="catalogo-meta.csv"'),
            *CABECERAS_COMUNES,
        ])
