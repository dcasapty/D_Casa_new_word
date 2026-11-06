"""Odoo → Worker ``juan`` para las pantallas del panel: sugerir, salud, costos de IA y el puente de WhatsApp.

Rutas del Worker (``juan/src/odoo-panel*.ts``), todas con ``Authorization: Bearer <JUAN_WORKER_TOKEN>``:

* ``GET  /odoo/salud``      — estado de cada canal, claves que faltan, gasto del mes (ya existía).
* ``POST /odoo/sugerir``    — un borrador de respuesta para la vendedora (no envía nada).
* ``POST /odoo/resumir``    — el resumen de una conversación para la vendedora (no envía ni escribe nada).
* ``POST /odoo/embeber``    — la «huella de significado» de unos textos (búsqueda en el conocimiento por significado).
* ``GET  /odoo/costos``     — gasto de IA del mes, por modelo.
* ``GET  /odoo/qr``         — el código QR para vincular WhatsApp (NUNCA se escribe en un registro).
* ``POST /odoo/reiniciar``  — reinicia el puente de WhatsApp.
* ``POST /odoo/desvincular``— desvincula el número de WhatsApp (hay que escanear otro QR).
* ``POST /odoo/olvidar``    — el Worker borra su copia de trabajo de UNA conversación (cuando Odoo la elimina).

Igual que ``cliente_worker.py``: nada lanza excepciones por culpa de la red. ``_pedir`` devuelve SIEMPRE el cuerpo que
contestó el Worker (aunque diga ``ok: false``, como hace ``/odoo/salud`` cuando hay algo por arreglar): justo en ese
caso es cuando la pantalla de Conexiones lo necesita. El token no se escribe en ningún registro y el cuerpo tampoco
(el QR viaja en él).
"""
import logging
import time

import requests

from odoo import api, models

from .cliente_worker import MAX_RESPUESTA, TIMEOUT  # noqa: F401 — la misma política de red

_logger = logging.getLogger(__name__)

TIMEOUT_RAPIDO = (2, 4)             # una búsqueda en vivo: o contesta enseguida o se sigue sin ella
MAX_RESPUESTA_GRANDE = 256 * 1024    # el QR (una imagen en base64) cabe de sobra
# «Sugerir»: el Worker contesta SIEMPRE antes de 42 s (juan/src/odoo-panel-sugerir.ts, PLAZO_TOTAL_MS), con el borrador
# o con un error claro. Odoo espera más que eso para no rendirse antes que él (con 25 s se rendía mientras la IA seguía
# pensando: «a veces sí, a veces no», 2026-11-06). Una prueba del Worker lee esta línea y exige que encajen.
TIMEOUT_SUGERIR = (3.05, 55)
# Si ni siquiera se pudo hablar con el Worker (la red se cortó), se reintenta una vez: un borrador no escribe nada.
PAUSA_ANTES_DE_REINTENTAR = 1.0
REINTENTAR_SI_FALLO_ANTES_DE = 5.0
# Lo que el Worker dice que pasó (juan/src/odoo-panel-sugerir.ts, CausaDeFallo).
CAUSAS_DEL_WORKER = {'tardo', 'no_disponible', 'vacio', 'revision', 'sin_clave'}


class JuanClientePanel(models.AbstractModel):
    _inherit = 'dcasa.juan.cliente'

    @api.model
    def _pedir(self, metodo, ruta, datos=None, timeout=TIMEOUT):
        """``{conectado, estado_http, cuerpo, error, sin_configurar, causa}``; ``cuerpo`` es siempre un diccionario.

        ``causa`` (solo si no hubo respuesta): ``tardo`` si el Worker no contestó dentro del plazo, ``sin_conexion``
        si ni siquiera se pudo hablar con él."""
        ajustes = self.env['dcasa.juan.ajustes']
        url = ajustes.url_worker()
        token = ajustes.token_worker()
        vacio = {'conectado': False, 'estado_http': None, 'cuerpo': {}, 'error': None, 'sin_configurar': False,
                 'causa': None}
        if not url or not token:
            return {**vacio, 'sin_configurar': True,
                    'error': 'Falta conectar el bot: no hay dirección o clave del Worker de Juan.'}
        if not self._url_valida(url):
            return {**vacio, 'sin_configurar': True,
                    'error': 'La dirección del Worker de Juan no es válida (debe ser https://).'}
        try:
            respuesta = requests.request(
                metodo, f'{url}{ruta}', json=datos if metodo != 'GET' else None, timeout=timeout,
                headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'}, allow_redirects=False)
        except requests.RequestException as error:
            # Solo el tipo de error: el mensaje de requests puede traer la URL.
            _logger.warning('Juan: el Worker no respondió a %s %s (%s).', metodo, ruta, type(error).__name__)
            tardo = isinstance(error, requests.ReadTimeout)
            return {**vacio, 'causa': 'tardo' if tardo else 'sin_conexion',
                    'error': 'El Worker de Juan tardó demasiado.' if tardo else 'El Worker de Juan no responde.'}
        try:
            cuerpo = respuesta.json() if respuesta.content and len(respuesta.content) <= MAX_RESPUESTA_GRANDE else {}
        except ValueError:
            cuerpo = {}
        cuerpo = cuerpo if isinstance(cuerpo, dict) else {}
        if respuesta.status_code >= 400:
            _logger.warning('Juan: el Worker respondió %s a %s %s.', respuesta.status_code, metodo, ruta)
        error = None
        if respuesta.status_code >= 400:
            error = str(cuerpo.get('error') or f'El Worker respondió {respuesta.status_code}.')[:300]
        return {'conectado': True, 'estado_http': respuesta.status_code, 'cuerpo': cuerpo, 'error': error,
                'sin_configurar': False, 'causa': None}

    @api.private
    @api.model
    def sugerir(self, conversacion_id, canal, id_externo, mensajes, nombre=None, interes=None, etiquetas=None):
        """Un borrador de respuesta: ``{ok, texto, avisos, modelo}`` o ``{ok: False, causa, error, ...}``.

        ``causa``: ``sin_configurar`` · ``sin_conexion`` · ``tardo`` · lo que dijo el Worker (``CAUSAS_DEL_WORKER``) ·
        ``error``. ``estado_http`` y ``ms`` son para el registro."""
        datos = {'conversacion_id': conversacion_id, 'canal': canal, 'id_externo': id_externo, 'mensajes': mensajes,
                 'nombre': nombre or '', 'interes': interes or '', 'etiquetas': etiquetas or []}
        inicio = time.monotonic()
        respuesta = self._pedir('POST', '/odoo/sugerir', datos, timeout=TIMEOUT_SUGERIR)
        if respuesta['causa'] == 'sin_conexion' and time.monotonic() - inicio < REINTENTAR_SI_FALLO_ANTES_DE:
            time.sleep(PAUSA_ANTES_DE_REINTENTAR)
            respuesta = self._pedir('POST', '/odoo/sugerir', datos, timeout=TIMEOUT_SUGERIR)
        ms = int((time.monotonic() - inicio) * 1000)
        cuerpo = respuesta['cuerpo']
        if respuesta['sin_configurar']:
            causa = 'sin_configurar'
        elif not respuesta['conectado']:
            causa = respuesta['causa'] or 'sin_conexion'
        elif respuesta['error'] or cuerpo.get('ok') is False:
            causa = cuerpo.get('causa') if cuerpo.get('causa') in CAUSAS_DEL_WORKER else 'error'
        else:
            return {**cuerpo, 'ok': True, 'ms': ms, 'estado_http': respuesta['estado_http']}
        return {'ok': False, 'causa': causa, 'ms': ms, 'estado_http': respuesta['estado_http'],
                'error': respuesta['error'] or str(cuerpo.get('error') or '')[:300]
                or 'El Worker no pudo redactar el borrador.',
                'respaldo_sin_clave': str(cuerpo.get('respaldo_sin_clave') or '')[:40],
                'sin_configurar': respuesta['sin_configurar']}

    @api.private
    @api.model
    def resumir(self, conversacion_id, canal, mensajes, nombre=None, etiquetas=None):
        """El resumen de una conversación: ``{ok, texto, avisos}`` o ``{ok: False, error}``."""
        respuesta = self._pedir('POST', '/odoo/resumir', {
            'conversacion_id': conversacion_id, 'canal': canal, 'mensajes': mensajes,
            'nombre': nombre or '', 'etiquetas': etiquetas or []})
        if respuesta['error'] or respuesta['cuerpo'].get('ok') is False:
            return {'ok': False, 'error': respuesta['error'] or str(respuesta['cuerpo'].get('error') or '')[:300]
                    or 'El Worker no pudo resumir.', 'sin_configurar': respuesta['sin_configurar']}
        return {**respuesta['cuerpo'], 'ok': True}

    @api.private
    @api.model
    def informe_de_salud(self):
        """``GET /odoo/salud`` completo (aunque el Worker diga ``ok: false``). Ver ``_pedir``."""
        return self._pedir('GET', '/odoo/salud')

    @api.private
    @api.model
    def embeber(self, textos, rapido=False):
        """Un vector por texto: ``{ok, vectores, dimensiones}`` o ``{ok: False, error}``. Con ``rapido`` (una búsqueda
        en vivo, con un cliente esperando) se rinde a los 4 segundos en vez de insistir."""
        respuesta = self._pedir('POST', '/odoo/embeber', {'textos': list(textos)},
                                timeout=TIMEOUT_RAPIDO if rapido else TIMEOUT)
        if respuesta['error'] or respuesta['cuerpo'].get('ok') is False:
            return {'ok': False, 'error': respuesta['error'] or str(respuesta['cuerpo'].get('error') or '')[:300]
                    or 'El Worker no pudo calcular el significado.', 'sin_configurar': respuesta['sin_configurar']}
        return {**respuesta['cuerpo'], 'ok': True}

    @api.private
    @api.model
    def costos(self):
        return self._pedir('GET', '/odoo/costos')

    @api.private
    @api.model
    def qr(self):
        return self._pedir('GET', '/odoo/qr')

    @api.private
    @api.model
    def reiniciar_puente(self):
        return self._pedir('POST', '/odoo/reiniciar', {})

    @api.private
    @api.model
    def desvincular_puente(self):
        return self._pedir('POST', '/odoo/desvincular', {})

    @api.private
    @api.model
    def olvidar_conversacion(self, canal, id_externo):
        """El Worker borra lo que recuerda de esa conversación (mensajes, archivos, memoria). Ver ``_pedir``."""
        return self._pedir('POST', '/odoo/olvidar', {'canal': canal, 'id_externo': id_externo})
