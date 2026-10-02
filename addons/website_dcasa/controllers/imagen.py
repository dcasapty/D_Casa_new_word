"""``GET /dcasa/img/<modelo>/<id>/<campo>/<ancho>.<webp|jpg>?v=<versión>`` (models/imagen.py)."""
import logging

from odoo import http
from odoo.addons.website_dcasa.models.imagen import ANCHOS, FORMATOS, FUENTES
from odoo.http import request

_logger = logging.getLogger(__name__)

UN_ANIO = 'public, max-age=31536000, immutable'


def _no_existe():
    return request.make_response('Not Found', status=404, headers=[
        ('Content-Type', 'text/plain'), ('Cache-Control', 'no-store')])


class DcasaImagen(http.Controller):

    def _dcasa_plantilla(self, registro):
        """Plantilla de la que depende que la foto sea pública."""
        if registro._name == 'product.template':
            return registro
        if registro._name == 'product.product':
            return registro.product_tmpl_id if registro.active else registro.browse()
        return registro.product_tmpl_id or registro.product_variant_id.product_tmpl_id

    @http.route('/dcasa/img/<string:modelo>/<int:res_id>/<string:campo>/<string:archivo>', type='http',
                auth='public', methods=['GET', 'HEAD'], save_session=False)
    def imagen(self, modelo, res_id, campo, archivo, v=None, **kwargs):
        ancho, _punto, formato = archivo.partition('.')
        if (modelo, campo) not in FUENTES or formato not in FORMATOS or not ancho.isdigit() \
                or int(ancho) not in ANCHOS or not 0 < res_id < 2**31:
            return _no_existe()
        ancho = int(ancho)
        # Sin website=True: esa capa pone la cookie frontend_lang y el borde no guarda nada con cookie.
        website = request.env['website'].get_current_website()
        # sudo: el permiso real es «publicado en este sitio», el mismo para todos (la respuesta es pública).
        registro = request.env[modelo].sudo().browse(res_id).exists()
        plantilla = registro and self._dcasa_plantilla(registro)
        # El dominio del visitante anónimo, sea quien sea el que pide: la respuesta se comparte en el borde.
        publicado = website.with_user(website.user_id)._dcasa_dominio_publicado()
        if not plantilla or not plantilla.filtered_domain(publicado):
            return _no_existe()
        adjunto = website._dcasa_img_adjuntos([(modelo, res_id, FUENTES[(modelo, campo)])]).get(
            (modelo, res_id, FUENTES[(modelo, campo)]))
        if not adjunto or not adjunto.checksum:
            return _no_existe()
        version = adjunto.checksum[:12]
        if v != version:
            # Sin versión o con una vieja (foto cambiada): a la URL vigente, que sí es inmutable.
            destino = f'/dcasa/img/{modelo}/{res_id}/{campo}/{ancho}.{formato}?v={version}'
            respuesta = request.redirect(destino, code=302, local=True)
            respuesta.headers['Cache-Control'] = 'no-cache'
            return respuesta
        etag = f'"{version}-{ancho}.{formato}"'
        cabeceras = [('Cache-Control', UN_ANIO), ('ETag', etag), ('X-Content-Type-Options', 'nosniff')]
        if etag in (request.httprequest.headers.get('If-None-Match') or ''):
            return request.make_response(b'', status=304, headers=cabeceras)
        try:
            datos = request.env['dcasa.imagen.variante']._dcasa_obtener(adjunto, ancho, formato)
        except Exception:  # Pillow no la abre (SVG, archivo dañado): que la sirva Odoo tal cual
            _logger.warning('No se pudo convertir la foto %s/%s/%s', modelo, res_id, campo, exc_info=True)
            respuesta = request.redirect(f'/web/image/{modelo}/{res_id}/{campo}', code=302, local=True)
            respuesta.headers['Cache-Control'] = 'no-cache'
            return respuesta
        return request.make_response(datos, headers=[
            ('Content-Type', FORMATOS[formato]), ('Content-Length', str(len(datos))), *cabeceras])
