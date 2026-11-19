"""Un Tilopay de mentira para las pruebas: ni red real ni dinero. Habla como el API documentado
(``https://tilopay.com/developers/openapi.json``, leído el 2026-11-19) y guarda cada llamada para poder mirarlas."""
import json as json_lib
import os
import uuid
from unittest.mock import patch

import requests

from odoo import Command
from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api

# Claves inventadas, con forma reconocible para buscarlas en logs y pantallas.
LLAVE = 'LLAVE-DE-PRUEBA-0001-NO-ES-REAL'
USUARIO = 'USUARIO-DE-PRUEBA-0002-NO-ES-REAL'
CLAVE = 'CLAVE-DE-PRUEBA-0003-NO-ES-REAL'
SECRETOS = (LLAVE, USUARIO, CLAVE)
ENTORNO_DE_PRUEBA = {'TILOPAY_API_KEY': LLAVE, 'TILOPAY_API_USER': USUARIO, 'TILOPAY_API_PASSWORD': CLAVE,
                     'TILOPAY_ENTORNO': 'prueba'}


class RespuestaFalsa:
    def __init__(self, estado, cuerpo):
        self.status_code = estado
        self._cuerpo = cuerpo
        self.content = cuerpo if isinstance(cuerpo, bytes) else json_lib.dumps(cuerpo).encode()
        self.reason = ''

    def json(self):
        if isinstance(self._cuerpo, bytes):
            return json_lib.loads(self._cuerpo)
        return self._cuerpo


class SimuladorTilopay:
    """Sustituye a ``requests.post`` mientras dura el ``with``. Todo lo que cambia el comportamiento es un atributo:

    ``falla`` = ``'tiempo'`` | ``'red'`` | ``'http500'`` | ``'basura'`` | ``'vacio'``; ``claves_buenas`` = ``False``
    para que el inicio de sesión dé 401; ``entorno`` = lo que dice ``environment`` en las filas; ``pagos[orden]`` = las
    filas de ``consult`` (se llenan con ``aprobar``/``rechazar``)."""

    def __init__(self, entorno='Test'):
        self.llamadas = []            # [(ruta, cuerpo, cabeceras)]
        self.pagos = {}
        self.entorno = entorno
        self.claves_buenas = True
        self.falla = None
        self.token = 'tok-' + uuid.uuid4().hex
        self.tokens_vigentes = {self.token}
        self.ordenes_creadas = set()
        self._parche = None

    # -- control de la prueba

    def __enter__(self):
        self._parche = patch.object(requests, 'post', side_effect=self)
        self._parche.start()
        return self

    def __exit__(self, *exc):
        self._parche.stop()
        return False

    def fila(self, orden, monto, moneda='USD', code='1', tipo='Payment', entorno=None, **extra):
        fila = {'id_tilopay': 734312, 'orderNumber': orden, 'amount': f'{float(monto):.2f}', 'currency': moneda,
                'merchantId': '88803956', 'code': code,
                'response': 'Transacción aprobada' if code == '1' else 'Fondos insuficientes', 'auth': '123456',
                'capture': 'Capture', 'environment': entorno or self.entorno, 'type': tipo,
                'date': '2026-11-19 16:59:20'}
        fila.update(extra)
        return fila

    def aprobar(self, orden, monto, **extra):
        self.pagos.setdefault(orden, []).append(self.fila(orden, monto, **extra))

    def rechazar(self, orden, monto, **extra):
        self.pagos.setdefault(orden, []).append(self.fila(orden, monto, code='4', **extra))

    def rutas(self, ruta=None):
        return [llamada for llamada in self.llamadas if ruta is None or llamada[0] == ruta]

    def orden_del_ultimo_pago(self):
        return self.rutas(api.RUTA_PAGO)[-1][1]['orderNumber']

    # -- el API

    def __call__(self, url, json=None, headers=None, timeout=None, **kwargs):
        assert url.startswith(api.HOST), url
        ruta = url[len(api.HOST):]
        self.llamadas.append((ruta, json, dict(headers or {})))
        assert timeout and timeout[1] <= 10, 'toda llamada lleva un tiempo de espera corto'
        if self.falla == 'tiempo':
            raise requests.exceptions.Timeout('lento')
        if self.falla == 'red':
            raise requests.exceptions.ConnectionError('caído')
        if self.falla == 'http500':
            return RespuestaFalsa(500, {'message': 'error'})
        if self.falla == 'basura':
            return RespuestaFalsa(200, b'<html>no es json</html>')
        if self.falla == 'vacio':
            return RespuestaFalsa(200, {})
        if ruta == api.RUTA_LOGIN:
            if self.claves_buenas and json.get('apiuser') == USUARIO and json.get('password') == CLAVE:
                return RespuestaFalsa(200, {'access_token': self.token, 'token_type': 'bearer', 'expires_in': 86400})
            return RespuestaFalsa(401, {'error': 'Unauthorized'})
        autorizacion = (headers or {}).get('Authorization', '')
        if autorizacion.replace('bearer ', '', 1) not in self.tokens_vigentes:
            return RespuestaFalsa(401, {})
        if ruta == api.RUTA_PAGO:
            return self._crear_pago(json)
        if ruta == api.RUTA_CONSULTA:
            return self._consultar(json)
        return RespuestaFalsa(404, {'message': 'no existe'})

    def _crear_pago(self, cuerpo):
        obligatorios = ('redirect', 'key', 'amount', 'currency', 'orderNumber', 'capture', 'billToFirstName',
                        'billToLastName', 'billToAddress', 'billToAddress2', 'billToCity', 'billToState',
                        'billToZipPostCode', 'billToCountry', 'billToTelephone', 'billToEmail', 'subscription',
                        'platform')
        faltan = [c for c in obligatorios if not str(cuerpo.get(c, '')).strip()]
        if faltan:
            return RespuestaFalsa(200, {'type': '400', 'message': 'faltan: ' + ', '.join(faltan)})
        if cuerpo['key'] != LLAVE:
            return RespuestaFalsa(200, {'type': '403', 'message': 'llave inválida'})
        if cuerpo['orderNumber'] in self.ordenes_creadas:
            return RespuestaFalsa(200, {'type': '400', 'message': 'Transacción duplicada'})
        self.ordenes_creadas.add(cuerpo['orderNumber'])
        return RespuestaFalsa(200, {'type': '100', 'html': 'Use url redirect',
                                    'url': f"https://secure.tilopay.com/htmls/{cuerpo['orderNumber']}_574572148file.html"})

    def _consultar(self, cuerpo):
        if cuerpo.get('key') != LLAVE:
            return RespuestaFalsa(200, {'type': '403', 'message': 'llave inválida'})
        filas = self.pagos.get(cuerpo.get('orderNumber'))
        if not filas:
            orden = cuerpo.get('orderNumber')
            return RespuestaFalsa(200, {'type': '400', 'message': f'Order number: {orden} does not exist'})
        return RespuestaFalsa(200, {'type': '200', 'message': '', 'response': filas})


class entorno:
    """Las claves de mentira en ``os.environ`` (y lo que se quiera cambiar; ``None`` la quita). Sirve con ``with`` o con
    ``.start()`` / ``.stop()``."""

    def __init__(self, **cambios):
        self.valores = {**ENTORNO_DE_PRUEBA, **cambios}
        self._parche = None

    def start(self):
        quitar = [k for k, v in self.valores.items() if v is None]
        self._parche = patch.dict(os.environ, {k: v for k, v in self.valores.items() if v is not None})
        self._parche.start()
        for k in quitar:
            os.environ.pop(k, None)
        return self

    def stop(self):
        self._parche.stop()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False


class PreparaPedido:
    """Mixin para pruebas con base de datos: un pedido de la web con el proveedor encendido en modo de prueba."""

    @classmethod
    def preparar_tilopay(cls, estado='test'):
        cls.website = cls.env.ref('website.default_website')
        cls.proveedor = cls.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        cls.metodo = cls.env.ref('dcasa_pago_tilopay.payment_method_tilopay')
        cls.cliente = cls.env['res.partner'].create({
            'name': 'Ana Prueba Pago', 'email': 'ana.prueba.pago@example.com', 'phone': '+507 6000-1111',
            'street': 'Calle de prueba 1', 'city': 'La Chorrera', 'country_id': cls.env.ref('base.pa').id})
        cls.producto = cls.env['product.product'].create({
            'name': 'Sofá de prueba (Tilopay)', 'type': 'consu', 'is_storable': True, 'list_price': 100.0,
            'taxes_id': [Command.set(cls.env.company.account_sale_tax_id.ids)]})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.producto, almacen.lot_stock_id, 10.0)
        cls.proveedor.state = estado
        cls.proveedor.is_published = True

    def pedido(self, cantidad=1):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'website_id': self.website.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': cantidad})]})
        return orden

    def transaccion(self, pedido, monto=None):
        return self.env['payment.transaction'].create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id,
            'amount': pedido.amount_total if monto is None else monto, 'currency_id': pedido.currency_id.id,
            'partner_id': pedido.partner_invoice_id.id, 'operation': 'online_redirect',
            'sale_order_ids': [Command.set(pedido.ids)]})


class ComunTilopay(PreparaPedido):
    """Lo de siempre en las pruebas con base de datos: proveedor encendido, claves de mentira y memoria de tokens
    limpia."""
    estado_del_proveedor = 'test'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_tilopay(cls.estado_del_proveedor)

    def setUp(self):
        super().setUp()
        api.olvidar_tokens()
        self.addCleanup(api.olvidar_tokens)
        self.addCleanup(entorno().start().stop)

    def abrir(self, tilopay, pedido=None, monto=None):
        """Crea la transacción y la página de pago (como lo hace la tienda). Devuelve (transacción, orden de
        Tilopay)."""
        pedido = pedido or self.pedido()
        tx = self.transaccion(pedido, monto)
        tx._get_processing_values()
        return tx, tx.dcasa_tilopay_orden

    def llamadas_a_consulta(self, tilopay):
        return tilopay.rutas(api.RUTA_CONSULTA)
