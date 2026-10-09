"""Odoo → Worker ``juan``: enviar un mensaje, tomar o devolver una conversación, pedir un seguimiento.

Rutas del Worker (docs/JUAN.md, «Odoo → Worker juan»), con ``Authorization: Bearer <JUAN_WORKER_TOKEN>``:

* ``POST /odoo/enviar``      — una vendedora escribe desde Odoo y sale por el canal.
* ``POST /odoo/estado``      — tomar (``humano``) o devolver (``bot``) la conversación.
* ``POST /odoo/seguimiento`` — pedir el seguimiento n.º 1 o 2.
* ``GET  /odoo/salud``       — estado del Worker.

Nada de aquí lanza excepciones por culpa de la red: cada método devuelve ``{'ok': bool, ...}`` con
``error`` en español cuando algo falla, para que quien llama deje el trabajo «por enviar» y lo
reintente (los mensajes nunca se pierden). El token no se escribe en ningún registro.
"""
import logging
from urllib.parse import urlsplit

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

TIMEOUT = (3.05, 25)
HOSTS_LOCALES = {'localhost', '127.0.0.1', '::1'}
MAX_RESPUESTA = 64 * 1024


class JuanCliente(models.AbstractModel):
    _name = 'dcasa.juan.cliente'
    _description = 'Cliente HTTP hacia el Worker de Juan'

    @api.model
    def _url_valida(self, url):
        partes = urlsplit(url or '')
        if partes.scheme == 'https' and partes.hostname:
            return True
        return partes.scheme == 'http' and (partes.hostname or '') in HOSTS_LOCALES

    @api.private
    @api.model
    def configurado(self):
        ajustes = self.env['dcasa.juan.ajustes']
        url = ajustes.url_worker()
        return bool(url and self._url_valida(url) and ajustes.token_worker())

    @api.model
    def _llamar(self, metodo, ruta, datos=None):
        ajustes = self.env['dcasa.juan.ajustes']
        url = ajustes.url_worker()
        token = ajustes.token_worker()
        if not url or not token:
            return {'ok': False, 'error': 'Falta configurar la dirección o el token del Worker de Juan.',
                    'sin_configurar': True}
        if not self._url_valida(url):
            return {'ok': False, 'error': 'La dirección del Worker de Juan no es válida (debe ser https://).',
                    'sin_configurar': True}
        try:
            respuesta = requests.request(
                metodo, f'{url}{ruta}', json=datos if metodo != 'GET' else None, timeout=TIMEOUT,
                headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
                allow_redirects=False)
        except requests.RequestException as error:
            # Solo el tipo de error: el mensaje de requests puede traer la URL.
            _logger.warning('Juan: el Worker no respondió a %s %s (%s).', metodo, ruta, type(error).__name__)
            return {'ok': False, 'error': 'El Worker de Juan no responde.'}
        try:
            cuerpo = respuesta.json() if respuesta.content and len(respuesta.content) <= MAX_RESPUESTA else {}
        except ValueError:
            cuerpo = {}
        if not isinstance(cuerpo, dict):
            cuerpo = {}
        if respuesta.status_code >= 400 or cuerpo.get('ok') is False:
            _logger.warning('Juan: el Worker respondió %s a %s %s.', respuesta.status_code, metodo, ruta)
            return {'ok': False, 'estado_http': respuesta.status_code, 'cuerpo': cuerpo,
                    'error': str(cuerpo.get('error') or f'El Worker respondió {respuesta.status_code}.')[:300]}
        return {**cuerpo, 'ok': True}

    # ------------------------------------------------------------------
    # Rutas
    # ------------------------------------------------------------------

    @api.private
    @api.model
    def enviar(self, canal, id_externo, texto=None, adjuntos=None):
        datos = {'canal': canal, 'id_externo': id_externo, 'autor': 'vendedora'}
        if texto:
            datos['texto'] = texto
        if adjuntos:
            datos['adjuntos'] = adjuntos
        return self._llamar('POST', '/odoo/enviar', datos)

    @api.private
    @api.model
    def cambiar_estado(self, canal, id_externo, estado, pausada_hasta=None, nota=None):
        datos = {'canal': canal, 'id_externo': id_externo, 'estado': estado}
        if pausada_hasta:
            datos['pausada_hasta'] = pausada_hasta
        if nota:
            # Extensión del contrato: lo que la vendedora le dejó dicho al asistente al devolverle la conversación.
            datos['nota_para_el_bot'] = nota
        return self._llamar('POST', '/odoo/estado', datos)

    @api.private
    @api.model
    def pedir_seguimiento(self, conversacion_id, canal, id_externo, numero, interes=None, ultimo_mensaje_ts=None):
        return self._llamar('POST', '/odoo/seguimiento', {
            'conversacion_id': conversacion_id, 'canal': canal, 'id_externo': id_externo, 'numero': numero,
            'contexto': {'interes': interes or '', 'ultimo_mensaje_ts': ultimo_mensaje_ts},
        })

    @api.private
    @api.model
    def salud(self):
        """Salud del Worker. Un Worker con problemas (faltan secretos, un canal sin conectar) contesta 200 con
        ``ok: false``: respondió, así que se devuelve lo que dijo (``mensaje``, ``canales``…) con ``con_problemas``."""
        resultado = self._llamar('GET', '/odoo/salud')
        if resultado.get('estado_http') == 200 and resultado.get('cuerpo'):
            return {**resultado['cuerpo'], 'ok': True, 'con_problemas': True}
        return resultado
