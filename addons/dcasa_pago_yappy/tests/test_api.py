"""La capa de Yappy sin base de datos: el hash con vectores, la verificación del aviso (lo único que paga), el
dominio, la orden, el celular, el cliente HTTP con un Yappy falso y que ninguna clave salga a un registro o a un
mensaje."""
import base64
import threading
from unittest.mock import patch

import requests

from odoo.addons.dcasa_pago_yappy.models import yappy_api as api
from odoo.tests import BaseCase, tagged

from .common import (
    CELULAR_LIMPIO,
    CLAVE_BASE64,
    DOMINIO,
    ID_COMERCIO,
    OTRO_DOMINIO,
    SECRETOS,
    YappyFalso,
    aviso_de,
    entorno,
    firmar,
)

ORDEN = 'S00008K3F9Q'
# LOS VECTORES SE CALCULARON APARTE, CON OTRA IMPLEMENTACIÓN (``openssl dgst -sha256 -hmac``), no con este código: una
# prueba que calcula el valor esperado con la misma función que prueba no comprueba nada. La clave secreta es el base64
# de «clave-inventada.segundo.tercer-trozo» (más de un punto: solo el primer trozo, «clave-inventada», firma) y lo que
# se firma es ORDEN + letra + dominio, pegados.
VECTORES = {
    'E': 'a6b19603314bdc55ea9ca93bc7ee1a40ecffe020e74b602baec76c59dec3b449',
    'R': 'bdf5cc590a53847ef73a001237c4202f962b0291b55fdc55c70d99d447608f95',
    'C': '7846a057cc401791f2877f20ce4443c41dcee98f0f68b5557fc4e53870f5e6a7',
    'X': 'b4b5bd0e8b1ee1eda08cdede0ea1df0b5f320c82393908f5d11338c42922d89a',
}
VECTOR_OTRA_ORDEN = ('ABC12345678901', 'E', 'f9e506689027be3d9c7f865257287f581df03ca526e9a5cd558106aec648a342')
VECTORES_DE_DOMINIO = {
    'www.dcasapty.com': '62947f8b3ee15c64361a6e75bf1814ec794922cadcea4cc8e2d7fbb302bf6e92',
    'https://dcasapty.com/': 'a9d0cd88156ce1ae852c489313a8b565afc9fe01ab78a5c1688e9aa368880693',
}
# firma bien hecha para otro-sitio.com
VECTOR_OTRO_SITIO = 'd5fa881a5aec3f8157f7407d7cfd106b0dfef06294e561066ba74000c9a9699f'
# Una clave que decodifica a «soloUnTrozo» (sin punto): firma con el texto entero.
CLAVE_SIN_PUNTO = 'c29sb1VuVHJvem8='
VECTOR_SIN_PUNTO = 'ef9d2ee143bd8ee3203d1af36b3534d3bbd010b276104f42435658ffb48383af'


def credenciales():
    return api.Credenciales(ID_COMERCIO, CLAVE_BASE64, DOMINIO)


@tagged('post_install', '-at_install')
class TestHashConVectores(BaseCase):

    def test_la_clave_de_las_pruebas_tiene_mas_de_un_punto(self):
        self.assertGreaterEqual(base64.b64decode(CLAVE_BASE64).decode().count('.'), 2)

    def test_los_cuatro_estados_dan_los_vectores_calculados_aparte(self):
        for estado, esperado in VECTORES.items():
            with self.subTest(estado=estado):
                self.assertEqual(api.firma_del_aviso(CLAVE_BASE64, ORDEN, estado, DOMINIO), esperado)

    def test_otra_orden_y_dominios_con_su_firma(self):
        orden, estado, esperado = VECTOR_OTRA_ORDEN
        self.assertEqual(api.firma_del_aviso(CLAVE_BASE64, orden, estado, DOMINIO), esperado)
        for dominio, esperado in VECTORES_DE_DOMINIO.items():
            self.assertEqual(api.firma_del_aviso(CLAVE_BASE64, ORDEN, 'E', dominio), esperado)

    def test_una_clave_sin_punto_firma_con_el_texto_entero(self):
        self.assertEqual(api.firma_del_aviso(CLAVE_SIN_PUNTO, ORDEN, 'E', DOMINIO), VECTOR_SIN_PUNTO)

    def test_es_hexadecimal_en_minusculas_de_64_caracteres(self):
        firma = api.firma_del_aviso(CLAVE_BASE64, ORDEN, 'E', DOMINIO)
        self.assertRegex(firma, r'^[0-9a-f]{64}$')

    def test_cambiar_cualquier_pieza_cambia_la_firma(self):
        base = api.firma_del_aviso(CLAVE_BASE64, ORDEN, 'E', DOMINIO)
        self.assertNotEqual(base, api.firma_del_aviso(CLAVE_BASE64, ORDEN + 'X', 'E', DOMINIO))
        self.assertNotEqual(base, api.firma_del_aviso(CLAVE_BASE64, ORDEN, 'R', DOMINIO))
        self.assertNotEqual(base, api.firma_del_aviso(CLAVE_BASE64, ORDEN, 'E', OTRO_DOMINIO))
        otra_clave = base64.b64encode(b'otra-clave.segundo.tercer-trozo').decode()
        self.assertNotEqual(base, api.firma_del_aviso(otra_clave, ORDEN, 'E', DOMINIO))

    def test_los_trozos_despues_del_primer_punto_no_influyen(self):
        otra = base64.b64encode(b'clave-inventada.OTRO.TROZO.MAS').decode()
        self.assertEqual(api.firma_del_aviso(otra, ORDEN, 'E', DOMINIO), VECTORES['E'])

    def test_el_base64_sin_relleno_tambien_se_lee(self):
        sin_relleno = CLAVE_BASE64.rstrip('=')
        self.assertEqual(api.firma_del_aviso(sin_relleno, ORDEN, 'E', DOMINIO), VECTORES['E'])

    def test_una_clave_que_no_se_puede_leer_no_es_una_clave(self):
        for mala in ('', '   ', '!!!no-es-base64!!!', base64.b64encode(b'.solo-segundo-trozo').decode(), None, 123):
            with self.subTest(clave=mala):
                self.assertFalse(api.secreto_valido(mala))
        self.assertTrue(api.secreto_valido(CLAVE_BASE64))


@tagged('post_install', '-at_install')
class TestVerificarAviso(BaseCase):
    """``verificar_aviso`` es LO ÚNICO que puede dar un pago: aquí se le ataca por todos lados."""

    def verificar(self, parametros, creds='bien'):
        return api.verificar_aviso(credenciales() if creds == 'bien' else creds, parametros)

    def test_un_aviso_bien_firmado_pasa_en_los_cuatro_estados(self):
        for estado in api.ESTADOS:
            with self.subTest(estado=estado):
                aviso, motivo = self.verificar({'orderId': ORDEN, 'status': estado, 'domain': DOMINIO,
                                                'hash': VECTORES[estado]})
                self.assertIsNone(motivo)
                self.assertEqual((aviso.orden, aviso.estado), (ORDEN, estado))

    def test_el_hash_en_mayusculas_o_con_espacios_pasa(self):
        for hash_ in (VECTORES['E'].upper(), f'  {VECTORES["E"]}  ', f'\t{VECTORES["E"].upper()}\n'):
            with self.subTest(hash=hash_):
                aviso, _motivo = self.verificar(aviso_de(ORDEN, 'E', hash=hash_))
                self.assertIsNotNone(aviso)

    def test_el_estado_en_minuscula_o_con_espacios_pasa_y_se_firma_la_letra(self):
        for estado in ('e', ' E ', 'e '):
            with self.subTest(estado=estado):
                aviso, _motivo = self.verificar({'orderId': ORDEN, 'status': estado, 'domain': DOMINIO,
                                                 'hash': VECTORES['E']})
                self.assertEqual(aviso.estado, 'E')

    def test_el_hash_de_otro_estado_no_sirve_para_aprobar(self):
        """La firma de un rechazo (o cancelación, o vencimiento) no sirve para decir «pagó»."""
        for otro in ('R', 'C', 'X'):
            with self.subTest(otro=otro):
                aviso, motivo = self.verificar({'orderId': ORDEN, 'status': 'E', 'domain': DOMINIO,
                                                'hash': VECTORES[otro]})
                self.assertIsNone(aviso)
                self.assertEqual(motivo, api.RECHAZO_FIRMA)

    def test_un_hash_inventado_cortado_vacio_o_raro_no_pasa(self):
        for hash_ in ('', 'a' * 64, VECTORES['E'][:-1], VECTORES['E'] + '0', 'no-es-hex', 'é' * 64, '0' * 64):
            with self.subTest(hash=hash_):
                aviso, motivo = self.verificar(aviso_de(ORDEN, 'E', hash=hash_))
                self.assertIsNone(aviso)
                self.assertEqual(motivo, api.RECHAZO_FIRMA)

    def test_un_aviso_sin_hash_o_con_campos_que_no_son_texto_no_pasa(self):
        completo = aviso_de(ORDEN, 'E')
        for campo in ('orderId', 'status', 'domain', 'hash'):
            sin = {k: v for k, v in completo.items() if k != campo}
            with self.subTest(sin=campo):
                self.assertEqual(self.verificar(sin), (None, api.RECHAZO_FORMA))
        for raro in ([ORDEN], 7, None, {'a': 1}, b'bytes'):
            with self.subTest(raro=raro):
                self.assertEqual(self.verificar(aviso_de(ORDEN, 'E', orderId=raro)), (None, api.RECHAZO_FORMA))
        for no_dict in (None, [], 'orderId=1', 5):
            self.assertEqual(self.verificar(no_dict), (None, api.RECHAZO_FORMA))

    def test_un_estado_que_yappy_no_define_se_rechaza_en_vez_de_adivinarse(self):
        for estado in ('Z', '', 'EE', 'ejecutado', 'P', '1', 'ER'):
            with self.subTest(estado=estado):
                aviso, motivo = self.verificar(aviso_de(ORDEN, 'E', status=estado,
                                                        hash=firmar(ORDEN, estado) if estado else ''))
                self.assertIsNone(aviso)
                self.assertIn(motivo, (api.RECHAZO_ESTADO, api.RECHAZO_FORMA))

    def test_la_orden_tiene_que_ser_de_1_a_15_letras_y_numeros(self):
        for orden in ('', 'A' * 16, 'S0008-K3F', 'S 0008', 'S0008\n', 'ÁÉ123', '１２３', "S0008';--"):
            with self.subTest(orden=orden):
                aviso, motivo = self.verificar(aviso_de(orden, 'E', hash=firmar(orden, 'E')))
                self.assertIsNone(aviso)
                self.assertEqual(motivo, api.RECHAZO_FORMA)

    def test_los_dominios_nuestros_pasan_con_o_sin_www_https_y_barra(self):
        for dominio in ('dcasapty.com', 'www.dcasapty.com', 'https://dcasapty.com', 'https://www.dcasapty.com/',
                        'https://dcasapty.com/', 'dcasapty.com/', 'www.dcasapty.com/'):
            with self.subTest(dominio=dominio):
                aviso, motivo = self.verificar(aviso_de(ORDEN, 'E', domain=dominio, hash=firmar(ORDEN, 'E', dominio)))
                self.assertIsNotNone(aviso, motivo)

    def test_el_vector_firmado_para_www_y_para_la_url_entera_pasa(self):
        for dominio, hash_ in VECTORES_DE_DOMINIO.items():
            aviso, _motivo = self.verificar({'orderId': ORDEN, 'status': 'E', 'domain': dominio, 'hash': hash_})
            self.assertIsNotNone(aviso, dominio)

    def test_un_dominio_de_otro_sitio_no_pasa_aunque_venga_bien_firmado_para_el(self):
        """Sin la comprobación del dominio ANTES del hash, bastaría firmar un aviso para otro dominio y la firma
        cuadraría consigo misma."""
        aviso, motivo = self.verificar({'orderId': ORDEN, 'status': 'E', 'domain': OTRO_DOMINIO,
                                        'hash': VECTOR_OTRO_SITIO})
        self.assertIsNone(aviso)
        self.assertEqual(motivo, api.RECHAZO_DOMINIO)

    def test_un_subdominio_o_un_dominio_parecido_tampoco_pasa(self):
        for dominio in ('evil.dcasapty.com', 'dcasapty.com.evil.com', 'xdcasapty.com', 'dcasapty.co',
                        'dcasapty.com:8080', ' dcasapty.com', 'dcasapty.com ', 'DCASAPTY.COM',
                        'dcasapty.com\x00.evil.com', 'http://dcasapty.com', 'dcasapty.com/otra/ruta', ''):
            with self.subTest(dominio=dominio):
                aviso, motivo = self.verificar(aviso_de(ORDEN, 'E', domain=dominio, hash=firmar(ORDEN, 'E', dominio)))
                self.assertIsNone(aviso)
                self.assertEqual(motivo, api.RECHAZO_DOMINIO)

    def test_el_dominio_se_firma_con_nuestra_copia_no_con_la_que_vino(self):
        """La firma se hace con la cadena nuestra: con un dominio nuestro y la firma de otro, no cuadra."""
        aviso, motivo = self.verificar(aviso_de(ORDEN, 'E', domain='www.dcasapty.com', hash=VECTORES['E']))
        self.assertIsNone(aviso)
        self.assertEqual(motivo, api.RECHAZO_FIRMA)

    def test_sin_claves_no_se_acepta_nada(self):
        self.assertEqual(api.verificar_aviso(None, aviso_de(ORDEN, 'E')), (None, api.RECHAZO_SIN_CLAVES))

    def test_con_otra_clave_secreta_no_pasa(self):
        otra = api.Credenciales(ID_COMERCIO, base64.b64encode(b'otra-clave.x').decode(), DOMINIO)
        self.assertEqual(self.verificar(aviso_de(ORDEN, 'E'), creds=otra), (None, api.RECHAZO_FIRMA))

    def test_la_comparacion_va_en_tiempo_constante_con_compare_digest(self):
        with patch.object(api.hmac, 'compare_digest', wraps=api.hmac.compare_digest) as comparar:
            aviso, _motivo = self.verificar(aviso_de(ORDEN, 'E'))
        self.assertIsNotNone(aviso)
        usadas = [llamada.args for llamada in comparar.call_args_list]
        esperada = VECTORES['E'].encode()
        self.assertIn((esperada, esperada), usadas, 'el hash se compara con hmac.compare_digest')
        for a, b in usadas:
            self.assertIsInstance(a, bytes)
            self.assertIsInstance(b, bytes)

    def test_el_codigo_no_compara_hashes_con_igualdad_simple(self):
        """Guardián de fuente: ningún ``==`` entre el hash recibido y el esperado."""
        import inspect  # noqa: PLC0415
        fuente = inspect.getsource(api.verificar_aviso)
        self.assertNotIn('recibida == esperada', fuente)
        self.assertNotIn('esperada == recibida', fuente)
        self.assertIn('compare_digest', fuente)

    def test_el_numero_de_confirmacion_es_informativo_y_no_firmado(self):
        con, _m = self.verificar(aviso_de(ORDEN, 'E', confirmationNumber='CONF-998877'))
        sin, _m = self.verificar(aviso_de(ORDEN, 'E'))
        otro, _m = self.verificar(aviso_de(ORDEN, 'E', confirmationNumber='OTRO-NUMERO'))
        self.assertEqual(con.confirmacion, 'CONF-998877')
        self.assertEqual(sin.confirmacion, '')
        self.assertEqual(otro.confirmacion, 'OTRO-NUMERO', 'cambiarlo no invalida la firma: por eso no decide nada')
        largo, _m = self.verificar(aviso_de(ORDEN, 'E', confirmationNumber='x' * 500 + '\n<script>'))
        self.assertLessEqual(len(largo.confirmacion), api.LARGO_TEXTO)
        raro, _m = self.verificar(aviso_de(ORDEN, 'E', confirmationNumber=['no', 'texto']))
        self.assertEqual(raro.confirmacion, '')

    def test_parametros_de_mas_no_cambian_nada(self):
        aviso, _m = self.verificar(aviso_de(ORDEN, 'E', otro='x', total='999.99', amount='1'))
        self.assertEqual((aviso.orden, aviso.estado), (ORDEN, 'E'))
        self.assertFalse(hasattr(aviso, 'monto'), 'el aviso no trae monto: el monto es el de nuestra transacción')


@tagged('post_install', '-at_install')
class TestPiezas(BaseCase):

    def test_la_orden_lleva_el_numero_del_pedido_delante_y_cabe_en_15(self):
        orden = api.orden_nueva('S00008')
        self.assertTrue(orden.startswith('S00008'))
        self.assertLessEqual(len(orden), 15)
        self.assertRegex(orden, r'^[A-Z0-9]+$')
        self.assertTrue(api.orden_valida(orden))
        self.assertEqual(len(orden), 11, 'S00008 + cinco al azar')

    def test_dos_ordenes_del_mismo_pedido_no_coinciden(self):
        self.assertEqual(len({api.orden_nueva('S00008') for _i in range(200)}), 200)

    def test_un_pedido_largo_se_recorta_pero_nunca_el_azar(self):
        for numero in ('S' + '0' * 40, 'WEB/2026/00012345-XYZ', 'ÁÉÍ-ñ-0001', '', '----'):
            with self.subTest(numero=numero):
                orden = api.orden_nueva(numero)
                self.assertTrue(api.orden_valida(orden), orden)
                self.assertGreaterEqual(len(orden), 5)
        largo = api.orden_nueva('S' + '0' * 40)
        self.assertEqual(len(largo), 15)
        self.assertTrue(largo.startswith('S000000000'))

    def test_orden_valida(self):
        self.assertEqual(api.orden_valida('A'), 'A')
        self.assertEqual(api.orden_valida('A' * 15), 'A' * 15)
        for mala in ('', 'A' * 16, 'a-b', 'a b', 'ñ', None, 5, 'ABC\n'):
            self.assertIsNone(api.orden_valida(mala), repr(mala))

    def test_celular_de_yappy(self):
        for escrito, limpio in (('6000 0101', '60000101'), ('6000-0101', '60000101'), ('(6000) 0101', '60000101'),
                                ('+507 6000-0101', '60000101'), ('507 60000101', '60000101'),
                                ('00507 6000 0101', '60000101'), ('  60000101 ', '60000101'),
                                ('6123.4567', '61234567')):
            with self.subTest(escrito=escrito):
                self.assertEqual(api.celular_de_yappy(escrito), limpio)
        for malo in ('', '1234567', '123456789', '0000 0101', '1000 0101', 'abcdefgh', '6000 010', '+1 6000 0101',
                     '+507 6000 01010', None, 60000101, '6' * 41, '６００００１０１'):
            with self.subTest(malo=malo):
                self.assertIsNone(api.celular_de_yappy(malo))

    def test_los_importes_van_con_dos_decimales(self):
        self.assertEqual(api.importe(64.19), '64.19')
        self.assertEqual(api.importe(5), '5.00')
        self.assertEqual(api.importe(0.1 + 0.2 - 0.3 + 107), '107.00')

    def test_los_dominios_aceptados_son_solo_nuestros(self):
        aceptados = api.dominios_aceptados('dcasapty.com')
        for forma in ('dcasapty.com', 'www.dcasapty.com', 'https://dcasapty.com', 'https://www.dcasapty.com/'):
            self.assertIn(forma, aceptados)
        for forma in aceptados:
            self.assertIn('dcasapty.com', forma)
            self.assertTrue(forma.replace('https://', '').replace('www.', '').rstrip('/') == 'dcasapty.com', forma)
        # Si se declaró con https y barra, se acepta tal cual y también sin ellas.
        declarado = api.dominios_aceptados('https://Mi-Sitio.com/')
        self.assertIn('https://Mi-Sitio.com/', declarado)
        self.assertIn('mi-sitio.com', declarado)
        self.assertEqual(api.dominios_aceptados(''), ())
        self.assertEqual(api.dominios_aceptados(None), ())

    def test_el_script_de_yappy_solo_puede_ser_el_de_su_cdn_por_https(self):
        self.assertTrue(api.anfitrion_del_cdn_permitido(api.cdn(api.PRODUCCION)))
        self.assertTrue(api.anfitrion_del_cdn_permitido(api.cdn(api.PRUEBA)))
        self.assertEqual(api.cdn(api.PRODUCCION), 'https://bt-cdn.yappy.cloud/v1/cdn/web-component-btn-yappy.js')
        self.assertEqual(api.cdn(api.PRUEBA), 'https://bt-cdn-uat.yappycloud.com/v1/cdn/web-component-btn-yappy.js')
        # el host del EJEMPLO: no responde
        for malo in ('https://bt-cdn.yappycloud.com/v1/cdn/web-component-btn-yappy.js',
                     'http://bt-cdn.yappy.cloud/v1/cdn/web-component-btn-yappy.js',
                     'https://evil.com/v1/cdn/web-component-btn-yappy.js',
                     'https://bt-cdn.yappy.cloud.evil.com/v1/cdn/web-component-btn-yappy.js',
                     'https://bt-cdn.yappy.cloud/otro.js', '', None):
            self.assertFalse(api.anfitrion_del_cdn_permitido(malo), malo)

    def test_los_servidores_son_los_de_la_documentacion(self):
        self.assertEqual(api.HOSTS[api.PRODUCCION], 'https://apipagosbg.bgeneral.cloud')
        self.assertEqual(api.HOSTS[api.PRUEBA], 'https://api-comecom-uat.yappycloud.com')

    def test_las_claves_no_salen_ni_imprimiendo_el_objeto(self):
        creds = credenciales()
        for texto in (repr(creds), str(creds), f'{creds}', '%s' % (creds,)):  # noqa: UP031
            for secreto in SECRETOS:
                self.assertNotIn(secreto, texto)

    def test_sin_una_de_las_variables_no_hay_credenciales_y_faltantes_dice_cual(self):
        for variable in ('YAPPY_ID_COMERCIO', 'YAPPY_CLAVE_SECRETA', 'YAPPY_DOMINIO'):
            with self.subTest(falta=variable), entorno(**{variable: None}):
                self.assertIsNone(api.credenciales())
                self.assertEqual(api.faltantes(), [variable])
        with entorno(YAPPY_CLAVE_SECRETA='!!no-es-base64!!'):
            self.assertIsNone(api.credenciales())
            self.assertEqual(len(api.faltantes()), 1)
            self.assertNotIn('no-es-base64', api.faltantes()[0], 'dice cuál falla, nunca su valor')
        with entorno():
            self.assertEqual(api.faltantes(), [])
            self.assertIsNotNone(api.credenciales())

    def test_el_entorno_por_defecto_es_prueba_y_produccion_exige_el_servidor_de_produccion(self):
        with entorno(YAPPY_ENTORNO=None, DCASA_ENTORNO=None):
            self.assertEqual(api.entorno_esperado(), api.PRUEBA)
        with entorno(YAPPY_ENTORNO='produccion', DCASA_ENTORNO=None):
            self.assertEqual(api.entorno_pedido(), api.PRODUCCION)
            self.assertEqual(api.entorno_esperado(), api.PRUEBA, 'aquí no es el servidor de producción')
        with entorno(YAPPY_ENTORNO='produccion', DCASA_ENTORNO='staging'):
            self.assertEqual(api.entorno_esperado(), api.PRUEBA)
        with entorno(YAPPY_ENTORNO='produccion', DCASA_ENTORNO='produccion'):
            self.assertEqual(api.entorno_esperado(), api.PRODUCCION)
        with entorno(YAPPY_ENTORNO='cualquier cosa', DCASA_ENTORNO='produccion'):
            self.assertEqual(api.entorno_esperado(), api.PRUEBA)

    def test_limpiar_quita_claves_tokens_y_saltos(self):
        sucio = f'hola {CLAVE_BASE64} y {ID_COMERCIO}\ncon un token ' + 'a' * 40 + '\t<b>fin</b>'
        limpio = api.limpiar(sucio, secretos=[ID_COMERCIO, CLAVE_BASE64])
        for secreto in (ID_COMERCIO, CLAVE_BASE64, 'a' * 40, '\n', '\t'):
            self.assertNotIn(secreto, limpio)
        self.assertLessEqual(len(api.limpiar('x ' * 400)), api.LARGO_TEXTO)


@tagged('post_install', '-at_install')
class TestCliente(BaseCase):
    """El cliente HTTP con un Yappy falso: ni una llamada real."""

    def setUp(self):
        super().setUp()
        self.addCleanup(entorno().start().stop)
        self.cliente = api.Cliente(credenciales(), api.PRUEBA)

    def crear(self, yappy, orden='S00008K3F9Q', celular=CELULAR_LIMPIO, total='64.19'):
        return self.cliente.crear_orden(orden, celular, total, 'https://dcasapty.com/payment/yappy/ipn')

    def test_valida_el_comercio_y_despues_crea_la_orden_en_ese_orden_con_el_cuerpo_exacto(self):
        with YappyFalso() as yappy:
            datos = self.crear(yappy)
        self.assertEqual(
            [llamada[0] for llamada in yappy.llamadas], ['/payments/validate/merchant', '/payments/payment-wc'])
        ruta, cuerpo, cabeceras = yappy.llamadas[0]
        self.assertEqual(cuerpo, {'merchantId': ID_COMERCIO, 'urlDomain': DOMINIO})
        self.assertNotIn('Authorization', cabeceras)
        ruta, cuerpo, cabeceras = yappy.llamadas[1]
        self.assertEqual(
            cabeceras['Authorization'], yappy.token, 'el token solo, sin «Bearer» (por confirmar con Yappy)')
        self.assertEqual(list(cuerpo), ['merchantId', 'orderId', 'domain', 'paymentDate', 'aliasYappy', 'ipnUrl',
                                        'discount', 'taxes', 'subtotal', 'total'], 'los campos, en el orden de la guía')
        self.assertEqual(cuerpo['merchantId'], ID_COMERCIO)
        self.assertEqual(cuerpo['orderId'], 'S00008K3F9Q')
        self.assertEqual(cuerpo['domain'], DOMINIO)
        self.assertIsInstance(cuerpo['paymentDate'], int)
        self.assertEqual(cuerpo['aliasYappy'], CELULAR_LIMPIO)
        self.assertEqual(cuerpo['ipnUrl'], 'https://dcasapty.com/payment/yappy/ipn')
        self.assertEqual((cuerpo['discount'], cuerpo['taxes'], cuerpo['subtotal'], cuerpo['total']),
                         ('0.00', '0.00', '64.19', '64.19'), 'los importes son cadenas con dos decimales')
        self.assertEqual(set(datos), {'transactionId', 'token', 'documentName'})

    def test_el_modo_decide_el_servidor_y_la_prueba_nunca_toca_produccion(self):
        with YappyFalso() as yappy, patch.object(requests, 'post', wraps=requests.post) as espia:
            self.crear(yappy)
        urls = [llamada.args[0] for llamada in espia.call_args_list]
        self.assertTrue(all(url.startswith('https://api-comecom-uat.yappycloud.com/') for url in urls), urls)
        with YappyFalso() as yappy, patch.object(requests, 'post', wraps=requests.post) as espia:
            api.Cliente(credenciales(), api.PRODUCCION).crear_orden('S00008K3F9Q', CELULAR_LIMPIO, '5.00', 'https://x.com/i')
        self.assertTrue(espia.call_args_list[0].args[0].startswith('https://apipagosbg.bgeneral.cloud/'))

    def test_E007_es_ya_estaba_y_no_un_fallo(self):
        with YappyFalso() as yappy:
            self.crear(yappy)
            with self.assertRaises(api.ErrorYappy) as ctx:
                self.crear(yappy)      # la misma orden otra vez
        self.assertEqual((ctx.exception.tipo, ctx.exception.codigo), ('ya_estaba', 'E007'))

    def test_los_errores_de_yappy_traen_su_codigo(self):
        for codigo in ('E005', 'E009', 'E010', 'E011', 'E100', 'E002', 'E006', 'E008', 'E012'):
            with self.subTest(codigo=codigo), YappyFalso() as yappy:
                yappy.errores[api.RUTA_ORDEN] = codigo
                with self.assertRaises(api.ErrorYappy) as ctx:
                    self.crear(yappy)
                self.assertEqual((ctx.exception.tipo, ctx.exception.codigo), ('rechazo', codigo))

    def test_un_numero_no_registrado_es_E005(self):
        with YappyFalso() as yappy:
            yappy.no_registrados.add(CELULAR_LIMPIO)
            with self.assertRaises(api.ErrorYappy) as ctx:
                self.crear(yappy)
        self.assertEqual(ctx.exception.codigo, 'E005')

    def test_lo_que_no_se_puede_mandar_ni_sale(self):
        for malo, cambios in (('orden larga', {'orden': 'A' * 16}), ('orden con guion', {'orden': 'S-0008'}),
                              ('celular', {'celular': '123'}), ('total cero', {'total': '0.00'}),
                              ('total sin decimales', {'total': '64'}), ('total negativo', {'total': '-5.00'}),
                              ('total con coma', {'total': '64,19'})):
            with self.subTest(malo), YappyFalso() as yappy:
                with self.assertRaises(api.ErrorYappy):
                    self.crear(yappy, **cambios)
                self.assertEqual(yappy.llamadas, [], 'no se gasta una llamada en algo que Yappy no aceptaría')

    def test_el_minimo_de_un_centavo_se_manda(self):
        with YappyFalso() as yappy:
            self.crear(yappy, total='0.01')
        self.assertEqual(yappy.ultima_orden()['total'], '0.01')

    def test_si_yappy_no_valida_el_comercio_no_se_intenta_crear_la_orden(self):
        with entorno(YAPPY_DOMINIO='otro-dominio.com'), YappyFalso() as yappy:
            cliente = api.Cliente(api.credenciales(), api.PRUEBA)
            with self.assertRaises(api.ErrorYappy) as ctx:
                cliente.crear_orden('S00008K3F9Q', CELULAR_LIMPIO, '5.00', 'https://x.com/i')
        self.assertEqual(ctx.exception.tipo, 'comercio')
        self.assertEqual(len(yappy.llamadas), 1)

    def test_respuestas_raras_son_errores_que_no_pagan_ni_revientan(self):
        for falla, tipo in (('tiempo', 'red'), ('red', 'red'), ('html', 'respuesta'), ('lista', 'respuesta'),
                            ('http500', 'comercio'), ('sin_body', 'comercio'), ('sin_token', 'comercio')):
            with self.subTest(falla=falla), YappyFalso() as yappy:
                yappy.falla = falla
                with self.assertRaises(api.ErrorYappy) as ctx:
                    self.crear(yappy)
                self.assertEqual(ctx.exception.tipo, tipo)
        for falla in ('orden_sin_body', 'sin_transaccion'):
            with self.subTest(falla_en_la_orden=falla), YappyFalso() as yappy:
                yappy.falla = falla
                with self.assertRaises(api.ErrorYappy) as ctx:
                    self.crear(yappy)
                self.assertEqual(ctx.exception.tipo, 'rechazo')

    def test_los_mensajes_de_error_no_filtran_claves(self):
        with YappyFalso() as yappy:
            yappy.errores[api.RUTA_VALIDAR] = 'E100'
            with self.assertRaises(api.ErrorYappy) as ctx:
                self.crear(yappy)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, str(ctx.exception))
            self.assertNotIn(secreto, ctx.exception.detalle)

    def test_ningun_registro_trae_claves_ni_tokens(self):
        with self.assertLogs('odoo.addons.dcasa_pago_yappy', level='DEBUG') as registro, YappyFalso() as yappy:
            self.crear(yappy)
            yappy.falla = 'html'
            with self.assertRaises(api.ErrorYappy):
                self.crear(yappy, orden='S00009AAAAA')
            yappy.falla = 'tiempo'
            with self.assertRaises(api.ErrorYappy):
                self.crear(yappy, orden='S00009BBBBB')
        texto = '\n'.join(registro.output)
        for secreto in SECRETOS + (yappy.token,):
            self.assertNotIn(secreto, texto)
        self.assertNotIn(CELULAR_LIMPIO, texto, 'el celular de la clienta no va al registro')

    def test_el_tope_de_llamadas_a_la_vez_no_espera_y_se_suelta_siempre(self):
        self.assertEqual(api.llamadas_en_vuelo(), 0)
        with self.assertRaises(RuntimeError), api.cupo():
            self.assertEqual(api.llamadas_en_vuelo(), 1)
            raise RuntimeError('pase lo que pase')
        self.assertEqual(api.llamadas_en_vuelo(), 0, 'el cupo se suelta aunque algo falle')
        abiertos = []
        try:
            for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                gestor = api.cupo()
                gestor.__enter__()
                abiertos.append(gestor)
            self.assertFalse(api.hay_cupo())
            with YappyFalso() as yappy, self.assertRaises(api.ErrorYappy) as ctx:
                self.crear(yappy)
            self.assertEqual(ctx.exception.tipo, 'ocupado')
            self.assertEqual(yappy.llamadas, [], 'con el tope lleno ni se intenta')
        finally:
            for gestor in abiertos:
                gestor.__exit__(None, None, None)
        self.assertEqual(api.llamadas_en_vuelo(), 0)
        self.assertTrue(api.hay_cupo())

    def test_con_hilos_de_verdad_nunca_pasan_mas_del_tope(self):
        maximo, candado = [0], threading.Lock()
        puerta = threading.Event()

        def trabajar():
            try:
                with api.cupo():
                    with candado:
                        maximo[0] = max(maximo[0], api.llamadas_en_vuelo())
                    puerta.wait(0.2)
            except api.ErrorYappy:
                pass

        hilos = [threading.Thread(target=trabajar) for _i in range(30)]
        for hilo in hilos:
            hilo.start()
        puerta.set()
        for hilo in hilos:
            hilo.join()
        self.assertLessEqual(maximo[0], api.TOPE_DE_LLAMADAS_A_LA_VEZ)
        self.assertEqual(api.llamadas_en_vuelo(), 0)

