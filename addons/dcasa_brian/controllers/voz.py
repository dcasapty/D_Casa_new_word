"""``POST /dcasa/brian/v1/voz``: la nota de voz del panel de Brian pasada a texto (``models/voz.py``).

JSON-RPC con la sesión del usuario (``auth='user'``) y **solo usuarios internos** (el portal y el público no). El
cuerpo se lee en memoria (nunca a un archivo temporal) y con tope (``max_content_length``). El audio se reenvía una vez
al Worker de Juan y se suelta: no queda en ningún adjunto, mensaje, auditoría ni registro. Solo vuelve el texto.

Entrada (``params``): ``{audio: <base64>, mime: "audio/webm;codecs=opus" | "audio/ogg" | "audio/mp4", duracion_ms}``.
Salida: ``{ok: true, texto, recortado}`` o ``{ok: false, causa, error}`` (``error`` en palabras sencillas).
"""
from odoo import http
from odoo.http import request

from ..models.voz import MAX_BASE64

# El audio en base64 más el sobre del JSON-RPC (``jsonrpc``, ``method``, ``id`` y los demás parámetros).
MAX_CUERPO = MAX_BASE64 + 4096


class BrianVozControlador(http.Controller):

    @http.route('/dcasa/brian/v1/voz', type='jsonrpc', auth='user', methods=['POST'], max_content_length=MAX_CUERPO)
    def transcribir(self, audio=None, mime=None, duracion_ms=None):
        return request.env['dcasa.brian.voz'].transcribir(audio, mime, duracion_ms)
