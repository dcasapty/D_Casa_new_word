"""Notas de voz para Brian del panel (docs/BRIAN.md › «Notas de voz»).

La persona graba una indicación en el panel (el navegador, con MediaRecorder), la página la manda a
``/dcasa/brian/v1/voz`` (``controllers/voz.py``: solo usuarios internos) y el texto vuelve a la caja de Brian para que
la persona lo revise y lo mande como cualquier mensaje. **Odoo no transcribe**: lo hace el Worker de Juan (Whisper de
Workers AI, dentro de la cuenta de Cloudflare de D'CASA) con el token que Odoo ya usa para hablarle
(``POST /odoo/voz``, ``juan/src/odoo-panel-voz.ts``). Este módulo no sabe hablar con el Worker (eso es de
``dcasa_conversaciones``, que depende de este): aquí están las reglas y el «no disponible», y
``dcasa_conversaciones/models/brian_voz.py`` pone la llamada.

Lo que no se negocia (para que nadie use esto para clonar voces):

* El audio **no se guarda en Odoo**: ni adjunto, ni mensaje de Brian, ni auditoría, ni registro (log). Se valida, se
  reenvía una vez al Worker y se suelta.
* No se devuelve ni se usa para generar voz: solo vuelve el texto.
* Notas cortas (``MAX_SEGUNDOS``, ``MAX_BYTES``) y solo lo que graba un navegador (``TIPOS``). Los topes por persona,
  por día y el techo del mes los cuenta el Worker.
"""
import base64
import binascii
import re

from odoo import api, models
from odoo.exceptions import AccessError

# Lo que graba un navegador con MediaRecorder: Chrome y Edge WebM, Firefox Ogg, Safari MP4 (como el Worker).
TIPOS = ('audio/webm', 'audio/ogg', 'audio/mp4')
MAX_BYTES = 1024 * 1024
MAX_SEGUNDOS = 60
TOLERANCIA_SEGUNDOS = 5
# El audio en base64 pesa 4/3 más; el controlador no lee más que esto (más el sobre del JSON-RPC).
MAX_BASE64 = (MAX_BYTES + 2) // 3 * 4
MAX_LETRAS = 2000
RE_BASE64 = re.compile(r'^[A-Za-z0-9+/]+={0,2}$')
RE_CODECS = re.compile(r'^codecs=[\w.,"-]{1,40}$')

# Lo que se le dice a la persona por cada causa (el Worker manda la causa; nunca se muestra su texto técnico).
TEXTOS = {
    'no_disponible': 'Las notas de voz no están disponibles ahora. Escríbele a Brian.',
    'tipo': 'Tu navegador grabó en un formato que no puedo leer. Prueba con Chrome, Edge, Firefox o Safari al día.',
    'audio': 'No pude leer la nota de voz. Grábala otra vez.',
    'muy_pesada': 'La nota pasa de un minuto. Graba una más corta.',
    'muy_larga': 'La nota pasa de un minuto. Graba una más corta.',
    'tope_usuario': 'Mandaste muchas notas de voz en la última hora. Espera un rato o escríbele a Brian.',
    'tope_dia': 'El equipo llegó al tope de notas de voz de hoy. Escríbele a Brian.',
    'tope_mes': 'Las notas de voz llegaron a su tope del mes. Escríbele a Brian.',
    'no_se_entendio': 'No entendí lo que dijiste. Grábala otra vez, un poco más cerca del micrófono.',
    'tardo': 'La nota tardó demasiado en pasarse a texto. Inténtalo otra vez.',
    'fallo': 'No pude pasar la nota a texto ahora. Inténtalo en un momento o escríbele a Brian.',
}
# Las firmas de los tres tipos (los primeros bytes): WebM (EBML), Ogg («OggS») y MP4 (caja «ftyp» en el byte 4).
FIRMAS = {
    'audio/webm': lambda b: b[:4] == b'\x1a\x45\xdf\xa3',
    'audio/ogg': lambda b: b[:4] == b'OggS',
    'audio/mp4': lambda b: b[4:8] == b'ftyp',
}
RE_CONTROLES = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]+')


def _no(causa):
    return {'ok': False, 'causa': causa, 'error': TEXTOS.get(causa, TEXTOS['fallo'])}


class BrianVoz(models.AbstractModel):
    _name = 'dcasa.brian.voz'
    _description = 'Notas de voz de Brian (solo el texto; el audio no se guarda)'

    @api.model
    def _exigir_interno(self):
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(self.env._('Las notas de voz de Brian son solo para el equipo de D’CASA.'))

    @api.private
    @api.model
    def disponible(self):
        """¿Se muestra el micrófono? Sin el Worker conectado (``dcasa_conversaciones``), no."""
        self._exigir_interno()
        return bool(self._disponible())

    @api.model
    def _disponible(self):
        return False

    @api.model
    def _validar(self, audio, mime, duracion_ms):
        """``(mime_limpio, duracion_ms)`` o la causa (texto) por la que no sirve. Nunca repite el audio."""
        partes = [p.strip() for p in str(mime or '').lower().split(';')]
        tipo = partes[0]
        if tipo not in TIPOS or len(partes) > 2 or (len(partes) == 2 and not RE_CODECS.match(partes[1])):
            return 'tipo'
        if not isinstance(audio, str) or not audio:
            return 'audio'
        if len(audio) > MAX_BASE64:
            return 'muy_pesada'
        if len(audio) % 4 or not RE_BASE64.match(audio):
            return 'audio'
        try:
            cabeza = base64.b64decode(audio[:12], validate=True)
        except (binascii.Error, ValueError):
            return 'audio'
        if not FIRMAS[tipo](cabeza):
            return 'audio'
        if duracion_ms is not None:
            if isinstance(duracion_ms, bool) or not isinstance(duracion_ms, int) or duracion_ms < 0:
                return 'audio'
            if duracion_ms > (MAX_SEGUNDOS + TOLERANCIA_SEGUNDOS) * 1000:
                return 'muy_larga'
        return (';'.join(partes), duracion_ms)

    @api.private
    @api.model
    def transcribir(self, audio, mime, duracion_ms=None):
        """La nota de voz (base64) pasada a texto: ``{ok, texto, recortado}`` o ``{ok: False, causa, error}``.

        Solo usuarios internos. No crea ningún registro: ni adjunto, ni mensaje, ni auditoría."""
        self._exigir_interno()
        validado = self._validar(audio, mime, duracion_ms)
        if isinstance(validado, str):
            return _no(validado)
        tipo, duracion = validado
        respuesta = self._pedir_al_worker(audio, tipo, duracion) or {}
        texto = respuesta.get('texto') if respuesta.get('ok') is True else None
        if not isinstance(texto, str):
            causa = str(respuesta.get('causa') or 'fallo')
            return _no(causa if causa in TEXTOS else 'fallo')
        limpio = ' '.join(RE_CONTROLES.sub(' ', texto).split())
        if not limpio:
            return _no('no_se_entendio')
        return {'ok': True, 'texto': limpio[:MAX_LETRAS], 'recortado': bool(respuesta.get('recortado'))
                or len(limpio) > MAX_LETRAS}

    @api.model
    def _pedir_al_worker(self, audio, mime, duracion_ms):
        """La llamada al Worker la pone ``dcasa_conversaciones`` (``models/brian_voz.py``). Sin él: no disponible."""
        return {'ok': False, 'causa': 'no_disponible'}
