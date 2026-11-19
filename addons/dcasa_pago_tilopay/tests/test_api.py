"""La capa sin base de datos: claves, formas de lo que llega, el cliente HTTP y, sobre todo, la decisión de
«¿este pago es de verdad?» (``evaluar_consulta``), caso por caso."""
import base64
import logging
from decimal import Decimal

from odoo.tests import BaseCase, tagged

from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api

from .common import CLAVE, LLAVE, SECRETOS, USUARIO, RespuestaFalsa, SimuladorTilopay, entorno

ORDEN = 'S00012-1-3fa9c2e1'


def cuerpo(*filas):
    return {'type': '200', 'message': '', 'response': list(filas)}


def fila(**cambios):
    base = {'id_tilopay': 734312, 'orderNumber': ORDEN, 'amount': '107.00', 'currency': 'USD', 'code': '1',
            'response': 'Transacción aprobada', 'auth': '123456', 'capture': 'Capture', 'environment': 'Test',
            'type': 'Payment'}
    base.update(cambios)
    return base


def evaluar(c, entorno_esperado='prueba', monto='107.00', moneda='USD'):
    return api.evaluar_consulta(c, ORDEN, Decimal(monto), moneda, entorno_esperado)


@tagged('post_install', '-at_install')
class TestClavesYFormas(BaseCase):

    def test_las_claves_no_salen_ni_imprimiendo_el_objeto(self):
        with entorno():
            creds = api.credenciales()
        self.assertEqual((creds.llave, creds.usuario, creds.clave), (LLAVE, USUARIO, CLAVE))
        for texto in (repr(creds), str(creds), f'{creds}', '%s' % (creds,)):
            for secreto in SECRETOS:
                self.assertNotIn(secreto, texto)

    def test_sin_una_de_las_tres_no_hay_credenciales(self):
        for falta in ('TILOPAY_API_KEY', 'TILOPAY_API_USER', 'TILOPAY_API_PASSWORD'):
            with self.subTest(falta=falta), entorno(**{falta: None}):
                self.assertIsNone(api.credenciales())
            with self.subTest(vacia=falta), entorno(**{falta: '   '}):
                self.assertIsNone(api.credenciales())

    def test_el_entorno_por_defecto_es_prueba(self):
        """Lo seguro: sin variable (o con una rara) un pago real no se acepta, y uno de prueba nunca paga producción."""
        for valor, esperado in ((None, 'prueba'), ('', 'prueba'), ('lo-que-sea', 'prueba'), ('prueba', 'prueba'),
                                ('produccion', 'produccion'), (' Producción ', 'produccion'), ('PRODUCTION', 'produccion')):
            with self.subTest(valor=valor), entorno(TILOPAY_ENTORNO=valor):
                self.assertEqual(api.entorno_esperado(), esperado)

    def test_limpiar_quita_claves_tokens_y_saltos(self):
        sucio = f'error con {LLAVE} y {CLAVE}\nlinea2 token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmnop'
        limpio = api.limpiar(sucio, SECRETOS)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, limpio)
        self.assertNotIn('eyJhbGci', limpio)
        self.assertNotIn('\n', limpio)
        self.assertLessEqual(len(api.limpiar('x' * 1000)), api.LARGO_TEXTO)

    def test_orden_valida(self):
        for buena in (ORDEN, 'S00012-1-abcdef12', 'DC-3fa9c2e1', 'A' * 64):
            self.assertEqual(api.orden_valida(buena), buena)
        for mala in (None, 123, '', 'corta', '-empieza-mal-123', 'con espacio 123456', "x'; DROP TABLE x;--", 'a' * 65,
                     'á' * 8, 'S00012/1/3fa9', ['S00012-1-3fa9c2e1']):
            self.assertIsNone(api.orden_valida(mala), mala)

    def test_extraer_orden_de_un_aviso_o_un_retorno(self):
        self.assertEqual(api.extraer_orden({'orderNumber': ORDEN}), ORDEN)
        self.assertEqual(api.extraer_orden({'order': ORDEN, 'code': '1'}), ORDEN)
        self.assertEqual(api.extraer_orden({'data': {'orderNumber': ORDEN}}), ORDEN)
        self.assertEqual(api.extraer_orden({'ORDERNUMBER': ORDEN}), ORDEN)
        self.assertEqual(api.extraer_orden({'order': ORDEN, 'orderNumber': ORDEN}), ORDEN, 'dos veces la misma: vale')
        self.assertIsNone(api.extraer_orden({'order': ORDEN, 'orderNumber': 'S00013-1-aaaaaaaa'}),
                          'dos órdenes distintas: no se adivina')
        for malo in (None, [], 'texto', 5, {}, {'order': {'x': 1}}, {'order': ['a']}, {'order': 'corta'},
                     {'data': 'texto'}, {'orderNumber': True}):
            self.assertIsNone(api.extraer_orden(malo), malo)

    def test_return_data_ida_y_vuelta_y_basura(self):
        self.assertEqual(api.orden_de_return_data(api.codificar_return_data(ORDEN)), ORDEN)
        for malo in (None, '', 5, '!!!!', 'x' * 300, base64.b64encode(b"x'; drop").decode(),
                     base64.b64encode('ñandú-123456'.encode()).decode()):
            self.assertIsNone(api.orden_de_return_data(malo), malo)

    def test_la_pagina_de_pago_solo_puede_ser_de_tilopay(self):
        for buena in ('https://secure.tilopay.com/htmls/1212122_574572148file.html', 'https://tilopay.com/x',
                      'https://pagos.tilopay.com/a?b=c'):
            self.assertTrue(api.url_de_pago_valida(buena), buena)
        for mala in ('http://secure.tilopay.com/x', 'https://tilopay.com.evil.example/x', 'https://evil.example/tilopay.com',
                     'https://eviltilopay.com/x', 'https://user:pass@secure.tilopay.com/x', 'javascript:alert(1)',
                     '//secure.tilopay.com/x', '', None, 5, 'https://secure.tilopay.com@evil.example/x'):
            self.assertFalse(api.url_de_pago_valida(mala), mala)

    def test_la_firma_no_se_puede_verificar_todavia(self):
        """El algoritmo de OrderHash no es público (docs/TILOPAY.md §5.4): el hueco dice «no verificable»."""
        self.assertIsNone(api.verificar_hash('b02927cb', orden=ORDEN))


@tagged('post_install', '-at_install')
class TestEvaluarConsulta(BaseCase):
    """Lo único que puede decir «pagado» (APROBADO) y cada razón por la que NO."""

    def test_aprobado_exacto(self):
        r = evaluar(cuerpo(fila()))
        self.assertEqual(r['veredicto'], api.APROBADO)
        self.assertIsInstance(r, api.DatosVerificados)
        self.assertEqual(r['monto'], Decimal('107.00'))
        self.assertEqual(r['moneda'], 'USD')
        self.assertEqual(r['entorno_visto'], 'prueba')

    def test_montos_equivalentes_en_texto_o_numero(self):
        for monto in ('107', '107.0', '107.00', 107, 107.0, ' 107.00 '):
            self.assertEqual(evaluar(cuerpo(fila(amount=monto)))['veredicto'], api.APROBADO, monto)

    def test_monto_distinto_no_paga(self):
        for monto in ('106.99', '107.01', '1.07', '0', '-107.00', 'abc', '', None, 'NaN', 'Infinity', '1e3', True,
                      '107.001'):
            with self.subTest(monto=monto):
                self.assertEqual(evaluar(cuerpo(fila(amount=monto)))['veredicto'], api.MONTO)

    def test_moneda_distinta_no_paga(self):
        for moneda in ('CRC', 'EUR', '', None, 'USD2'):
            with self.subTest(moneda=moneda):
                self.assertEqual(evaluar(cuerpo(fila(currency=moneda)))['veredicto'], api.MONEDA)
        self.assertEqual(evaluar(cuerpo(fila(currency=' usd ')))['veredicto'], api.APROBADO, 'mayúsculas y espacios')

    def test_orden_distinta_no_cuenta(self):
        """Una fila de OTRA orden no es de esta transacción, aunque esté aprobada y con el monto justo."""
        self.assertEqual(evaluar(cuerpo(fila(orderNumber='S00099-1-aaaaaaaa')))['veredicto'], api.SIN_REGISTRO)
        self.assertEqual(evaluar(cuerpo(fila(orderNumber=ORDEN.lower())))['veredicto'], api.SIN_REGISTRO)
        self.assertEqual(evaluar(cuerpo(fila(orderNumber=ORDEN + ' ')))['veredicto'], api.APROBADO,
                         'solo se le quitan espacios al borde')
        r = evaluar(cuerpo(fila(orderNumber='S00099-1-aaaaaaaa'), fila(code='4')))
        self.assertEqual(r['veredicto'], api.RECHAZADO, 'solo se miran las filas de esta orden')

    def test_sin_filas_o_con_error_de_tilopay_queda_pendiente(self):
        self.assertEqual(evaluar(cuerpo())['veredicto'], api.SIN_REGISTRO)
        self.assertEqual(evaluar({'type': '400', 'message': f'Order number: {ORDEN} does not exist'})['veredicto'],
                         api.SIN_REGISTRO)
        self.assertEqual(evaluar({'error': 'Unauthorized'})['veredicto'], api.SIN_REGISTRO)

    def test_respuestas_con_forma_rara_no_pagan_ni_fallan(self):
        for raro in (None, [], 'ok', 5, {'type': '200'}, {'type': '200', 'response': 'x'},
                     {'type': '200', 'response': {'orderNumber': ORDEN}}, {'type': 200, 'response': [None, 5, 'x']}):
            with self.subTest(raro=raro):
                self.assertNotEqual(evaluar(raro)['veredicto'], api.APROBADO)

    def test_type_200_numerico_tambien_vale(self):
        self.assertEqual(evaluar({'type': 200, 'response': [fila()]})['veredicto'], api.APROBADO)

    def test_rechazado(self):
        r = evaluar(cuerpo(fila(code='4', response='Fondos insuficientes')))
        self.assertEqual(r['veredicto'], api.RECHAZADO)
        self.assertIn('Fondos insuficientes', r['detalle'])
        for codigo in ('0', '2', '3', '', None, 'aprobado', '11', '1.0'):
            self.assertEqual(evaluar(cuerpo(fila(code=codigo)))['veredicto'], api.RECHAZADO, codigo)

    def test_rechazado_y_luego_aprobado_paga(self):
        """El cliente se equivoca de tarjeta y reintenta en la misma página: cuenta el pago aprobado."""
        r = evaluar(cuerpo(fila(code='4'), fila(code='1')))
        self.assertEqual(r['veredicto'], api.APROBADO)

    def test_dos_aprobadas_o_movimientos_ajenos_lo_revisa_una_persona(self):
        self.assertEqual(evaluar(cuerpo(fila(), fila()))['veredicto'], api.AMBIGUO)
        for tipo in ('Refund', 'Reversal', 'Reembolso', 'Void', '', None):
            with self.subTest(tipo=tipo):
                self.assertEqual(evaluar(cuerpo(fila(), fila(type=tipo, amount='107.00')))['veredicto'], api.AMBIGUO)
        self.assertEqual(evaluar(cuerpo(fila(type='Refund')))['veredicto'], api.AMBIGUO,
                         'una fila que no es un pago nunca se toma por uno')

    def test_el_tipo_se_compara_sin_importar_mayusculas(self):
        self.assertEqual(evaluar(cuerpo(fila(type='PAYMENT')))['veredicto'], api.APROBADO)

    def test_entorno_de_prueba_nunca_paga_produccion_y_al_reves(self):
        prueba, real = cuerpo(fila(environment='Test')), cuerpo(fila(environment='Production'))
        self.assertEqual(evaluar(prueba, 'prueba')['veredicto'], api.APROBADO)
        self.assertEqual(evaluar(real, 'produccion')['veredicto'], api.APROBADO)
        self.assertEqual(evaluar(prueba, 'produccion')['veredicto'], api.ENTORNO)
        self.assertEqual(evaluar(real, 'prueba')['veredicto'], api.ENTORNO)

    def test_entorno_desconocido_o_ausente_no_paga(self):
        for visto in ('Live', 'Sandbox2', '', None, 'prod-eu', 5):
            with self.subTest(visto=visto):
                for esperado in ('prueba', 'produccion'):
                    self.assertEqual(evaluar(cuerpo(fila(environment=visto)), esperado)['veredicto'], api.ENTORNO)

    def test_pago_sin_capturar_no_paga(self):
        for captura in ('Authorization', 'Auth', 'Pending', 'x'):
            self.assertEqual(evaluar(cuerpo(fila(capture=captura)))['veredicto'], api.CAPTURA, captura)
        for captura in ('Capture', 'captured', '', None):
            self.assertEqual(evaluar(cuerpo(fila(capture=captura)))['veredicto'], api.APROBADO, captura)

    def test_solo_el_aprobado_trae_datos_para_pagar(self):
        for c in (cuerpo(), cuerpo(fila(code='4')), cuerpo(fila(amount='1')), cuerpo(fila(), fila())):
            r = evaluar(c)
            self.assertNotEqual(r['veredicto'], api.APROBADO)
            self.assertNotIn('id_tilopay', r)

    def test_los_textos_de_tilopay_salen_limpios(self):
        r = evaluar(cuerpo(fila(code='4', response='x' * 500 + '\n' + LLAVE)))
        self.assertLessEqual(len(r['detalle']), api.LARGO_TEXTO)
        self.assertNotIn('\n', r['detalle'])


@tagged('post_install', '-at_install')
class TestCliente(BaseCase):

    def setUp(self):
        super().setUp()
        api.olvidar_tokens()
        self.addCleanup(api.olvidar_tokens)
        parche = entorno().start()
        self.addCleanup(parche.stop)
        self.cliente = api.Cliente(api.credenciales())

    def test_el_token_se_pide_una_vez_y_se_reutiliza(self):
        with SimuladorTilopay() as tilopay:
            tilopay.aprobar(ORDEN, 107)
            self.cliente.consultar(ORDEN)
            self.cliente.consultar(ORDEN)
        self.assertEqual(len(tilopay.rutas(api.RUTA_LOGIN)), 1)
        self.assertEqual(len(tilopay.rutas(api.RUTA_CONSULTA)), 2)
        self.assertEqual(tilopay.rutas(api.RUTA_CONSULTA)[0][2]['Authorization'], f'bearer {tilopay.token}')

    def test_el_usuario_y_la_clave_solo_viajan_al_inicio_de_sesion(self):
        with SimuladorTilopay() as tilopay:
            tilopay.aprobar(ORDEN, 107)
            self.cliente.consultar(ORDEN)
        for ruta, cuerpo_enviado, _cab in tilopay.llamadas:
            texto = repr(cuerpo_enviado)
            if ruta == api.RUTA_LOGIN:
                self.assertEqual(set(cuerpo_enviado), {'apiuser', 'password'})
            else:
                self.assertNotIn(USUARIO, texto)
                self.assertNotIn(CLAVE, texto)

    def test_un_token_vencido_se_renueva_una_vez(self):
        with SimuladorTilopay() as tilopay:
            tilopay.aprobar(ORDEN, 107)
            self.cliente.consultar(ORDEN)
            tilopay.tokens_vigentes = set()      # Tilopay lo dio por vencido
            tilopay.token = 'tok-nuevo'
            tilopay.tokens_vigentes = {'tok-nuevo'}
            r = self.cliente.consultar(ORDEN)
        self.assertEqual(r['type'], '200')
        self.assertEqual(len(tilopay.rutas(api.RUTA_LOGIN)), 2)

    def test_claves_malas_es_un_error_de_claves(self):
        with SimuladorTilopay() as tilopay:
            tilopay.claves_buenas = False
            with self.assertRaises(api.ErrorTilopay) as ctx:
                self.cliente.consultar(ORDEN)
        self.assertEqual(ctx.exception.tipo, 'claves')

    def test_tiempo_agotado_red_basura_y_http_500_son_errores_que_no_pagan(self):
        for falla, tipo in (('tiempo', 'red'), ('red', 'red'), ('basura', 'respuesta'), ('http500', 'respuesta'),
                            ('vacio', 'respuesta')):
            api.olvidar_tokens()
            with self.subTest(falla=falla), SimuladorTilopay() as tilopay:
                tilopay.falla = falla
                with self.assertRaises(api.ErrorTilopay) as ctx:
                    self.cliente.consultar(ORDEN)
                self.assertEqual(ctx.exception.tipo, tipo)
                for secreto in SECRETOS:
                    self.assertNotIn(secreto, str(ctx.exception))

    def test_crear_pago_devuelve_la_pagina_y_rechaza_una_ajena(self):
        datos = {'orderNumber': ORDEN, 'amount': '107.00', 'currency': 'USD', 'redirect': 'https://x.test/r',
                 'capture': '1', 'billToFirstName': 'A', 'billToLastName': 'B', 'billToAddress': 'C',
                 'billToAddress2': 'C', 'billToCity': 'C', 'billToState': 'PA', 'billToZipPostCode': '0',
                 'billToCountry': 'PA', 'billToTelephone': '1', 'billToEmail': 'a@example.com', 'subscription': '0',
                 'platform': 'Odoo'}
        with SimuladorTilopay() as tilopay:
            url = self.cliente.crear_pago(datos)
            self.assertTrue(url.startswith('https://secure.tilopay.com/'))
            with self.assertRaises(api.ErrorTilopay) as ctx:      # misma orden otra vez: «Transacción duplicada»
                self.cliente.crear_pago(datos)
            self.assertEqual(ctx.exception.tipo, 'rechazo')
        self.assertEqual(tilopay.rutas(api.RUTA_PAGO)[0][1]['key'], LLAVE)

    def test_si_tilopay_manda_a_otro_sitio_no_se_le_cree(self):
        with SimuladorTilopay() as tilopay:
            tilopay._crear_pago = lambda c: RespuestaFalsa(200, {'type': '100', 'url': 'https://evil.example/pagar'})
            with self.assertRaises(api.ErrorTilopay) as ctx:
                self.cliente.crear_pago({'orderNumber': ORDEN})
        self.assertEqual(ctx.exception.tipo, 'respuesta')

    def test_probar_dice_si_o_lanza(self):
        with SimuladorTilopay() as tilopay:
            self.assertTrue(self.cliente.probar())
            tilopay.claves_buenas = False
            with self.assertRaises(api.ErrorTilopay):
                self.cliente.probar()

    def test_ningun_log_trae_claves_ni_token(self):
        api.olvidar_tokens()
        with self.assertLogs(api._logger.name, level=logging.DEBUG) as registros:
            with SimuladorTilopay() as tilopay:
                tilopay.aprobar(ORDEN, 107)
                self.cliente.consultar(ORDEN)
                tilopay.falla = 'tiempo'
                with self.assertRaises(api.ErrorTilopay):
                    self.cliente.consultar(ORDEN)
                tilopay.falla = None
                tilopay.claves_buenas = False
                api.olvidar_tokens()
                with self.assertRaises(api.ErrorTilopay):
                    self.cliente.consultar(ORDEN)
        texto = '\n'.join(registros.output)
        for secreto in (*SECRETOS, tilopay.token):
            self.assertNotIn(secreto, texto)
        self.assertNotIn('Authorization', texto)
