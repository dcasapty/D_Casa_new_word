"""Descarga de un adjunto de una conversación con URL firmada y de vida corta (ver ``models/firma.py``).

Solo sirve adjuntos de MENSAJES de conversaciones (``res_model = 'dcasa.mensaje'``): aunque alguien conociera el
id de otro adjunto de Odoo y tuviera el secreto, no se sirve nada que no sea de una conversación. Sin firma
válida o vencida, 404 (no se distingue de un adjunto inexistente).
"""
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..models import firma as F

_logger = logging.getLogger(__name__)

# Tipos que se sirven tal cual; todo lo demás sale como descarga genérica (un HTML/SVG/JS nunca se ejecuta).
TIPOS_SEGUROS = ('image/png', 'image/jpeg', 'image/webp', 'image/gif', 'application/pdf', 'audio/', 'video/')


def _no_existe():
    return request.make_response('No existe.', status=404, headers=[
        ('Content-Type', 'text/plain; charset=utf-8'), ('Cache-Control', 'no-store')])


class AdjuntosJuan(http.Controller):

    @http.route(f'{F.PREFIJO}/<int:adjunto_id>/<int:vence>/<string:firma>/<path:nombre>', type='http', auth='none',
                methods=['GET'], csrf=False, save_session=False, readonly=True)
    def adjunto(self, adjunto_id, vence, firma, nombre=None, **_kw):
        entorno = request.env(user=SUPERUSER_ID)
        adjunto = entorno['ir.attachment'].browse(adjunto_id).exists()
        secreto = entorno['ir.config_parameter'].get_param('database.secret') or ''
        if (not adjunto or adjunto.res_model != 'dcasa.mensaje' or not secreto
                or not F.es_valida(secreto, adjunto.id, vence, firma, adjunto.checksum)):
            return _no_existe()
        mime = (adjunto.mimetype or 'application/octet-stream').lower()
        seguro = mime.startswith(TIPOS_SEGUROS)
        cabeceras = [
            ('Content-Type', mime if seguro else 'application/octet-stream'),
            ('Content-Disposition', http.content_disposition(adjunto.name or nombre or 'adjunto')),
            ('Cache-Control', 'private, no-store'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
        ]
        return request.make_response(adjunto.raw or b'', headers=cabeceras)
