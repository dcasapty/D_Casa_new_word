"""Las dos rutas públicas de Yappy: abrir el cobro (la página de pago) y el aviso del servidor (IPN).

* ``/payment/yappy/iniciar`` (JSON, la llama nuestro JavaScript cuando la clienta pulsa el botón de Yappy): valida que
  la transacción es de ESTA sesión y que sigue en borrador, pone un límite de intentos ANTES de crear nada (cada orden
  es una llamada a la cuenta de Yappy), hace los dos POST en el servidor y devuelve SOLO ``{transactionId, token,
  documentName}``. La clave secreta nunca sale del servidor.
* ``/payment/yappy/ipn`` (GET abierto, lo llama Yappy): lo único que puede pagar. Comprueba la firma (HMAC en tiempo
  constante) y que el dominio sea nuestro ANTES de tocar la base; un aviso que no cuadra se rechaza sin decir por qué;
  uno firmado de una orden desconocida contesta lo mismo que uno bueno. Sin sesión, sin CSRF (lo manda Yappy, sin
  cookies). Es la única entrada pública que escribe en una transacción, y solo después de verificar la firma: por eso
  usa ``sudo`` (el visitante anónimo no tiene permiso sobre las transacciones).
"""
import logging

from odoo import http
from odoo.addons.dcasa_base.red import llave_ip
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
from odoo.exceptions import ConcurrencyError, ValidationError
from odoo.http import request
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY

from ..models import yappy_api as api_yappy
from ..models.yappy_ritmo import LimiteDeRitmo

_logger = logging.getLogger(__name__)

# Lo que Odoo repite por su cuenta (la petición entera, con una foto nueva de la base): nunca se atrapa aquí.
CHOQUES_DE_CONCURRENCIA = (*PG_CONCURRENCY_EXCEPTIONS_TO_RETRY, ConcurrencyError)
MAX_PARAMETROS = 30
MAX_LARGO_DE_TEXTO = 100
# Quien abre cobros: máximo 8 por minuto por conexión (una persona real pulsa el botón de vez en cuando).
RITMO_DE_INICIAR = LimiteDeRitmo(maximo=8, ventana=60)
# Los avisos de Yappy vienen de pocas direcciones: el freno es generoso y solo corta a quien martilla.
RITMO_DEL_AVISO = LimiteDeRitmo(maximo=120, ventana=60)
MENSAJE_MUCHOS_INTENTOS = 'Estás intentando pagar muchas veces seguidas. Espera un momento y vuelve a intentarlo.'
MENSAJE_SIN_DATOS = 'No se entendió el pago. Recarga la página e inténtalo otra vez.'
MENSAJE_OTRA_SESION = 'Tu pago cambió mientras tanto. Recarga la página e inténtalo otra vez.'


def _dentro_del_ritmo(limite):
    llave = llave_ip(request.httprequest.remote_addr or '')
    return limite.permitir(llave)


def _respuesta(texto, estado):
    respuesta = request.make_response(texto, headers=[('Content-Type', 'text/plain; charset=utf-8'),
                                                        ('Cache-Control', 'no-store')])
    respuesta.status_code = estado
    return respuesta


class YappyController(http.Controller):
    _iniciar_url = '/payment/yappy/iniciar'
    _aviso_url = '/payment/yappy/ipn'

    @http.route(_iniciar_url, type='jsonrpc', auth='public', methods=['POST'])
    def yappy_iniciar(self, reference=None, celular=None, **_kwargs):
        """Abre el cobro en Yappy para la transacción de esta sesión. Cualquier fallo es un mensaje claro para la
        clienta (``{'ok': False, 'mensaje': …}``) y el botón se puede reintentar."""
        if not _dentro_del_ritmo(RITMO_DE_INICIAR):
            return {'ok': False, 'mensaje': MENSAJE_MUCHOS_INTENTOS}
        if not (isinstance(reference, str) and 0 < len(reference) <= MAX_LARGO_DE_TEXTO) \
                or not (isinstance(celular, str) and len(celular) <= 40):
            return {'ok': False, 'mensaje': MENSAJE_SIN_DATOS}
        tx = request.env['payment.transaction'].sudo().browse(
            request.session.get(PaymentPostProcessing.MONITORED_TX_ID_KEY)).exists()
        # La transacción tiene que ser la que ESTA sesión viene pagando (la que acaba de crear la tienda o el portal):
        # nunca la de otra persona, aunque se conozca su referencia.
        if not tx or tx.reference != reference or tx.provider_code != 'yappy':
            return {'ok': False, 'mensaje': MENSAJE_OTRA_SESION}
        try:
            datos = tx._dcasa_yappy_iniciar(celular)
        except ValidationError as error:
            return {'ok': False, 'mensaje': error.args[0] if error.args else MENSAJE_SIN_DATOS}
        # SOLO lo que necesita el botón. Nada más de lo que contestó Yappy.
        return {'ok': True, 'transactionId': datos['transactionId'], 'token': datos['token'],
                'documentName': datos['documentName']}

    @http.route(_aviso_url, type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def yappy_aviso(self, **_datos):
        """El aviso de Yappy (IPN). Solo un aviso bien firmado, con un dominio nuestro, mueve algo."""
        if not _dentro_del_ritmo(RITMO_DEL_AVISO):
            return _respuesta('demasiadas peticiones', 429)
        parametros = {nombre: valor for nombre, valor in list(request.httprequest.args.items())[:MAX_PARAMETROS]}
        aviso, motivo = api_yappy.verificar_aviso(api_yappy.credenciales(), parametros)
        if aviso is None:
            # Sin decir por qué: ni a quien llama ni en el cuerpo. El motivo solo va al registro del servidor (sin
            # valores).
            _logger.warning('Yappy: aviso rechazado (%s).', motivo)
            return _respuesta('no autorizado', 403)
        try:
            with request.env.cr.savepoint():
                tx = request.env['payment.transaction']._dcasa_yappy_buscar(aviso.orden)
                if tx:
                    tx._dcasa_yappy_aplicar_aviso(aviso)
                else:
                    _logger.warning('Yappy: llegó un aviso bien firmado (%s) de la orden %s, que no existe en Odoo: '
                                    'revisa el reporte de Yappy Comercial.', aviso.estado, aviso.orden)
        except CHOQUES_DE_CONCURRENCIA:
            # Otra petición tiene esta fila (o la acaba de soltar): Odoo repite la petición ENTERA con una foto nueva de
            # la base, y el segundo aviso ve lo que hizo el primero. Tragarse el error daría un 500 y un aviso que no se
            # aplica.
            raise
        except Exception:
            # Un fallo nuestro: Yappy puede volver a intentarlo; el detalle queda en el registro del servidor.
            _logger.exception('Yappy: error al procesar el aviso de la orden %s.', aviso.orden)
            return _respuesta('error', 500)
        return _respuesta('ok', 200)
