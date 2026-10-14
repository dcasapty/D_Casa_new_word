"""Solo en STAGING: cuando ``GET /dcasa/salud`` responde 500, dice por qué.

El Worker del borde solo ve el código y los primeros caracteres de la respuesta. Un 500 de Odoo trae la
página genérica de Werkzeug («Internal Server Error»), sin la causa, y la traza completa queda en los logs
del contenedor, que desde GitHub Actions no se leen. Este módulo (que es ``server_wide``: se importa antes
de la primera petición) guarda en memoria los primeros errores distintos que Odoo registró y, si la ruta de salud
iba a contestar 500, la cambia por un 503 JSON con esos errores. Así ``/__edge/health`` (y el paso
«Esperar a que el sitio esté sano» del despliegue) muestran la causa real.

* Apagado en producción y en local: solo actúa con ``DCASA_ENTORNO=staging``.
* Solo toca ``/dcasa/salud``; cualquier otra ruta pasa tal cual.
* Guarda lo mínimo: clase y mensaje del error (cortados) y los últimos archivos:línea; no la traza entera.
"""

import collections
import json
import logging
import os
import traceback

ENTORNO_STAGING = 'staging'
RUTA_SALUD = '/dcasa/salud'
MAXIMO_ERRORES = 5
LARGO_MENSAJE = 160


class GuardarErrores(logging.Handler):
    """Se queda con los primeros errores DISTINTOS (ERROR o peor) que cualquier registro de Odoo escribe.

    La causa de raíz casi siempre es de las primeras; lo que viene después se repite en cada petición."""

    def __init__(self, ultimos):
        super().__init__(level=logging.ERROR)
        self.ultimos = ultimos

    def emit(self, record):
        try:
            if record.exc_info and record.exc_info[1] is not None:
                error = record.exc_info[1]
                sitios = traceback.extract_tb(record.exc_info[2])[-3:]
                donde = ' > '.join(f'{os.path.basename(s.filename)}:{s.lineno}' for s in sitios)
                texto = f'{type(error).__name__}: {str(error)[:LARGO_MENSAJE]} @ {donde}'
            else:
                texto = f'{record.name}: {record.getMessage()[:LARGO_MENSAJE]}'
            if texto not in self.ultimos and len(self.ultimos) < MAXIMO_ERRORES:
                self.ultimos.append(texto)
        except Exception:  # noqa: BLE001 - un registro roto nunca debe romper a Odoo
            pass


def envolver(aplicacion, ultimos):
    """La aplicación WSGI de Odoo, con la ruta de salud explicada cuando falla con 500."""

    def llamar(self, environ, start_response):
        if environ.get('PATH_INFO') != RUTA_SALUD:
            return aplicacion(self, environ, start_response)
        respuesta = {}

        def capturar(estado, cabeceras, exc_info=None):
            respuesta['estado'], respuesta['cabeceras'] = estado, cabeceras
            return lambda datos: None

        cuerpo = b''.join(aplicacion(self, environ, capturar))
        if respuesta.get('estado', '').startswith('500'):
            datos = json.dumps({'ok': False, 'diagnostico': list(ultimos)}, ensure_ascii=False,
                               separators=(',', ':')).encode()
            start_response('503 Service Unavailable', [
                ('Content-Type', 'application/json'), ('Content-Length', str(len(datos))),
                ('Cache-Control', 'no-store')])
            return [datos]
        start_response(respuesta['estado'], respuesta['cabeceras'])
        return [cuerpo]

    return llamar


def instalar(entorno=None):
    """Lo activa solo en staging. Devuelve ``True`` si quedó instalado."""
    if (entorno if entorno is not None else os.environ.get('DCASA_ENTORNO')) != ENTORNO_STAGING:
        return False
    from odoo import http
    if getattr(http.Application.__call__, 'dcasa_diagnostico', False):
        return False
    ultimos = collections.deque(maxlen=MAXIMO_ERRORES)
    logging.getLogger().addHandler(GuardarErrores(ultimos))
    llamar = envolver(http.Application.__call__, ultimos)
    llamar.dcasa_diagnostico = True
    http.Application.__call__ = llamar
    return True
