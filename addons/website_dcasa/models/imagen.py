"""Fotos de producto en WebP/JPEG al ancho justo (`/dcasa/img/...`), generadas una sola vez.

Odoo 19 sirve cada foto en un solo formato (el que se subió) y en tamaños fijos (128-1920); no hace
WebP para el navegador que lo acepta ni elige formato. Aquí:

* URL: ``/dcasa/img/<modelo>/<id>/<campo>/<ancho>.<webp|jpg>?v=<checksum[:12]>``. La versión es el
  checksum del adjunto de la foto original: cambia solo si cambia la foto (no el precio), así que la
  respuesta es ``immutable`` por un año y el borde la guarda (edge/src/routing.ts).
* Origen: siempre la foto más grande guardada (``image_1920`` / ``image_variant_1920``); nunca se
  agranda (si el original es más chico, se re-codifica a su tamaño).
* Se genera **una vez** por (foto, ancho, formato): el resultado queda en ``dcasa.imagen.variante``
  (adjunto, o sea R2 con ``dcasa_adjuntos_r2``) para que el contenedor de 1/4 vCPU no vuelva a
  redimensionar tras un reinicio ni cuando la caché del borde se vacía o no existe (workers.dev).
  Cuando la foto cambia, las variantes de la versión anterior se borran (el objeto de R2 lo recoge
  el cron de 45 días).
* Solo productos publicados en el sitio (y sus variantes y fotos extra); lo demás, 404.
"""
import base64
import io
import logging

from PIL import Image, WebPImagePlugin  # noqa: F401 — odoo.tools.image deja solo los formatos que registra

from odoo import api, fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)

ANCHOS = (256, 512, 1024, 1600)
FORMATOS = {'webp': 'image/webp', 'jpg': 'image/jpeg'}
CALIDAD = {'webp': 80, 'jpg': 82}
# (modelo, campo de la URL) → campo binario de origen con el adjunto. Nada fuera de esta lista.
FUENTES = {
    ('product.template', 'image_1920'): 'image_1920',
    ('product.product', 'image_variant_1920'): 'image_variant_1920',
    ('product.image', 'image_1920'): 'image_1920',
}
_MEMO = '_dcasa_img_versiones'


def codificar(datos, ancho, formato):
    """Bytes de la foto ``datos`` a ``ancho`` px (sin agrandar) en ``webp`` o ``jpg``, sin metadatos."""
    with Image.open(io.BytesIO(datos)) as original:
        original.load()
        imagen = original
        if imagen.width > ancho:
            alto = max(1, round(imagen.height * ancho / imagen.width))
            imagen = imagen.resize((ancho, alto), Image.LANCZOS)
        transparente = imagen.mode in ('RGBA', 'LA', 'PA') or (
            imagen.mode == 'P' and 'transparency' in imagen.info)
        salida = io.BytesIO()
        if formato == 'webp':
            imagen = imagen.convert('RGBA' if transparente else 'RGB')
            imagen.save(salida, format='WEBP', quality=CALIDAD['webp'], method=4)
        else:
            if transparente:
                # Las fotos del catálogo van sobre fondo blanco; el JPEG no tiene canal alfa.
                rgba = imagen.convert('RGBA')
                fondo = Image.new('RGB', rgba.size, (255, 255, 255))
                fondo.paste(rgba, mask=rgba.getchannel('A'))
                imagen = fondo
            else:
                imagen = imagen.convert('RGB')
            imagen.save(salida, format='JPEG', quality=CALIDAD['jpg'], optimize=True, progressive=True)
        return salida.getvalue()


class DcasaImagenVariante(models.Model):
    _name = 'dcasa.imagen.variante'
    _description = 'Foto de producto redimensionada (WebP/JPEG) para el sitio'
    _log_access = False

    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    res_field = fields.Char(required=True)
    version = fields.Char(required=True)
    ancho = fields.Integer(required=True)
    formato = fields.Char(required=True)
    datos = fields.Binary(attachment=True, required=True)

    _variante_unica = models.Constraint(
        'UNIQUE(res_model, res_id, res_field, version, ancho, formato)',
        'Cada foto se genera una sola vez por ancho y formato.')

    @api.model
    def _dcasa_obtener(self, adjunto, ancho, formato):
        """Bytes de la variante; la genera y guarda si no existe. ``adjunto``: el de la foto original."""
        clave = [
            ('res_model', '=', adjunto.res_model), ('res_id', '=', adjunto.res_id),
            ('res_field', '=', adjunto.res_field), ('version', '=', adjunto.checksum[:12]),
            ('ancho', '=', ancho), ('formato', '=', formato),
        ]
        Variante = self.sudo()
        guardada = Variante.search(clave, limit=1)
        if guardada:
            return base64.b64decode(guardada.datos)
        datos = codificar(adjunto.raw, ancho, formato)
        valores = {campo: valor for campo, _op, valor in clave}
        try:
            with self.env.cr.savepoint():
                Variante.create(dict(valores, datos=base64.b64encode(datos)))
                # Las de una foto anterior ya no las pide nadie (la URL cambió de versión).
                Variante.search([
                    ('res_model', '=', adjunto.res_model), ('res_id', '=', adjunto.res_id),
                    ('res_field', '=', adjunto.res_field), ('version', '!=', valores['version']),
                ]).unlink()
        except Exception:  # otra petición la guardó a la vez (UNIQUE): se sirve igual
            _logger.info('Variante de foto ya guardada por otra petición: %s', valores, exc_info=True)
        return datos


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _dcasa_img_fuente(self, registro):
        """(modelo, id, campo) del adjunto que tiene la foto de ``registro``, o None.

        Una variante sin foto propia usa la de su plantilla (igual que ``image_1920`` de Odoo): así
        las variantes comparten URL y caché.
        """
        if registro._name == 'product.product':
            variante = registro.sudo()
            if variante.with_context(bin_size=True).image_variant_1920:
                return ('product.product', variante.id, 'image_variant_1920')
            registro = variante.product_tmpl_id
        if registro._name in ('product.template', 'product.image') and registro.id:
            return (registro._name, registro.id, 'image_1920')
        return None

    @api.model
    def _dcasa_img_adjuntos(self, fuentes):
        """{(modelo, id, campo): ir.attachment} de una lista de fuentes, en una consulta por modelo."""
        por_modelo = {}
        for modelo, res_id, campo in fuentes:
            por_modelo.setdefault((modelo, campo), set()).add(res_id)
        resultado = {}
        Adjunto = self.env['ir.attachment'].sudo()
        for (modelo, campo), ids in por_modelo.items():
            for adjunto in Adjunto.search([
                ('res_model', '=', modelo), ('res_field', '=', campo), ('res_id', 'in', list(ids)),
            ]):
                resultado[(modelo, adjunto.res_id, campo)] = adjunto
        return resultado

    @api.model
    def _dcasa_img_base(self, registro):
        """(``/dcasa/img/<modelo>/<id>/<campo>``, versión) de la foto de ``registro``, o None si no tiene.

        En una página con muchas tarjetas, la primera llamada resuelve de una vez todos los
        registros del mismo prefetch y deja el resultado para el resto de la petición.
        """
        memo = getattr(request, _MEMO, None) if request else None
        if memo is None:
            memo = {}
            if request:
                setattr(request, _MEMO, memo)
        clave = (registro._name, registro.id)
        if clave not in memo:
            lote = registro.browse(registro._prefetch_ids)[:200] | registro
            fuentes = {(r._name, r.id): self._dcasa_img_fuente(r) for r in lote}
            adjuntos = self._dcasa_img_adjuntos([f for f in fuentes.values() if f])
            for (modelo, res_id), fuente in fuentes.items():
                adjunto = adjuntos.get(fuente) if fuente else None
                memo[(modelo, res_id)] = (
                    ('/dcasa/img/{}/{}/{}'.format(*fuente), adjunto.checksum[:12])
                    if adjunto and adjunto.checksum else None)
        return memo[clave]

    @api.model
    def _dcasa_img_url(self, registro, ancho, formato='webp'):
        base = self._dcasa_img_base(registro)
        return base and f'{base[0]}/{ancho}.{formato}?v={base[1]}'

    @api.model
    def _dcasa_img_srcset(self, registro, anchos=(256, 512, 1024), formato='webp'):
        base = self._dcasa_img_base(registro)
        if not base:
            return ''
        return ', '.join(f'{base[0]}/{ancho}.{formato}?v={base[1]} {ancho}w' for ancho in anchos)
