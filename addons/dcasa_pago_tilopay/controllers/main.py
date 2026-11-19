"""Las dos rutas públicas de Tilopay: el retorno del cliente y el aviso del servidor.

Las dos hacen lo mismo con lo que reciben: **buscar qué orden revisar** y dejar que ``_dcasa_tilopay_confirmar`` le
pregunte a Tilopay. Nada de lo que llegue aquí decide un pago. Reglas (docs/TILOPAY.md §4):

* Nada caro antes de validar: tope de tamaño (16 KB), forma de la orden y que exista una transacción de Tilopay con
  esa orden. Una orden inventada no llama a Tilopay.
* Respuesta uniforme exista o no la orden (el aviso: ``200 {"estado": "ok"}``; el retorno: la misma redirección a
  ``/payment/status``). Sin trazas hacia afuera: un error se registra en el servidor y la respuesta no cambia.
* ``csrf=False`` porque las manda Tilopay (sin cookies); ``save_session=False`` para no darle una sesión nueva a nadie.
* En la ruta no viaja ningún secreto (Odoo registra la ruta de cada visita).
"""
import json
import logging

from odoo import http
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
from odoo.http import request

from ..models import tilopay_api as api_tilopay

_logger = logging.getLogger(__name__)

MAX_CUERPO = 16 * 1024
MAX_PARAMETROS = 50
FORMULARIOS = ('application/x-www-form-urlencoded', 'multipart/form-data')


class TilopayController(http.Controller):
    _return_url = '/payment/tilopay/return'
    _webhook_url = '/payment/tilopay/webhook'

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False, save_session=False,
                max_content_length=MAX_CUERPO)
    def tilopay_retorno(self, **datos):
        """El cliente vuelve de la página de Tilopay. ``code`` y lo demás son solo pistas: se consulta a Tilopay."""
        try:
            with request.env.cr.savepoint():
                self._procesar_retorno(datos)
        except Exception:  # noqa: BLE001 - el cliente siempre vuelve a la página de estado; el detalle queda en el servidor
            _logger.exception('Tilopay: error al procesar el retorno del cliente.')
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False, save_session=False,
                max_content_length=MAX_CUERPO)
    def tilopay_aviso(self, **datos):
        """El aviso de Tilopay (su forma exacta no es pública: docs/TILOPAY.md §8). Solo se usa para saber qué orden
        revisar; siempre responde igual."""
        try:
            with request.env.cr.savepoint():
                self._procesar_aviso(datos)
        except Exception:  # noqa: BLE001
            _logger.exception('Tilopay: error al procesar un aviso.')
        return request.make_json_response({'estado': 'ok'})

    # ------------------------------------------------------------------

    @staticmethod
    def _procesar_retorno(datos):
        Tx = request.env['payment.transaction'].sudo()
        tx = Tx._dcasa_tilopay_buscar(datos.get('order'))
        if not tx:
            tx = Tx._dcasa_tilopay_buscar(api_tilopay.orden_de_return_data(datos.get('returnData')))
        if not tx:
            # Lo último: la transacción que esta misma sesión viene pagando (nunca la de otra persona).
            monitoreada = request.env['payment.transaction'].sudo().browse(
                request.session.get(PaymentPostProcessing.MONITORED_TX_ID_KEY)).exists()
            tx = monitoreada if monitoreada.provider_code == 'tilopay' else Tx.browse()
        if not tx:
            return
        codigo = str(datos.get('code', '')).strip()
        tx._dcasa_tilopay_confirmar('retorno', navegador_cancelo=bool(codigo) and codigo != '1')

    @staticmethod
    def _cuerpo_del_aviso(datos):
        """Los datos del aviso como diccionario (formulario o JSON); vacío si no se entiende o es demasiado."""
        crudo = dict(list(datos.items())[:MAX_PARAMETROS])
        mimetype = (request.httprequest.mimetype or '').lower()
        if mimetype in FORMULARIOS:
            return crudo      # los campos del formulario ya vienen en ``datos``
        # JSON con cualquier tipo de contenido (o sin él): la forma del aviso de compras no es pública
        # (docs/TILOPAY.md §8).
        try:
            json_cuerpo = json.loads(request.httprequest.get_data(cache=False) or b'null')
        except ValueError:
            return crudo
        if isinstance(json_cuerpo, dict):
            crudo.update(json_cuerpo)
        return crudo

    @classmethod
    def _procesar_aviso(cls, datos):
        orden = api_tilopay.extraer_orden(cls._cuerpo_del_aviso(datos))
        if not orden:
            return
        tx = request.env['payment.transaction']._dcasa_tilopay_buscar(orden)
        if tx:
            tx._dcasa_tilopay_confirmar('aviso')


class TilopayPostProcessing(PaymentPostProcessing):
    """Mientras el cliente espera en «Estado del pago», cada vuelta del reloj de esa página le pregunta a Tilopay
    (con el freno de una consulta cada 5 segundos por transacción): así un pago de Yappy que se aprueba tarde no se
    queda dando vueltas aunque el aviso no llegue. También pregunta si la transacción quedó en «error»: un rechazo
    seguido de un pago aprobado en la misma página de Tilopay se recupera."""

    @http.route()
    def poll_status(self, **kwargs):
        tx = self._get_monitored_transaction()
        if tx and tx.provider_code == 'tilopay' and tx.state in ('draft', 'pending', 'error'):
            try:
                with request.env.cr.savepoint():
                    tx._dcasa_tilopay_confirmar('estado')
            except Exception:  # noqa: BLE001
                _logger.exception('Tilopay: error al preguntar desde «Estado del pago».')
        return super().poll_status(**kwargs)
