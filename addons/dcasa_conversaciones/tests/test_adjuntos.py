"""Adjuntos del Worker: validación del contrato y descarga sin SSRF, con tope de tamaño."""
import base64
import socket
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import BaseCase, tagged

from ..models import adjuntos as A


def respuesta_falsa(contenido=b'datos', estado=200, cabeceras=None):
    respuesta = MagicMock()
    respuesta.status_code = estado
    respuesta.headers = cabeceras or {}
    respuesta.iter_content.return_value = iter([contenido[i:i + 4] for i in range(0, len(contenido), 4)])
    respuesta.__enter__.return_value = respuesta
    respuesta.__exit__.return_value = False
    return respuesta


def resolver(*direcciones):
    return patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (d, 0))
                                                     for d in direcciones])


@tagged('post_install', '-at_install')
class TestValidarAdjuntos(BaseCase):

    def test_adjunto_valido(self):
        adjunto = A.validar({'tipo': 'imagen', 'url': 'https://x.test/a.jpg', 'nombre': 'a.jpg', 'mime': 'image/jpeg'})
        self.assertEqual(adjunto, {'tipo': 'imagen', 'nombre': 'a.jpg', 'mime': 'image/jpeg',
                                   'url': 'https://x.test/a.jpg', 'base64': None, 'sensible': False})

    def test_los_cuatro_tipos_del_contrato(self):
        for tipo in ('imagen', 'audio', 'documento', 'video'):
            self.assertEqual(A.validar({'tipo': tipo, 'url': 'https://x.test/a'})['tipo'], tipo)

    def test_rechaza_lo_que_no_cumple_el_contrato(self):
        for malo in (None, 'texto', [], {'tipo': 'gif', 'url': 'https://x.test/a'}, {'tipo': 'imagen'},
                     {'tipo': 'imagen', 'url': 'https://x.test/a', 'base64': 'QQ=='},
                     {'tipo': 'imagen', 'url': 5}, {'tipo': 'imagen', 'url': 'https://x.test/' + 'a' * 3000},
                     {'tipo': 'imagen', 'base64': 7}):
            with self.subTest(malo=malo), self.assertRaises(A.AdjuntoInvalido):
                A.validar(malo)

    def test_limpia_nombre_y_mime(self):
        adjunto = A.validar({'tipo': 'documento', 'url': 'https://x.test/a', 'nombre': '../../etc/pass\x00wd',
                             'mime': 'texto raro'})
        self.assertNotIn('/', adjunto['nombre'])
        self.assertNotIn('\x00', adjunto['nombre'])
        self.assertEqual(adjunto['mime'], '')
        self.assertEqual(A.validar({'tipo': 'documento', 'url': 'https://x.test/a'})['nombre'], 'adjunto')

    def test_sensible_viene_del_worker(self):
        self.assertTrue(A.validar({'tipo': 'imagen', 'url': 'https://x.test/a', 'sensible': True})['sensible'])

    def test_lista(self):
        self.assertEqual(A.validar_lista(None), [])
        self.assertEqual(A.validar_lista([]), [])
        with self.assertRaises(A.AdjuntoInvalido):
            A.validar_lista({'tipo': 'imagen'})
        with self.assertRaises(A.AdjuntoInvalido):
            A.validar_lista([{'tipo': 'imagen', 'url': 'https://x.test/a'}] * (A.MAX_ADJUNTOS + 1))

    def test_tipo_segun_mime(self):
        self.assertEqual(A.tipo_de_mime('image/png'), 'imagen')
        self.assertEqual(A.tipo_de_mime('audio/ogg'), 'audio')
        self.assertEqual(A.tipo_de_mime('video/mp4'), 'video')
        self.assertEqual(A.tipo_de_mime('application/pdf'), 'documento')
        self.assertEqual(A.tipo_de_mime(None), 'documento')


@tagged('post_install', '-at_install')
class TestDescargaSegura(BaseCase):

    def test_direcciones(self):
        for publica in ('8.8.8.8', '1.1.1.1', '2606:4700:4700::1111'):
            self.assertTrue(A.direccion_publica(publica), publica)
        for interna in ('127.0.0.1', '10.0.0.5', '172.16.3.4', '192.168.1.1', '169.254.169.254', '0.0.0.0',
                        '::1', 'fe80::1', 'fc00::1', '224.0.0.1', '::ffff:127.0.0.1', '100.64.0.1', 'no-es-ip'):
            self.assertFalse(A.direccion_publica(interna), interna)

    def test_url_permitida(self):
        with resolver('93.184.216.34'):
            self.assertTrue(A.url_permitida('https://media.example.com/a.jpg'))
            self.assertTrue(A.url_permitida('http://media.example.com:80/a.jpg'))

    def test_url_prohibida(self):
        with resolver('93.184.216.34'):
            for url in ('ftp://x.test/a', 'file:///etc/passwd', 'https://x.test:8069/a', 'https://user:pw@x.test/a',
                        'javascript:alert(1)', 'https:///sin-host', 'no es url'):
                with self.subTest(url=url):
                    self.assertFalse(A.url_permitida(url))

    def test_url_que_resuelve_a_una_red_interna(self):
        for interna in ('127.0.0.1', '10.1.2.3', '169.254.169.254'):
            with resolver(interna), self.subTest(interna=interna):
                self.assertFalse(A.url_permitida('https://interno.example.com/a'))
        # Si UNA de las direcciones es interna, no se descarga.
        with resolver('93.184.216.34', '10.0.0.9'):
            self.assertFalse(A.url_permitida('https://mixto.example.com/a'))

    def test_url_que_no_resuelve(self):
        with patch('socket.getaddrinfo', side_effect=socket.gaierror):
            self.assertFalse(A.url_permitida('https://no-existe.example.com/a'))

    def test_descarga_normal(self):
        with resolver('93.184.216.34'), patch('requests.get', return_value=respuesta_falsa(b'0123456789')) as get:
            self.assertEqual(A.descargar('https://media.example.com/a.jpg'), b'0123456789')
        # Sin redirecciones: una redirección podría saltarse la comprobación de la red.
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertTrue(get.call_args.kwargs['stream'])

    def test_no_descarga_de_redes_internas(self):
        with resolver('127.0.0.1'), patch('requests.get') as get:
            self.assertIsNone(A.descargar('https://interno.example.com/a'))
        get.assert_not_called()

    def test_tope_de_tamano(self):
        with resolver('93.184.216.34'):
            with patch('requests.get', return_value=respuesta_falsa(b'x' * 100)):
                self.assertIsNone(A.descargar('https://media.example.com/a', max_bytes=50))
            declarado = respuesta_falsa(b'x', cabeceras={'Content-Length': '99999999'})
            with patch('requests.get', return_value=declarado):
                self.assertIsNone(A.descargar('https://media.example.com/a', max_bytes=1000))

    def test_errores_de_red_y_estados_distintos_de_200(self):
        with resolver('93.184.216.34'):
            with patch('requests.get', return_value=respuesta_falsa(estado=404)):
                self.assertIsNone(A.descargar('https://media.example.com/a'))
            with patch('requests.get', return_value=respuesta_falsa(estado=302)):
                self.assertIsNone(A.descargar('https://media.example.com/a'))
            with patch('requests.get', side_effect=requests.ConnectionError('boom')):
                self.assertIsNone(A.descargar('https://media.example.com/a'))
            with patch('requests.get', return_value=respuesta_falsa(b'')):
                self.assertIsNone(A.descargar('https://media.example.com/a'))

    def test_base64(self):
        codificado = base64.b64encode(b'hola mundo').decode()
        self.assertEqual(A.decodificar_base64(codificado), b'hola mundo')
        self.assertEqual(A.decodificar_base64('data:text/plain;base64,' + codificado), b'hola mundo')
        self.assertIsNone(A.decodificar_base64('esto no es base64 !!'))
        self.assertIsNone(A.decodificar_base64(''))
        self.assertIsNone(A.decodificar_base64(base64.b64encode(b'x' * 100).decode(), max_bytes=10))

    def test_obtener_contenido_usa_base64_o_url(self):
        adjunto = A.validar({'tipo': 'documento', 'base64': base64.b64encode(b'abc').decode()})
        self.assertEqual(A.obtener_contenido(adjunto), b'abc')
        with patch.object(A, 'descargar', return_value=b'desde url') as descargar:
            self.assertEqual(A.obtener_contenido(A.validar({'tipo': 'imagen', 'url': 'https://x.test/a'})), b'desde url')
        descargar.assert_called_once_with('https://x.test/a')
