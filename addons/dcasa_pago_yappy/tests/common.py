"""Un Yappy de mentira para las pruebas: ni red real ni dinero. Habla como la documentación de Yappy (docs/YAPPY.md
§2) y guarda cada llamada para poder mirarlas. Todas las claves de aquí son INVENTADAS, con forma reconocible para
buscarlas en registros y pantallas."""
import base64
import hashlib
import hmac
import json as json_lib
import os
import re
import uuid
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

import requests

from odoo import Command, fields
from odoo.addons.dcasa_pago_yappy.models import yappy_api as api
from odoo.exceptions import ValidationError

ID_COMERCIO = 'COMERCIO-DE-PRUEBA-0001-NO-ES-REAL'
# La clave secreta que da Yappy viene en base64; decodificada trae varios trozos separados por «.» y solo el
# primero firma.
CLAVE_TEXTO = 'clave-inventada.segundo.tercer-trozo'
CLAVE_BASE64 = base64.b64encode(CLAVE_TEXTO.encode()).decode()
LLAVE_DEL_HASH = CLAVE_TEXTO.split('.', maxsplit=1)[0]
DOMINIO = 'dcasapty.com'
OTRO_DOMINIO = 'otro-sitio.com'
SECRETOS = (ID_COMERCIO, CLAVE_BASE64, CLAVE_TEXTO, LLAVE_DEL_HASH)
ENTORNO_DE_PRUEBA = {
    'YAPPY_ID_COMERCIO': ID_COMERCIO, 'YAPPY_CLAVE_SECRETA': CLAVE_BASE64, 'YAPPY_DOMINIO': DOMINIO,
    'YAPPY_ENTORNO': 'prueba'}
CELULAR = '6000 0101'
CELULAR_LIMPIO = '60000101'
URL_DE_AVISO = '/payment/yappy/ipn'


def firmar(orden, estado, dominio=DOMINIO, clave=LLAVE_DEL_HASH):
    """El hash que mandaría Yappy, calculado con la biblioteca estándar (no con el código que se prueba)."""
    return hmac.new(clave.encode(), f'{orden}{estado}{dominio}'.encode(), hashlib.sha256).hexdigest()


def aviso_de(orden, estado, **cambios):
    """Los parámetros de un aviso bien firmado (``cambios`` los pisa)."""
    datos = {'orderId': orden, 'status': estado, 'domain': DOMINIO, 'hash': firmar(orden, estado)}
    datos.update(cambios)
    return datos


class RespuestaFalsa:
    def __init__(self, estado, cuerpo):
        self.status_code = estado
        self._cuerpo = cuerpo
        self.content = cuerpo if isinstance(cuerpo, bytes) else json_lib.dumps(cuerpo).encode()

    def json(self):
        if isinstance(self._cuerpo, bytes):
            return json_lib.loads(self._cuerpo)
        return self._cuerpo


class YappyFalso:
    """Sustituye a ``requests.post`` mientras dura el ``with``. Lo que cambia el comportamiento es un atributo:

    ``falla`` = ``'tiempo'`` | ``'red'`` | ``'http500'`` | ``'html'`` | ``'sin_body'`` | ``'sin_token'`` |
    ``'sin_transaccion'`` | ``'orden_sin_body'`` | ``'lista'``; ``errores`` = ``{ruta: codigo}`` (Yappy contesta ese
    código de error en esa ruta); ``no_registrados`` = celulares que Yappy no conoce (E005)."""

    def __init__(self):
        self.llamadas = []            # [(ruta, cuerpo, cabeceras)]
        self.falla = None
        self.errores = {}
        self.no_registrados = set()
        self.token = 'tok-sesion-' + uuid.uuid4().hex
        self.ordenes = {}
        self._parche = None

    def __enter__(self):
        self._parche = patch.object(requests, 'post', side_effect=self)
        self._parche.start()
        return self

    def __exit__(self, *exc):
        self._parche.stop()
        return False

    def rutas(self, ruta=None):
        return [llamada for llamada in self.llamadas if ruta is None or llamada[0] == ruta]

    def ultima_orden(self):
        return self.rutas(api.RUTA_ORDEN)[-1][1]

    def _error(self, codigo, estado=400):
        return RespuestaFalsa(estado, {'status': {'code': codigo, 'description': f'Error {codigo}'}, 'body': None})

    def __call__(self, url, json=None, headers=None, timeout=None, **kwargs):
        assert url.startswith(api.HOSTS[api.PRUEBA]) or url.startswith(api.HOSTS[api.PRODUCCION]), url
        ruta = urlsplit(url).path
        self.llamadas.append((ruta, json, dict(headers or {})))
        assert timeout and timeout[1] <= 10, 'toda llamada lleva un tiempo de espera corto'
        if self.falla == 'tiempo':
            raise requests.exceptions.Timeout('lento')
        if self.falla == 'red':
            raise requests.exceptions.ConnectionError('caído')
        if self.falla == 'http500':
            return RespuestaFalsa(500, {'status': {'code': 'E012', 'description': 'Algo salió mal'}})
        if self.falla == 'html':
            return RespuestaFalsa(200, b'<html>no es json</html>')
        if self.falla == 'lista':
            return RespuestaFalsa(200, ['no', 'es', 'un', 'objeto'])
        if ruta in self.errores:
            return self._error(self.errores[ruta])
        if ruta == api.RUTA_VALIDAR:
            if (json or {}).get('merchantId') != ID_COMERCIO or (json or {}).get('urlDomain') != DOMINIO:
                return RespuestaFalsa(400, {'status': {'code': 'YAPPY-005', 'description': 'Illegal Arguments'}})
            if self.falla == 'sin_body':
                return RespuestaFalsa(200, {'status': {'code': 'YP-0000', 'description': 'Success'}})
            if self.falla == 'sin_token':
                return RespuestaFalsa(200, {'status': {'code': 'YP-0000'}, 'body': {'epochTime': 1}})
            return RespuestaFalsa(200, {'status': {'code': 'YP-0000', 'description': 'Success'},
                                        'body': {'epochTime': 1700000000, 'token': self.token}})
        if ruta == api.RUTA_ORDEN:
            return self._crear_orden(json or {}, headers or {})
        return RespuestaFalsa(404, {'message': 'no existe'})

    def _crear_orden(self, cuerpo, cabeceras):
        if cabeceras.get('Authorization') != self.token:
            return self._error('E100')
        orden = cuerpo.get('orderId', '')
        if not re.fullmatch(r'[A-Za-z0-9]{1,15}', str(orden)):
            return self._error('E009')
        for campo in ('discount', 'taxes', 'subtotal', 'total'):
            if not re.fullmatch(r'[0-9]+\.[0-9]{2}', str(cuerpo.get(campo, ''))):
                return self._error('E010')
        if float(cuerpo['total']) < 0.01:
            return self._error('E010')
        if not str(cuerpo.get('ipnUrl', '')).startswith('http'):
            return self._error('E011')
        alias = str(cuerpo.get('aliasYappy', ''))
        if not re.fullmatch(r'[0-9]{8}', alias) or alias in self.no_registrados:
            return self._error('E005')
        if orden in self.ordenes:
            return self._error('E007')
        self.ordenes[orden] = cuerpo
        if self.falla == 'orden_sin_body':
            return RespuestaFalsa(200, {'status': {'code': 'YP-0000'}})
        if self.falla == 'sin_transaccion':
            return RespuestaFalsa(200, {'status': {'code': 'YP-0000'}, 'body': {'token': 'x'}})
        return RespuestaFalsa(200, {'status': {'code': 'YP-0000', 'description': 'Success'}, 'body': {
            'transactionId': 'TX-' + uuid.uuid4().hex[:12], 'token': 'tok-boton-' + uuid.uuid4().hex,
            'documentName': 'doc-' + uuid.uuid4().hex[:10]}})


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
    def preparar_yappy(cls, estado='test'):
        cls.website = cls.env.ref('website.default_website')
        cls.proveedor = cls.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        cls.metodo = cls.env.ref('dcasa_pago_yappy.payment_method_yappy')
        cls.cliente = cls.env['res.partner'].create({
            'name': 'Ana Prueba Yappy', 'email': 'ana.prueba.yappy@example.com', 'phone': '+507 6000-0101',
            'street': 'Calle de prueba 1', 'city': 'La Chorrera', 'country_id': cls.env.ref('base.pa').id})
        cls.producto = cls.env['product.product'].create({
            'name': 'Sofá de prueba (Yappy)', 'type': 'consu', 'is_storable': True, 'list_price': 100.0,
            'taxes_id': [Command.set(cls.env.company.account_sale_tax_id.ids)]})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.producto, almacen.lot_stock_id, 50.0)
        cls.proveedor.state = estado
        cls.proveedor.is_published = True

    def pedido(self, cantidad=1):
        return self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'website_id': self.website.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': cantidad})]})

    def transaccion(self, pedido, monto=None, **extra):
        return self.env['payment.transaction'].create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id,
            'amount': pedido.amount_total if monto is None else monto, 'currency_id': pedido.currency_id.id,
            'partner_id': pedido.partner_invoice_id.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(pedido.ids)], **extra})


class ComunYappy(PreparaPedido):
    """Lo de siempre en las pruebas con base de datos: proveedor encendido, claves de mentira."""
    estado_del_proveedor = 'test'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_yappy(cls.estado_del_proveedor)

    def setUp(self):
        super().setUp()
        self.addCleanup(entorno().start().stop)

    def abrir(self, yappy, pedido=None, monto=None, celular=CELULAR):
        """Crea la transacción y abre el cobro en el Yappy falso (como lo hace la tienda). Devuelve (transacción,
        orden de Yappy, lo que recibe el botón)."""
        pedido = pedido or self.pedido()
        tx = self.transaccion(pedido, monto)
        tx._get_processing_values()
        datos = tx._dcasa_yappy_iniciar(celular)
        return tx, tx.dcasa_yappy_orden, datos

    def iniciar_y_fallar(self, tx, celular=CELULAR):
        """Abre el cobro esperando que Yappy no lo abra, y devuelve el mensaje que lee la clienta. NO usa
        ``assertRaises``: el de Odoo deshace (con un savepoint) todo lo escrito dentro, y en la tienda el controlador
        atrapa el error y deja lo escrito (la transacción cerrada, el código de Yappy) justo para poder reintentar."""
        try:
            tx._dcasa_yappy_iniciar(celular)
        except ValidationError as error:
            return error.args[0]
        self.fail('Yappy debía fallar y el cobro se abrió')

    def aviso(self, tx, estado, **cambios):
        """Entrega a la transacción un aviso REAL (firmado y verificado como lo hace el controlador). Devuelve el
        estado."""
        aviso, motivo = api.verificar_aviso(api.credenciales(), aviso_de(tx.dcasa_yappy_orden, estado, **cambios))
        self.assertIsNotNone(aviso, f'el aviso de la prueba tiene que pasar la verificación ({motivo})')
        return tx._dcasa_yappy_aplicar_aviso(aviso)

    def envejecer(self, tx, **delta):
        """Hace que la transacción haya nacido (y se haya mandado a Yappy) hace ``delta`` (``minutes=…``)."""
        antes = fields.Datetime.now() - timedelta(**delta)
        self.env.cr.execute(
            'UPDATE payment_transaction SET create_date = %s, dcasa_yappy_iniciada = %s WHERE id = %s',
            [antes, antes, tx.id])
        tx.invalidate_recordset(['create_date', 'dcasa_yappy_iniciada'])
