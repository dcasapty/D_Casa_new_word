"""Webhook del bot de Telegram de Brian: ``POST /brian/telegram/<secreto>``.

Doble verificación: el secreto en la URL y el encabezado
``X-Telegram-Bot-Api-Secret-Token`` (que Telegram manda porque se registró con
``secret_token``) deben coincidir con ``BRIAN_TELEGRAM_SECRETO``. Si no hay secreto
configurado o no coincide, responde 404 como si la ruta no existiera.

Siempre responde 200 a Telegram una vez validado (aunque algo falle por dentro) para que
no reintente en bucle; los errores quedan en el log y la transacción se revierte.
"""
import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

_logger = logging.getLogger(__name__)

MAX_CUERPO = 256 * 1024


def _iguales(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(str(a).encode(), str(b).encode())


class BrianTelegram(http.Controller):

    @http.route('/brian/telegram/<string:secreto>', type='http', auth='none', methods=['POST'],
                csrf=False, save_session=False, readonly=False)
    def webhook(self, secreto, **_kw):
        env = request.env(user=SUPERUSER_ID)
        Enlace = env['brian.telegram.enlace']
        esperado = Enlace._secreto()
        encabezado = request.httprequest.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if not _iguales(secreto, esperado) or not _iguales(encabezado, esperado):
            return request.make_response('Not Found', status=404)
        if (request.httprequest.content_length or 0) > MAX_CUERPO:
            return request.make_response('Payload Too Large', status=413)
        try:
            update = json.loads(request.httprequest.get_data(cache=False, as_text=True) or '{}')
        except ValueError:
            return request.make_response('Bad Request', status=400)
        if not isinstance(update, dict):
            return request.make_response('Bad Request', status=400)
        try:
            with env.cr.savepoint():
                Enlace.procesar_update(update)
        except Exception:  # noqa: BLE001 — Telegram no debe reintentar en bucle
            _logger.exception('Brian/Telegram: error procesando el update %s', update.get('update_id'))
        return request.make_json_response({'ok': True})
