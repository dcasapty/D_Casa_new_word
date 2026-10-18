"""Lo que el sitio público dibuja para el píxel (y nada más), y la compuerta de la política de privacidad.

El layout solo lleva ``data-dcasa-meta-pixel="<id>"`` cuando se cumple TODO: el píxel encendido con un ID válido, el
servidor es el de producción (en staging no hay píxel), la política de privacidad publicada tiene la sección de Meta,
el sitio muestra el aviso de cookies, quien visita no es del personal y la página no es de las que llevan datos de la
persona en su dirección o en su contenido (``pagina_sin_pixel``). Ni ``<script src=connect.facebook.net>`` ni
``<noscript>``: el JS (``static/src/js/meta_pixel.js``) carga el píxel solo después del consentimiento. Los datos de
la ficha van en ``data-*`` iguales para todos los visitantes, así sirven también en la página guardada en el borde.

Por qué hay páginas sin píxel: el píxel de Meta le manda a Meta la dirección COMPLETA de la página en cada evento
(y la de la página anterior). Un enlace del portal lleva ``?access_token=…`` (abre el pedido o la factura con nombre,
dirección y celular), una búsqueda puede traer un correo o un celular escrito por la persona, y las páginas de la
cuenta, del inicio de sesión y del formulario de dirección tienen esos datos a la vista. En esas páginas no se dibuja
el píxel y, mientras el píxel está encendido, llevan ``<meta name="referrer" content="origin">`` para que la página
siguiente (donde sí hay píxel) no reciba esa dirección como «de dónde vino».
"""
import logging
import re

from odoo import api, models, tools
from odoo.http import request

from . import meta_api
from .meta_evento import leer_config

_logger = logging.getLogger(__name__)

SECCION_PRIVACIDAD = re.compile(r'''\bid\s*=\s*["']privacidad-meta["']''')
PLANTILLA_PRIVACIDAD = 'website_dcasa.privacidad_cuerpo'

# Cuenta del cliente, portal de Odoo, Socios, inicio de sesión y claves, pagos, Brian, el panel y los formularios con
# correo y celular (dirección del checkout y contacto). Con o sin prefijo de idioma (/en/my…).
RUTAS_SIN_PIXEL = re.compile(
    r'^(?:/[a-z]{2}(?:_[a-z]{2})?)?/(?:my|mi-cuenta|socios|web|odoo|payment|brian|contactus|shop/address)(?:/|$)',
    re.IGNORECASE)
# Los parámetros de campaña (los mismos que el borde ignora) sí sirven para medir: con ellos hay píxel.
PARAMETROS_DE_CAMPANA = re.compile(r'^(?:utm_[a-z_]+|gclid|fbclid|msclkid|gbraid|wbraid)$')
RE_DATO_DE_PERSONA = re.compile(r'@|\d{7,}')  # un correo o un celular (7 dígitos o más, sin separadores)
RE_SEPARADORES = re.compile(r'[\s().+\-/]')


def pagina_sin_pixel(httprequest):
    """¿Esta página lleva datos de la persona en su dirección o en su contenido? (ver arriba)."""
    if RUTAS_SIN_PIXEL.match(httprequest.path or ''):
        return True
    for nombre, valor in httprequest.args.items(multi=True):
        if PARAMETROS_DE_CAMPANA.match(nombre):
            continue
        if 'token' in nombre.lower() or RE_DATO_DE_PERSONA.search(RE_SEPARADORES.sub('', valor or '')):
            return True
    return False


class Website(models.Model):
    _inherit = 'website'

    def write(self, vals):
        """El aviso de cookies cambia el HTML de todas las páginas (y si el píxel se dibuja): el borde las vuelve a
        armar. Sin sudo: solo anota «regenerar todo» en la tabla interna del borde."""
        resultado = super().write(vals)
        if 'cookies_bar' in vals:
            self.env['dcasa.tienda.pendiente']._dcasa_marcar([0], 'meta')
        return resultado

    def _dcasa_meta_pixel_del_sitio(self):
        """ID del píxel si el SITIO cumple las condiciones (encendido, producción, aviso de cookies, política y visita
        que no es del personal), sin mirar la página; si no, ``None``."""
        self.ensure_one()
        config = leer_config(self.env)
        if not (config['pixel_activo'] and meta_api.RE_PIXEL.match(config['pixel_id']) and self.cookies_bar):
            return None
        if not meta_api.es_produccion():
            return None  # staging, local y pruebas: sin píxel (decisión de la dueña, docs/META_EVENTOS.md)
        if request and request.env.user._is_internal():
            return None  # el personal con sesión no cuenta como visita (ni se rastrea)
        if not self._dcasa_meta_privacidad_lista(self.id):
            return None
        return config['pixel_id']

    def _dcasa_meta_pixel_html(self):
        """ID del píxel para el atributo del layout, o ``None`` si falta una sola de las condiciones o si la página
        lleva datos de la persona (``pagina_sin_pixel``)."""
        pixel = self._dcasa_meta_pixel_del_sitio()
        if pixel and request and pagina_sin_pixel(request.httprequest):
            return None
        return pixel

    def _dcasa_meta_referer_corto(self):
        """``True`` en una página sin píxel por sus datos, con el píxel encendido: que la página siguiente no reciba
        su dirección como «de dónde vino» (``<meta name="referrer" content="origin">``). Apagado, nada cambia."""
        return bool(request and pagina_sin_pixel(request.httprequest) and self._dcasa_meta_pixel_del_sitio())

    def _dcasa_meta_ficha(self, combination_info):
        """``data-*`` de la ficha para ``ViewContent``: id de la variante mostrada (contrato 2.1), el precio que dibuja
        la página (sin ITBMS) y la moneda. Vacío con el píxel apagado: la página no lleva nada de Meta."""
        self.ensure_one()
        producto_id = (combination_info or {}).get('product_id')
        if not producto_id or not self._dcasa_meta_pixel_html():
            return {}
        moneda = combination_info.get('currency')
        return {
            'data-dcasa-meta-id': str(producto_id),
            'data-dcasa-meta-valor': '%.2f' % (combination_info.get('price') or 0.0),
            'data-dcasa-meta-moneda': moneda.name if moneda else '',
        }

    @api.model
    def _dcasa_meta_privacidad_lista(self, website_id=None):
        """¿La política de privacidad publicada ya tiene la sección de Meta (``id="privacidad-meta"``)?

        Se renderiza el cuerpo real (``website_dcasa.privacidad_cuerpo``) con la versión de ese sitio. El resultado
        queda en la caché de plantillas: se vuelve a mirar en cuanto cambia cualquier vista.
        """
        if not website_id:
            website_id = (self[:1] or self.get_current_website()).id
        return self._dcasa_meta_privacidad_en_cache(website_id)

    @api.model
    @tools.ormcache('website_id', cache='templates')
    def _dcasa_meta_privacidad_en_cache(self, website_id):
        """Si el cuerpo de la política no se puede dibujar solo (por ejemplo, un cambio le agrega una variable), se
        responde «no está lista»: el píxel no se dibuja y las ventas no salen, pero ninguna página del sitio se cae
        (esto se mira en cada página con el píxel encendido) ni el cron falla."""
        try:
            html = self.env['ir.qweb'].sudo().with_context(website_id=website_id)._render(PLANTILLA_PRIVACIDAD, {})
        except Exception as error:  # noqa: BLE001 — se cierra la compuerta, nunca se rompe el sitio
            _logger.warning('Meta: no se pudo revisar la política de privacidad (%s); el píxel y las ventas quedan '
                            'sin salir hasta que se arregle.', type(error).__name__)
            return False
        return bool(SECCION_PRIVACIDAD.search(str(html)))
