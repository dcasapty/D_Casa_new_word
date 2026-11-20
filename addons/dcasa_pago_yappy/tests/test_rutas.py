"""Las rutas públicas de verdad (HTTP), siempre con el Yappy falso: abrir el cobro (``/payment/yappy/iniciar``) y el
aviso de Yappy (``/payment/yappy/ipn``). Aquí se ataca lo que cualquiera puede alcanzar desde internet."""
import inspect
import json
from unittest.mock import patch
from urllib.parse import urlencode

from psycopg2 import errorcodes
from psycopg2.errors import SerializationFailure

from odoo import Command
from odoo.addons.dcasa_pago_yappy.controllers import main as controlador
from odoo.addons.dcasa_pago_yappy.models import yappy_api as api
from odoo.tests import HttpCase, tagged

from .common import (
    CELULAR,
    CELULAR_LIMPIO,
    DOMINIO,
    ID_COMERCIO,
    OTRO_DOMINIO,
    SECRETOS,
    ComunYappy,
    YappyFalso,
    aviso_de,
    entorno,
    firmar,
)


class ChoqueDeSerializacion(SerializationFailure):
    """El error de PostgreSQL cuando otra transacción ganó la fila (con su código: es lo que Odoo mira para repetir)."""
    pgcode = errorcodes.SERIALIZATION_FAILURE


INICIAR = '/payment/yappy/iniciar'
AVISO = '/payment/yappy/ipn'


class BaseHttp(ComunYappy, HttpCase):

    def setUp(self):
        super().setUp()
        controlador.RITMO_DE_INICIAR.olvidar()
        controlador.RITMO_DEL_AVISO.olvidar()
        self.addCleanup(controlador.RITMO_DE_INICIAR.olvidar)
        self.addCleanup(controlador.RITMO_DEL_AVISO.olvidar)

    def crear_transaccion(self, pedido=None, **extra):
        """La transacción como la crea la tienda de verdad (la ruta del portal del pedido), en la sesión actual."""
        pedido = pedido or self.pedido()
        self.env.flush_all()
        valores = self.make_jsonrpc_request(f'/my/orders/{pedido.id}/transaction', {
            'access_token': pedido._portal_ensure_token(), 'provider_id': self.proveedor.id,
            'payment_method_id': self.metodo.id, 'token_id': None, 'amount': pedido.amount_total,
            'flow': 'direct', 'tokenization_requested': False, 'landing_route': pedido.get_portal_url(),
            'is_validation': False, **extra})
        return pedido, valores

    def iniciar(self, referencia, celular=CELULAR, **extra):
        self.env.flush_all()
        parametros = {'reference': referencia, 'celular': celular, **extra}
        respuesta = self.url_open(INICIAR, data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': parametros}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:300])
        cuerpo = respuesta.json()
        self.assertNotIn('error', cuerpo, cuerpo)
        return cuerpo['result']

    def ipn(self, parametros, **kwargs):
        self.env.flush_all()
        return self.url_open(f'{AVISO}?{urlencode(parametros)}', **kwargs)

    def releer(self, *txs):
        self.env.invalidate_all()
        for tx in txs:
            tx.invalidate_recordset()


@tagged('post_install', '-at_install')
class TestIniciar(BaseHttp):

    def test_el_camino_feliz_devuelve_solo_lo_que_necesita_el_boton(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            pedido, valores = self.crear_transaccion()
            self.assertEqual(valores['provider_code'], 'yappy')
            self.assertEqual(yappy.llamadas, [], 'crear la transacción no llama a Yappy')
            resultado = self.iniciar(valores['reference'])
        self.assertEqual(set(resultado), {'ok', 'transactionId', 'token', 'documentName'})
        self.assertTrue(resultado['ok'])
        self.assertEqual(len(yappy.llamadas), 2)
        texto = json.dumps(resultado)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, texto, 'la clave secreta y el ID de comercio nunca llegan al navegador')
        self.releer()
        tx = self.env['payment.transaction'].search([('reference', '=', valores['reference'])])
        self.assertEqual(tx.state, 'pending')
        self.assertEqual(tx.dcasa_yappy_celular, CELULAR_LIMPIO)
        self.assertEqual(tx.operation, 'online_direct')

    def test_sin_ninguna_transaccion_en_la_sesion_no_se_abre_nada(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            resultado = self.iniciar('S00001-1')
        self.assertFalse(resultado['ok'])
        self.assertIn('Tu pago cambió', resultado['mensaje'])
        self.assertEqual(yappy.llamadas, [])

    def test_la_transaccion_de_otra_sesion_no_se_abre(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            _pedido, valores = self.crear_transaccion()
            self.authenticate(None, None)      # otra persona, otra sesión
            resultado = self.iniciar(valores['reference'])
        self.assertFalse(resultado['ok'])
        self.assertEqual(yappy.llamadas, [])
        self.releer()
        tx = self.env['payment.transaction'].search([('reference', '=', valores['reference'])])
        self.assertEqual(tx.state, 'draft')
        self.assertFalse(tx.dcasa_yappy_orden)

    def test_solo_se_abre_la_transaccion_que_esta_sesion_viene_pagando(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            pedido, primera = self.crear_transaccion()
            _p, segunda = self.crear_transaccion(pedido)
            vieja = self.iniciar(primera['reference'])
            self.assertFalse(vieja['ok'], 'la sesión vigila la última: la primera ya no es la que se está pagando')
            self.assertEqual(yappy.llamadas, [])
            self.assertTrue(self.iniciar(segunda['reference'])['ok'])

    def test_una_referencia_inventada_o_de_otro_proveedor_no_abre_nada(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            _pedido, valores = self.crear_transaccion()
            for referencia in ('', 'x' * 500, valores['reference'] + 'x', "S1'; DROP TABLE payment_transaction;--"):
                resultado = self.iniciar(referencia)
                self.assertFalse(resultado['ok'], referencia[:30])
            self.assertEqual(yappy.llamadas, [])

    def test_los_tipos_raros_no_revientan(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            _pedido, valores = self.crear_transaccion()
            ref = valores['reference']
            for referencia, celular in ((None, CELULAR), (['a'], CELULAR), ({'a': 1}, CELULAR), (ref, None),
                                        (ref, 60000101), (ref, ['6']), (ref, 'x' * 500)):
                respuesta = self.url_open(INICIAR, data=json.dumps({
                    'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
                        'reference': referencia, 'celular': celular}}), headers={'Content-Type': 'application/json'})
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(respuesta.json()['result']['ok'])
            self.assertEqual(yappy.llamadas, [])

    def test_ya_pagada_o_ya_iniciada_no_se_vuelve_a_abrir(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            _pedido, valores = self.crear_transaccion()
            self.assertTrue(self.iniciar(valores['reference'])['ok'])
            llamadas = len(yappy.llamadas)
            repetida = self.iniciar(valores['reference'])
            self.assertFalse(repetida['ok'])
            self.assertIn('ya se usó', repetida['mensaje'])
            self.assertEqual(len(yappy.llamadas), llamadas)
            self.releer()
            tx = self.env['payment.transaction'].search([('reference', '=', valores['reference'])])
            tx._set_done()
            self.assertFalse(self.iniciar(valores['reference'])['ok'], 'una transacción pagada no se abre otra vez')
            self.assertEqual(len(yappy.llamadas), llamadas)

    def test_el_monto_cero_no_pasa_ni_siquiera_a_crear_la_transaccion(self):
        self.authenticate(None, None)
        pedido = self.pedido()
        pedido.order_line.price_unit = 0.0
        # La ruta del portal se niega con una JsonRpcException (de ahí el ``Exception`` a secas).
        with YappyFalso() as yappy, self.assertRaises(Exception):  # noqa: B017
            self.crear_transaccion(pedido)
        self.assertEqual(yappy.llamadas, [])

    def test_el_monto_que_manda_el_navegador_no_manda(self):
        self.authenticate(None, None)
        pedido = self.pedido()
        with YappyFalso() as yappy, self.assertRaises(Exception):   # noqa: B017
            self.crear_transaccion(pedido, amount=1.0)
        self.assertEqual(yappy.llamadas, [])

    def test_un_celular_malo_dice_que_hace_falta_y_no_gasta_llamadas(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            _pedido, valores = self.crear_transaccion()
            resultado = self.iniciar(valores['reference'], celular='123')
        self.assertFalse(resultado['ok'])
        self.assertIn('celular de tu app de Yappy', resultado['mensaje'])
        self.assertEqual(yappy.llamadas, [])

    def test_si_yappy_falla_el_mensaje_es_claro_sin_trazas_ni_claves(self):
        for falla in ('tiempo', 'red', 'html', 'http500'):
            with self.subTest(falla=falla), YappyFalso() as yappy:
                self.authenticate(None, None)
                yappy.falla = falla
                _pedido, valores = self.crear_transaccion()
                resultado = self.iniciar(valores['reference'])
                self.assertFalse(resultado['ok'])
                self.assertIn('No pudimos abrir el pago con Yappy', resultado['mensaje'])
                self.assertEqual(set(resultado), {'ok', 'mensaje'})
                for secreto in SECRETOS:
                    self.assertNotIn(secreto, json.dumps(resultado))

    def test_numero_no_registrado_se_le_explica_a_la_clienta(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            yappy.no_registrados.add(CELULAR_LIMPIO)
            _pedido, valores = self.crear_transaccion()
            resultado = self.iniciar(valores['reference'])
        self.assertIn('no está registrado en Yappy', resultado['mensaje'])

    def test_hay_un_limite_de_intentos_por_conexion_antes_de_crear_nada(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            _pedido, valores = self.crear_transaccion()
            for _i in range(8):
                self.iniciar('no-es-la-mia')
            resultado = self.iniciar(valores['reference'])
            self.assertFalse(resultado['ok'])
            self.assertIn('muchas veces seguidas', resultado['mensaje'])
            self.assertEqual(yappy.llamadas, [], 'con el límite excedido no se llama a Yappy')
        controlador.RITMO_DE_INICIAR.olvidar()
        with YappyFalso():
            self.assertTrue(self.iniciar(valores['reference'])['ok'])

    def test_solo_post(self):
        self.authenticate(None, None)
        for metodo in ('GET', 'PUT', 'DELETE'):
            respuesta = self.url_open(INICIAR, method=metodo)
            self.assertIn(respuesta.status_code, (404, 405), metodo)

    def test_apagado_o_sin_claves_la_ruta_no_abre_nada(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            _pedido, valores = self.crear_transaccion()
            self.proveedor.state = 'disabled'
            resultado = self.iniciar(valores['reference'])
            self.assertFalse(resultado['ok'])
            self.proveedor.state = 'test'
            with entorno(YAPPY_CLAVE_SECRETA=None):
                self.assertFalse(self.iniciar(valores['reference'])['ok'])
            self.assertEqual(yappy.llamadas, [])

    def test_un_visitante_no_puede_forzar_un_proveedor_sin_publicar(self):
        self.proveedor.is_published = False
        self.authenticate(None, None)
        pedido = self.pedido()
        with YappyFalso() as yappy, self.assertRaises(Exception):   # noqa: B017 - la ruta del portal se niega a crearla
            self.crear_transaccion(pedido)
        self.assertEqual(yappy.llamadas, [])

    def test_el_pedido_cambia_despues_de_crear_la_transaccion(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            pedido, valores = self.crear_transaccion()
            pedido.order_line.product_uom_qty = 5
            resultado = self.iniciar(valores['reference'])
        self.assertFalse(resultado['ok'])
        self.assertIn('solo paga el pedido completo', resultado['mensaje'])
        self.assertEqual(yappy.llamadas, [])


@tagged('post_install', '-at_install')
class TestAviso(BaseHttp):

    def abrir_en_sesion(self):
        self.authenticate(None, None)
        with YappyFalso() as yappy:
            pedido, valores = self.crear_transaccion()
            self.assertTrue(self.iniciar(valores['reference'])['ok'])
        self.releer()
        tx = self.env['payment.transaction'].search([('reference', '=', valores['reference'])])
        self.assertEqual(tx.state, 'pending')
        return pedido, tx, yappy

    def test_un_aviso_bien_firmado_paga_y_responde_ok_sin_sesion(self):
        pedido, tx, _yappy = self.abrir_en_sesion()
        respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.assertEqual((respuesta.status_code, respuesta.text), (200, 'ok'))
        self.assertNotIn('Set-Cookie', respuesta.headers, 'no se le da una sesión a nadie')
        self.assertEqual(respuesta.headers.get('Cache-Control'), 'no-store')
        self.releer(tx)
        self.assertEqual(tx.state, 'done')
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')

    def test_los_cuatro_estados_por_http(self):
        for estado, final in (('E', 'done'), ('R', 'cancel'), ('C', 'cancel'), ('X', 'cancel')):
            with self.subTest(estado=estado):
                _pedido, tx, _yappy = self.abrir_en_sesion()
                self.assertEqual(self.ipn(aviso_de(tx.dcasa_yappy_orden, estado)).status_code, 200)
                self.releer(tx)
                self.assertEqual(tx.state, final)

    def test_un_hash_malo_se_rechaza_sin_decir_por_que_y_no_toca_nada(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        orden = tx.dcasa_yappy_orden
        casos = {
            'hash inventado': aviso_de(orden, 'E', hash='a' * 64),
            'hash vacío': aviso_de(orden, 'E', hash=''),
            'hash de otro estado': aviso_de(orden, 'E', hash=firmar(orden, 'R')),
            'dominio de otro sitio bien firmado': aviso_de(orden, 'E', domain=OTRO_DOMINIO,
                                                          hash=firmar(orden, 'E', OTRO_DOMINIO)),
            'estado desconocido': aviso_de(orden, 'Z', hash=firmar(orden, 'Z')),
            'orden con símbolos': aviso_de(orden + '-', 'E', hash=firmar(orden + '-', 'E')),
            'sin parámetros': {},
            'firmado con otra clave': aviso_de(orden, 'E', hash=firmar(orden, 'E', clave='otra-clave')),
        }
        respuestas = {nombre: self.ipn(parametros) for nombre, parametros in casos.items()}
        for nombre, respuesta in respuestas.items():
            self.assertEqual(respuesta.status_code, 403, nombre)
        self.assertEqual(
            {r.text for r in respuestas.values()}, {'no autorizado'}, 'el mismo cuerpo siempre: sin decir por qué')
        self.releer(tx)
        self.assertEqual(tx.state, 'pending')
        self.assertFalse(tx.dcasa_yappy_avisos)

    def test_un_aviso_firmado_de_una_orden_desconocida_contesta_igual_que_uno_bueno(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        buena = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'R'))
        desconocida = self.ipn(aviso_de('S99999ZZZZZ', 'E'))
        self.assertEqual((buena.status_code, buena.text), (desconocida.status_code, desconocida.text))
        self.assertEqual(desconocida.text, 'ok', 'no filtra si la orden existe')

    def test_una_orden_de_otro_proveedor_no_se_toca(self):
        pedido = self.pedido()
        transferencia = self.env.ref('payment.payment_provider_transfer')
        metodo = self.env['payment.method'].search([('code', '=', 'wire_transfer')], limit=1)
        otra = self.env['payment.transaction'].create({
            'provider_id': transferencia.id, 'payment_method_id': metodo.id, 'amount': pedido.amount_total,
            'currency_id': pedido.currency_id.id, 'partner_id': pedido.partner_id.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(pedido.ids)]})
        otra.dcasa_yappy_orden = 'S00001ABCDE'
        respuesta = self.ipn(aviso_de('S00001ABCDE', 'E'))
        self.assertEqual(respuesta.status_code, 200)
        self.releer(otra)
        self.assertEqual(otra.state, 'draft')

    def test_el_mismo_aviso_muchas_veces_no_duplica_nada(self):
        pedido, tx, _yappy = self.abrir_en_sesion()
        for _i in range(5):
            self.assertEqual(self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E')).status_code, 200)
        self.releer(tx)
        tx._post_process()
        self.assertEqual(self.env['account.payment'].search_count([('payment_transaction_id', '=', tx.id)]), 1)
        self.assertEqual(tx.dcasa_yappy_avisos.count('E '), 1)

    def test_un_rechazo_despues_de_un_pago_no_lo_deshace(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.ipn(aviso_de(tx.dcasa_yappy_orden, 'R'))
        self.releer(tx)
        self.assertEqual(tx.state, 'done')

    def test_un_pago_despues_de_un_rechazo_no_se_paga_solo(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        self.ipn(aviso_de(tx.dcasa_yappy_orden, 'R'))
        self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.releer(tx)
        self.assertEqual(tx.state, 'error')
        self.assertTrue(tx.dcasa_yappy_revision)

    def test_hash_en_mayusculas_estado_en_minuscula_y_dominios_con_o_sin_www(self):
        for nombre, cambios in (('hash en mayúsculas', {'hash': lambda o: firmar(o, 'E').upper()}),
                                ('estado en minúscula', {'status': lambda o: 'e'}),
                                ('con www', {'domain': lambda o: 'www.' + DOMINIO,
                                             'hash': lambda o: firmar(o, 'E', 'www.' + DOMINIO)}),
                                ('con https y barra', {'domain': lambda o: f'https://{DOMINIO}/',
                                                       'hash': lambda o: firmar(o, 'E', f'https://{DOMINIO}/')}),
                                # H6: las formas que antes daban 403 y podían ser las reales
                                ('con http', {'domain': lambda o: f'http://{DOMINIO}',
                                              'hash': lambda o: firmar(o, 'E', f'http://{DOMINIO}')}),
                                ('en mayúsculas', {'domain': lambda o: DOMINIO.upper(),
                                                   'hash': lambda o: firmar(o, 'E', DOMINIO.upper())}),
                                ('con el puerto por defecto', {'domain': lambda o: f'{DOMINIO}:443',
                                                               'hash': lambda o: firmar(o, 'E', f'{DOMINIO}:443')}),
                                ('con doble barra', {'domain': lambda o: f'https://{DOMINIO}//',
                                                     'hash': lambda o: firmar(o, 'E', f'https://{DOMINIO}//')})):
            with self.subTest(nombre):
                _pedido, tx, _yappy = self.abrir_en_sesion()
                orden = tx.dcasa_yappy_orden
                parametros = aviso_de(orden, 'E', **{k: f(orden) for k, f in cambios.items()})
                self.assertEqual(self.ipn(parametros).status_code, 200)
                self.releer(tx)
                self.assertEqual(tx.state, 'done')

    # ------------------------------------------------------------------ H6: un aviso rechazado deja rastro claro

    def _log_del_aviso(self, parametros):
        with self.assertLogs('odoo.addons.dcasa_pago_yappy.controllers.main', level='WARNING') as registro:
            respuesta = self.ipn(parametros)
        return respuesta, '\n'.join(registro.output)

    def test_un_aviso_rechazado_por_el_dominio_deja_en_el_registro_cual_llego_y_cual_esta_declarado(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        orden = tx.dcasa_yappy_orden
        raro = 'sitio-que-no-es-el-nuestro.example'
        parametros = aviso_de(orden, 'E', domain=raro, hash=firmar(orden, 'E', raro))
        respuesta, texto = self._log_del_aviso(parametros)
        self.assertEqual((respuesta.status_code, respuesta.text), (403, 'no autorizado'), 'a quien llama, lo mismo')
        self.assertNotIn('Set-Cookie', respuesta.headers)
        self.assertIn(raro, texto, 'quien opera ve el dominio que llegó')
        self.assertIn(DOMINIO, texto, 'y el que está declarado')
        self.assertIn(orden, texto)
        self.assertNotIn(parametros['hash'], texto, 'nunca la firma recibida')
        for secreto in SECRETOS:
            self.assertNotIn(secreto, texto)

    def test_un_aviso_rechazado_de_una_orden_nuestra_queda_anotado_en_su_transaccion(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        orden = tx.dcasa_yappy_orden
        raro = 'http://otro-sitio.example'
        self._log_del_aviso(aviso_de(orden, 'E', domain=raro, hash=firmar(orden, 'E', raro)))
        self.releer(tx)
        self.assertEqual(tx.dcasa_yappy_rechazos, 1)
        self.assertIn(raro, tx.dcasa_yappy_rechazo)
        self.assertIn('dominio', tx.dcasa_yappy_rechazo)
        self.assertEqual(tx.state, 'pending', 'no paga ni cancela: solo deja constancia')
        self.assertFalse(tx.dcasa_yappy_avisos)
        # la firma mala de una orden nuestra también: puede ser la clave mal pegada
        self._log_del_aviso(aviso_de(orden, 'E', hash='b' * 64))
        self.releer(tx)
        self.assertEqual(tx.dcasa_yappy_rechazos, 2)
        self.assertIn('firma', tx.dcasa_yappy_rechazo)
        self.assertNotIn('b' * 64, tx.dcasa_yappy_rechazo)
        self.assertEqual(tx.state, 'pending')

    def test_el_rastro_de_los_rechazos_tiene_tope_y_no_lo_llena_quien_ataca(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        for _vez in range(9):
            self._log_del_aviso(aviso_de(tx.dcasa_yappy_orden, 'E', hash='c' * 64))
        self.releer(tx)
        self.assertEqual(tx.dcasa_yappy_rechazos, 5)

    def test_sin_rastro_si_la_orden_no_es_nuestra_o_el_aviso_ni_tiene_la_forma(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        orden = tx.dcasa_yappy_orden
        self._log_del_aviso(aviso_de('S99999ZZZZZ', 'E', hash='d' * 64))           # una orden que no existe
        self._log_del_aviso(aviso_de(orden, 'Z', hash=firmar(orden, 'Z')))          # estado que no existe
        self._log_del_aviso({'orderId': orden})                                      # sin el resto
        self._log_del_aviso(aviso_de(orden + '-', 'E'))                              # orden con símbolos
        self.releer(tx)
        self.assertEqual(tx.dcasa_yappy_rechazos, 0)

    def test_un_rechazo_sobre_un_cobro_ya_cerrado_no_escribe_nada(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        self.assertEqual(self.ipn(aviso_de(tx.dcasa_yappy_orden, 'R')).status_code, 200)
        self._log_del_aviso(aviso_de(tx.dcasa_yappy_orden, 'E', hash='e' * 64))
        self.releer(tx)
        self.assertEqual(tx.dcasa_yappy_rechazos, 0)

    def test_sin_las_claves_en_el_servidor_el_aviso_de_una_orden_nuestra_queda_anotado(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        with entorno(YAPPY_CLAVE_SECRETA=None):
            respuesta, texto = self._log_del_aviso(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('faltan las claves', texto)
        self.releer(tx)
        self.assertEqual(tx.dcasa_yappy_rechazos, 1)

    def test_solo_get_y_los_datos_van_en_la_direccion_no_en_el_cuerpo(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        for metodo in ('POST', 'PUT', 'DELETE'):
            respuesta = self.url_open(AVISO, data=urlencode(aviso_de(tx.dcasa_yappy_orden, 'E')), method=metodo)
            self.assertIn(respuesta.status_code, (404, 405), metodo)
        self.releer(tx)
        self.assertEqual(tx.state, 'pending')

    def test_sin_las_claves_en_el_servidor_nada_se_acepta(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        with entorno(YAPPY_CLAVE_SECRETA=None):
            respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.assertEqual(respuesta.status_code, 403)
        self.releer(tx)
        self.assertEqual(tx.state, 'pending')

    def test_apagado_el_proveedor_un_aviso_firmado_igual_paga_quien_pago_antes(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        self.proveedor.state = 'disabled'
        self.assertEqual(self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E')).status_code, 200)
        self.releer(tx)
        self.assertEqual(tx.state, 'done')

    def test_el_numero_de_confirmacion_no_decide_nada(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E', hash='b' * 64, confirmationNumber='CONF-1'))
        self.assertEqual(respuesta.status_code, 403, 'un número de confirmación no reemplaza a la firma')
        respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'R', confirmationNumber='CONF-2'))
        self.assertEqual(respuesta.status_code, 200)
        self.releer(tx)
        self.assertEqual(tx.state, 'cancel')
        self.assertEqual(tx.dcasa_yappy_confirmacion, 'CONF-2')

    def test_pasado_el_freno_de_ritmo_no_se_procesa_nada(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        controlador.RITMO_DEL_AVISO.maximo = 2
        self.addCleanup(setattr, controlador.RITMO_DEL_AVISO, 'maximo', 120)
        self.assertEqual(self.ipn(aviso_de('S99999ZZZZZ', 'R')).status_code, 200)
        self.assertEqual(self.ipn(aviso_de('S99999ZZZZZ', 'R')).status_code, 200)
        respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.assertEqual(respuesta.status_code, 429)
        self.releer(tx)
        self.assertEqual(tx.state, 'pending')

    def test_un_fallo_nuestro_responde_500_para_que_yappy_pueda_reintentar_y_no_filtra_nada(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        with patch.object(type(self.env['payment.transaction']), '_dcasa_yappy_aplicar_aviso',
                          side_effect=RuntimeError('detalle interno ' + ID_COMERCIO)), \
                self.assertLogs('odoo.addons.dcasa_pago_yappy', level='ERROR') as registro:
            respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.assertEqual((respuesta.status_code, respuesta.text), (500, 'error'))
        self.assertNotIn('detalle interno', respuesta.text)
        self.assertTrue(registro.output)
        self.releer(tx)
        self.assertEqual(tx.state, 'pending')

    def test_un_choque_de_concurrencia_no_se_traga_odoo_repite_la_peticion_y_el_aviso_se_aplica(self):
        """Si otra petición tenía la fila (o la soltó justo ahora), PostgreSQL contesta con un error de serialización.
        Atraparlo daba un 500 y un aviso perdido; el controlador lo deja pasar y Odoo repite la petición entera con
        una foto nueva."""
        _pedido, tx, _yappy = self.abrir_en_sesion()
        modelo = type(self.env['payment.transaction'])
        original = modelo._dcasa_yappy_aplicar_aviso
        intentos = []

        def choca_la_primera_vez(este, aviso):
            intentos.append(aviso.estado)
            if len(intentos) == 1:
                raise ChoqueDeSerializacion('could not serialize access due to concurrent update')
            return original(este, aviso)

        with patch.object(modelo, '_dcasa_yappy_aplicar_aviso', autospec=True, side_effect=choca_la_primera_vez):
            respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        self.assertEqual((respuesta.status_code, respuesta.text), (200, 'ok'))
        self.assertEqual(intentos, ['E', 'E'], 'Odoo repitió la petición una vez')
        self.releer(tx)
        self.assertEqual(tx.state, 'done')

    def test_ningun_registro_del_aviso_trae_claves(self):
        _pedido, tx, _yappy = self.abrir_en_sesion()
        with self.assertLogs('odoo', level='INFO') as registro:
            self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E', hash='c' * 64))
            self.ipn(aviso_de(tx.dcasa_yappy_orden, 'E'))
        texto = '\n'.join(registro.output)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, texto)
        self.assertNotIn(CELULAR_LIMPIO, texto)

    def test_el_aviso_no_usa_sudo_en_el_controlador_y_la_busqueda_es_por_igualdad(self):
        """El visitante anónimo no tiene permiso sobre las transacciones: lo único que escribe es el aviso, DESPUÉS de
        verificar la firma, y por el método del modelo (que es quien hace ``sudo``). El controlador del aviso no lo
        hace."""
        fuente = inspect.getsource(controlador.YappyController.yappy_aviso)
        self.assertNotIn('sudo', fuente)
        self.assertLess(fuente.index('verificar_aviso'), fuente.index('_dcasa_yappy_buscar'),
                        'la firma se comprueba ANTES de buscar nada en la base')
        busqueda = inspect.getsource(type(self.env['payment.transaction'])._dcasa_yappy_buscar)
        self.assertIn("('dcasa_yappy_orden', '=', orden)", busqueda)
        self.assertNotIn('ilike', busqueda)
        self.assertNotIn('execute', busqueda)

    def test_el_visitante_no_puede_leer_las_transacciones_por_ninguna_ruta_nueva(self):
        """Ninguna de las dos rutas devuelve datos de una transacción: el aviso contesta texto fijo y la de abrir solo
        lo que necesita el botón."""
        _pedido, tx, _yappy = self.abrir_en_sesion()
        respuesta = self.ipn(aviso_de(tx.dcasa_yappy_orden, 'R'))
        for dato in (tx.reference, tx.dcasa_yappy_orden, tx.dcasa_yappy_celular, ID_COMERCIO):
            self.assertNotIn(str(dato), respuesta.text)
        self.assertNotIn('payment.transaction', respuesta.text)
        for ruta in ('/payment/yappy', '/payment/yappy/'):
            self.assertIn(self.url_open(ruta).status_code, (404, 405))


@tagged('post_install', '-at_install')
class TestLaPaginaDePago(BaseHttp):
    """El paso de pago de la tienda con Yappy directo: una sola fila «Yappy», con su número y su CDN."""

    def test_la_fila_de_yappy_es_una_sola_y_trae_el_script_del_entorno_y_el_celular(self):
        from lxml import html as lxml_html  # noqa: PLC0415
        pedido = self.pedido()
        pedido.write({'require_payment': True, 'prepayment_percent': 1.0})
        pedido.action_quotation_sent()
        self.env.flush_all()
        respuesta = self.url_open(pedido.get_portal_url())
        self.assertEqual(respuesta.status_code, 200)
        arbol = lxml_html.fromstring(respuesta.text)
        radios = arbol.xpath('//form[@id="o_payment_form"]//input[@name="o_payment_radio"]')
        yappys = [r for r in radios if r.get('data-payment-method-code') in ('yappy', 'yappy_directo')]
        self.assertEqual([r.get('data-payment-method-code') for r in yappys], ['yappy_directo'],
                         'un solo «Yappy»: el directo, sin el manual')
        etiquetas = [
            e.text_content().strip() for e in arbol.xpath('//label[contains(@class, "o_payment_option_label")]')]
        self.assertEqual(etiquetas.count('Yappy'), 1)
        caja = arbol.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " o_dcasa_yappy ")]')
        self.assertEqual(len(caja), 1)
        self.assertEqual(caja[0].get('data-yappy-script'), api.cdn(api.PRUEBA))
        campo = caja[0].xpath('.//input[@name="o_dcasa_yappy_celular"]')[0]
        self.assertEqual(campo.get('value'), '6000 0101', 'viene escrito con el celular del pedido')
        self.assertEqual(campo.get('type'), 'tel')
        self.assertTrue(caja[0].xpath('.//label[contains(@class, "o_dcasa_yappy_etiqueta")]'))
        self.assertNotIn(ID_COMERCIO, respuesta.text)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, respuesta.text)
        # El script de Yappy NO está en el HTML: lo pide el JavaScript al elegir la fila.
        sin_lo_nuestro = respuesta.text.replace(api.cdn(api.PRUEBA), '').replace('data-yappy-script', '')
        self.assertNotIn('yappy.cloud', sin_lo_nuestro)

    def test_apagado_la_pagina_muestra_el_yappy_manual_de_siempre(self):
        from lxml import html as lxml_html  # noqa: PLC0415
        self.proveedor.state = 'disabled'
        pedido = self.pedido()
        pedido.write({'require_payment': True, 'prepayment_percent': 1.0})
        pedido.action_quotation_sent()
        self.env.flush_all()
        respuesta = self.url_open(pedido.get_portal_url())
        arbol = lxml_html.fromstring(respuesta.text)
        codigos = arbol.xpath('//form[@id="o_payment_form"]//input[@name="o_payment_radio"]/@data-payment-method-code')
        self.assertIn('yappy', codigos)
        self.assertNotIn('yappy_directo', codigos)
        self.assertFalse(arbol.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " o_dcasa_yappy ")]'))
        self.assertNotIn('data-yappy-script', respuesta.text)

    def test_el_celular_del_pedido_que_no_es_de_panama_no_se_escribe(self):
        from lxml import html as lxml_html  # noqa: PLC0415
        self.cliente.phone = '+1 415 555 0100'
        pedido = self.pedido()
        pedido.write({'require_payment': True, 'prepayment_percent': 1.0})
        pedido.action_quotation_sent()
        self.env.flush_all()
        arbol = lxml_html.fromstring(self.url_open(pedido.get_portal_url()).text)
        campos = arbol.xpath('//input[@name="o_dcasa_yappy_celular"]')
        self.assertEqual(campos[0].get('value') or '', '')
