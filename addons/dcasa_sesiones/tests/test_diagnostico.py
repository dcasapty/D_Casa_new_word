import logging
from collections import deque

from odoo.tests import BaseCase, tagged

from .. import diagnostico


def aplicacion_con(estado, cuerpo=b'<h1>Internal Server Error</h1>'):
    def aplicacion(self, environ, start_response):
        start_response(estado, [('Content-Type', 'text/html'), ('Content-Length', str(len(cuerpo)))])
        return [cuerpo]
    return aplicacion


def llamar(app, ruta):
    respuesta = {}

    def start_response(estado, cabeceras, exc_info=None):
        respuesta['estado'], respuesta['cabeceras'] = estado, dict(cabeceras)

    cuerpo = b''.join(app(None, {'PATH_INFO': ruta}, start_response))
    return respuesta, cuerpo


@tagged('post_install', '-at_install')
class TestDiagnosticoDeSalud(BaseCase):

    def test_un_500_de_la_ruta_de_salud_se_explica_con_los_ultimos_errores(self):
        ultimos = deque(['KeyError: x @ http.py:99'], maxlen=5)
        app = diagnostico.envolver(aplicacion_con('500 INTERNAL SERVER ERROR'), ultimos)
        respuesta, cuerpo = llamar(app, '/dcasa/salud')
        self.assertTrue(respuesta['estado'].startswith('503'))
        self.assertIn(b'KeyError: x', cuerpo)
        self.assertEqual(respuesta['cabeceras']['Content-Length'], str(len(cuerpo)))

    def test_un_200_de_salud_pasa_igual(self):
        app = diagnostico.envolver(aplicacion_con('200 OK', b'{"ok": true}'), deque())
        respuesta, cuerpo = llamar(app, '/dcasa/salud')
        self.assertEqual((respuesta['estado'], cuerpo), ('200 OK', b'{"ok": true}'))

    def test_otras_rutas_no_se_tocan_ni_con_500(self):
        app = diagnostico.envolver(aplicacion_con('500 INTERNAL SERVER ERROR'), deque(['algo']))
        respuesta, cuerpo = llamar(app, '/shop')
        self.assertEqual(respuesta['estado'], '500 INTERNAL SERVER ERROR')
        self.assertNotIn(b'algo', cuerpo)

    def test_guarda_clase_mensaje_y_sitio_pero_no_la_traza(self):
        ultimos = deque(maxlen=5)
        registro = logging.getLogger('prueba.diagnostico')
        registro.propagate = False
        registro.addHandler(diagnostico.GuardarErrores(ultimos))
        try:
            raise ValueError('falla de prueba')
        except ValueError:
            registro.exception('Exception during request handling.')
        registro.info('esto no es un error')
        self.assertEqual(len(ultimos), 1)
        self.assertIn('ValueError: falla de prueba', ultimos[0])
        self.assertIn('test_diagnostico.py', ultimos[0])
        self.assertNotIn('Traceback', ultimos[0])

    def test_un_error_repetido_se_guarda_una_sola_vez_y_el_tope_es_cinco(self):
        ultimos = deque()
        registro = logging.getLogger('prueba.diagnostico.repetidos')
        registro.propagate = False
        registro.addHandler(diagnostico.GuardarErrores(ultimos))
        for _veces in range(10):
            registro.error('siempre lo mismo')
        self.assertEqual(list(ultimos), ['prueba.diagnostico.repetidos: siempre lo mismo'])
        for numero in range(10):
            registro.error('error %s', numero)
        self.assertEqual(len(ultimos), diagnostico.MAXIMO_ERRORES)

    def test_solo_actua_en_staging(self):
        self.assertFalse(diagnostico.instalar('produccion'))
        self.assertFalse(diagnostico.instalar(''))
