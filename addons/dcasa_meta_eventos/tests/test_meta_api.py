"""Normalización y hash como pide Meta, y el envío sin filtrar el token (funciones puras de meta_api)."""
import hashlib
import json
from unittest.mock import patch

import requests

from odoo.tests import BaseCase, tagged

from ..models import meta_api
from .common import respuesta

TOKEN = 'EAAprueba-token-de-meta-0000000000000000000000'


def sha(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


@tagged('post_install', '-at_install')
class TestNormalizacionYHash(BaseCase):

    def test_el_correo_con_mayusculas_y_espacios_da_el_mismo_hash(self):
        esperado = sha('cliente.prueba@example.com')
        for escrito in ('cliente.prueba@example.com', '  Cliente.Prueba@Example.COM ', 'CLIENTE.PRUEBA@EXAMPLE.COM'):
            with self.subTest(escrito=escrito):
                self.assertEqual(meta_api.hash_correo(escrito), esperado)
        self.assertIsNone(meta_api.hash_correo('no es un correo'))
        self.assertIsNone(meta_api.hash_correo(''))

    def test_el_celular_de_panama_lleva_el_507_y_solo_digitos(self):
        esperado = sha('50760261919')
        for escrito in ('6026-1919', '+507 6026 1919', '00507 6026 1919', '507 6026-1919', '(507) 6026-1919'):
            with self.subTest(escrito=escrito):
                self.assertEqual(meta_api.hash_telefono(escrito), esperado)

    def test_un_numero_de_otro_pais_conserva_sus_digitos(self):
        self.assertEqual(meta_api.hash_telefono('+1 305 555 0100'), sha('13055550100'))
        self.assertEqual(meta_api.hash_telefono('0034 612 345 678'), sha('34612345678'))
        self.assertIsNone(meta_api.hash_telefono('123'))

    def test_el_hash_es_sha256_hexadecimal_en_minusculas_una_sola_vez(self):
        valor = meta_api.hash_correo('cliente.prueba@example.com')
        self.assertRegex(valor, r'^[0-9a-f]{64}$')
        self.assertNotEqual(valor, sha(valor), 'Nunca un hash del hash')
        # Un hash no es un correo: no se vuelve a cifrar por error.
        self.assertIsNone(meta_api.hash_correo(valor))

    def test_id_externo_y_pais(self):
        self.assertEqual(meta_api.hash_id_externo(42), sha('dcasa-42'))
        self.assertEqual(meta_api.hash_pais('PA'), sha('pa'))
        self.assertIsNone(meta_api.hash_pais('CR'), 'De otros países no se manda nada (sin verificar con Meta)')

    def test_fbp_y_fbc_se_guardan_tal_cual_si_tienen_la_forma(self):
        self.assertEqual(meta_api.fbp_valida('fb.1.1596403881668.1116446470'), 'fb.1.1596403881668.1116446470')
        self.assertEqual(meta_api.fbc_valida('fb.1.1554763741205.AbCdEf_-123'), 'fb.1.1554763741205.AbCdEf_-123')
        for basura in ('', 'hola', 'fb.1.123.<script>', 'x' * 900):
            with self.subTest(basura=basura):
                self.assertIsNone(meta_api.fbp_valida(basura))
                self.assertIsNone(meta_api.fbc_valida(basura))


@tagged('post_install', '-at_install')
class TestEnvio(BaseCase):

    def test_limpiar_error_quita_el_token_los_hashes_y_los_correos(self):
        texto = (f'fallo con access_token={TOKEN}&x=1 {TOKEN} de cliente.prueba@example.com '
                 f'hash {sha("algo")} "access_token": "otro-secreto"')
        limpio = meta_api.limpiar_error(texto, TOKEN)
        for prohibido in (TOKEN, 'cliente.prueba@example.com', sha('algo'), 'otro-secreto'):
            self.assertNotIn(prohibido, limpio)
        eco = meta_api.limpiar_error('Invalid client_ip_address 203.0.113.7 / 2001:db8::7 fbc fb.1.1554763741205.AbC_1')
        for prohibido in ('203.0.113.7', '2001:db8::7', 'fb.1.1554763741205.AbC_1'):
            self.assertNotIn(prohibido, eco, 'Meta puede repetir en su error un dato del evento')
        self.assertIn('HTTP 500', meta_api.limpiar_error('HTTP 500 · código 2'), 'Lo útil queda')
        self.assertLessEqual(len(meta_api.limpiar_error('x' * 2000, TOKEN)), 500)

    def test_clasificar(self):
        self.assertEqual(meta_api.clasificar(200, {'events_received': 1})[0], meta_api.OK)
        self.assertEqual(meta_api.clasificar(401, {})[0], meta_api.TOKEN)
        self.assertEqual(meta_api.clasificar(400, {'error': {'code': 190}})[0], meta_api.TOKEN)
        self.assertEqual(meta_api.clasificar(500, {})[0], meta_api.REINTENTAR)
        self.assertEqual(meta_api.clasificar(429, {})[0], meta_api.REINTENTAR)
        self.assertEqual(meta_api.clasificar(400, {'error': {'code': 100}})[0], meta_api.INVALIDO)

    def test_el_token_va_en_el_cuerpo_y_nunca_en_la_url(self):
        with patch('requests.post', return_value=respuesta()) as post:
            resultado = meta_api.enviar([{'event_name': 'PageView'}], '123456789012345', 'v26.0', TOKEN, 'TEST1')
        self.assertEqual(resultado['tipo'], meta_api.OK)
        self.assertEqual(resultado['fbtrace_id'], 'AbCdEfTrace')
        post.assert_called_once()
        url = post.call_args.args[0]
        self.assertEqual(url, 'https://graph.facebook.com/v26.0/123456789012345/events')
        self.assertNotIn(TOKEN, url)
        datos = post.call_args.kwargs['data']
        self.assertEqual(datos['access_token'], TOKEN)
        self.assertEqual(datos['test_event_code'], 'TEST1')
        self.assertEqual(json.loads(datos['data']), [{'event_name': 'PageView'}])
        self.assertEqual(post.call_args.kwargs['timeout'], (5, 20))

    def test_sin_codigo_de_prueba_no_lo_manda(self):
        with patch('requests.post', return_value=respuesta()) as post:
            meta_api.enviar([{}], '123456789012345', 'v26.0', TOKEN)
        self.assertNotIn('test_event_code', post.call_args.kwargs['data'])

    def test_sin_token_o_con_un_id_raro_no_llama_a_nadie(self):
        with patch('requests.post') as post:
            self.assertEqual(meta_api.enviar([{}], '123456789012345', 'v26.0', '')['tipo'], meta_api.TOKEN)
            self.assertEqual(meta_api.enviar([{}], '12a', 'v26.0', TOKEN)['tipo'], meta_api.INVALIDO)
            self.assertEqual(meta_api.enviar([{}], '123456789012345', '26', TOKEN)['tipo'], meta_api.INVALIDO)
        post.assert_not_called()

    def test_un_error_de_red_no_lanza_ni_filtra_el_token(self):
        error = requests.ConnectionError(f'no hay red para https://graph.facebook.com/?access_token={TOKEN}')
        with patch('requests.post', side_effect=error):
            resultado = meta_api.enviar([{}], '123456789012345', 'v26.0', TOKEN)
        self.assertEqual(resultado['tipo'], meta_api.REINTENTAR)
        self.assertNotIn(TOKEN, resultado['mensaje'])

    def test_un_error_de_meta_no_filtra_el_token_en_el_mensaje(self):
        cuerpo = {'error': {'code': 100, 'message': f'Invalid parameter (token {TOKEN})', 'fbtrace_id': 'Tr4ce'}}
        with patch('requests.post', return_value=respuesta(400, cuerpo)):
            resultado = meta_api.enviar([{}], '123456789012345', 'v26.0', TOKEN)
        self.assertEqual(resultado['tipo'], meta_api.INVALIDO)
        self.assertNotIn(TOKEN, resultado['mensaje'])
        self.assertEqual(resultado['fbtrace_id'], 'Tr4ce')
