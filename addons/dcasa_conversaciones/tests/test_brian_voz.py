"""Las notas de voz de Brian del panel pasan a texto en el Worker de Juan (``models/brian_voz.py``).

Odoo llama a ``POST /odoo/voz`` con el token de siempre, manda el audio una vez, devuelve solo el texto y no guarda
nada.
"""
import base64
import logging
from contextlib import contextmanager

from odoo.addons.dcasa_conversaciones.models.brian_voz import TIMEOUT_VOZ
from odoo.addons.dcasa_conversaciones.models.panel_juan import renglones_de_cloudflare
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import TOKEN_WORKER, URL_WORKER, JuanCase, respuesta_http

DICHO = 'Brian, ¿cuánto se vendió hoy en la tienda?'
# Lo que graba Chrome empieza así (EBML).
WEBM = b'\x1a\x45\xdf\xa3' + b'\x9f\x42\x86\x81\x01' + b'\x00' * 400


@contextmanager
def registros():
    """Todo lo que Odoo escribe en sus registros (en cualquier nivel) mientras dura el bloque."""
    lineas = []

    class Captura(logging.Handler):
        def emit(self, record):
            lineas.append(record.getMessage())

    captura = Captura(logging.DEBUG)
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.addHandler(captura)
    raiz.setLevel(logging.DEBUG)
    try:
        yield lineas
    finally:
        raiz.removeHandler(captura)
        raiz.setLevel(nivel)


@tagged('post_install', '-at_install')
class TestBrianVozWorker(JuanCase):

    def contar(self):
        modelos = ['ir.attachment', 'brian.conversacion', 'brian.mensaje', 'brian.accion', 'mail.message']
        return {m: self.env[m].sudo().with_context(active_test=False).search_count([]) for m in modelos}

    def test_sin_worker_no_hay_microfono(self):
        voz = self.env['dcasa.brian.voz'].with_user(self.interno)
        self.assertFalse(voz.disponible())
        r = voz.transcribir(base64.b64encode(WEBM).decode(), 'audio/webm')
        self.assertEqual(r['causa'], 'no_disponible')

    def test_manda_el_audio_al_worker_una_vez_y_devuelve_solo_el_texto(self):
        worker = self.configurar_worker()
        worker.return_value = respuesta_http({'ok': True, 'texto': DICHO, 'recortado': False})
        voz = self.env['dcasa.brian.voz'].with_user(self.interno)
        self.assertTrue(voz.disponible())
        audio = base64.b64encode(WEBM).decode()
        antes = self.contar()
        with registros() as lineas:
            r = voz.transcribir(audio, 'audio/webm;codecs=opus', 3500)
        self.assertEqual(r, {'ok': True, 'texto': DICHO, 'recortado': False})
        worker.assert_called_once()
        metodo, url = worker.call_args.args
        self.assertEqual((metodo, url), ('POST', f'{URL_WORKER}/odoo/voz'))
        self.assertEqual(worker.call_args.kwargs['headers']['Authorization'], f'Bearer {TOKEN_WORKER}')
        self.assertEqual(worker.call_args.kwargs['json'], {'mime': 'audio/webm;codecs=opus', 'base64': audio,
                                                           'usuario': self.interno.id, 'duracion_ms': 3500})
        self.assertEqual(worker.call_args.kwargs['timeout'], TIMEOUT_VOZ)
        self.assertEqual(self.contar(), antes, 'Odoo no guarda nada de una nota de voz')
        todo = '\n'.join(lineas)
        for prohibido in (audio[:40], DICHO, TOKEN_WORKER):
            self.assertNotIn(prohibido, todo)

    def test_lo_que_dice_el_worker_llega_en_palabras_sencillas(self):
        worker = self.configurar_worker()
        voz = self.env['dcasa.brian.voz'].with_user(self.interno)
        audio = base64.b64encode(WEBM).decode()
        for estado, cuerpo, causa in (
            (429, {'ok': False, 'causa': 'tope_usuario', 'error': 'Llegaste al tope de notas de voz por hora.'},
             'tope_usuario'),
            (503, {'ok': False, 'causa': 'no_disponible', 'error': 'TRANSCRIBIR_AUDIO'}, 'no_disponible'),
            (413, {'ok': False, 'causa': 'muy_larga'}, 'muy_larga'),
            (500, {}, 'fallo'),
        ):
            with self.subTest(causa=causa):
                worker.return_value = respuesta_http(cuerpo, estado)
                r = voz.transcribir(audio, 'audio/webm')
                self.assertEqual(r['causa'], causa)
                self.assertNotIn('TRANSCRIBIR_AUDIO', r['error'])

    def test_el_portal_no_llega_al_worker(self):
        worker = self.configurar_worker()
        with self.assertRaises(AccessError):
            voz = self.env['dcasa.brian.voz'].with_user(self.portal)
            voz.transcribir(base64.b64encode(WEBM).decode(), 'audio/webm')
        worker.assert_not_called()

    def test_costos_de_ia_nombra_el_renglon_de_las_notas_de_voz(self):
        renglones = renglones_de_cloudflare({'cloudflare': [
            {'concepto': 'cloudflare:notas-de-voz-del-panel', 'usd': 0.0021, 'lecturas': 7, 'estimado': False}]})
        self.assertEqual(renglones[0]['modelo'], 'Cloudflare: notas de voz del panel')
        self.assertEqual(renglones[0]['lecturas'], 7)
