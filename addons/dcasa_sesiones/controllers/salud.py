"""``GET /dcasa/salud``: ¿la base responde? La consulta el Worker del borde.

* 200 ``{"ok": true}`` si ``SELECT 1`` responde; 503 ``{"ok": false}`` si no.
* En la imagen de producción además dice **qué versión responde**, **si la base está al día** con su
  código y **cómo salió la prueba de humo** del arranque: ``{"ok": true, "version": "<12 primeros del
  commit>", "base_al_dia": true, "humo": "ok"}``. El despliegue lo exige
  (``.github/scripts/esperar_salud.sh``): «sano» es la versión nueva con la base actualizada y las
  pantallas principales abriendo, no solo «Odoo contesta» (incidente del 2026-10-16, #97). El commit es
  público (el repositorio lo es); no dice nombre de base ni el detalle de los errores (eso va al log).
* ``auth='none'`` y ``save_session=False``: no lee usuario, no guarda sesión, no pone cookie.
* Como el módulo es ``server_wide``, la ruta existe también sin base (cuando la base no
  responde Odoo cae al modo sin base, y desde ahí contesta 503).
"""

import json
import logging
import os

from odoo import http, sql_db
from odoo.http import request

from ..almacen import nombre_base

_logger = logging.getLogger(__name__)

# Lo escribe el arranque (docker/entrypoint.sh) con la huella del código de la imagen tras actualizar la base,
# siempre DESPUÉS de la versión (PARAM_VERSION).
PARAM_CODIGO = 'dcasa.codigo_desplegado'
PARAM_VERSION = 'dcasa.deployed_version'
# La prueba de humo del arranque (dcasa_base/models/humo.py): {"ok": …, "columnas_faltantes": […], "errores": […]}.
PARAM_HUMO = 'dcasa.humo'


def _consultar(consulta, parametros=()):
    """La primera fila de una consulta en la base de esta petición (o por conexión directa, sin registro)."""
    if request.env is not None:
        request.env.cr.execute(consulta, parametros)
        return request.env.cr.fetchone()
    nombre = request.db or nombre_base()
    if not nombre:
        return None
    with sql_db.db_connect(nombre).cursor() as cr:
        cr.execute(consulta, parametros, log_exceptions=False)
        return cr.fetchone()


def base_responde():
    """True si la base responde a ``SELECT 1``."""
    try:
        return _consultar('SELECT 1') == (1,)
    except Exception as error:  # noqa: BLE001 - cualquier fallo es «la base no responde»
        _logger.warning('Salud: la base no responde: %s', type(error).__name__)
        return False


def codigo_en_la_base():
    """La huella del código con que se actualizó la base por última vez, o None si no se sabe.

    Una imagen anterior a este control solo marca la versión (``dcasa.deployed_version``): si la versión se marcó
    DESPUÉS que la huella, la huella quedó vieja y no prueba nada (None)."""
    try:
        fila = _consultar("""
            SELECT c.value, c.write_date < v.write_date
              FROM ir_config_parameter c
              LEFT JOIN ir_config_parameter v ON v.key = %s
             WHERE c.key = %s
        """, [PARAM_VERSION, PARAM_CODIGO])
    except Exception as error:  # noqa: BLE001 - sin dato: el despliegue esperará y fallará con su aviso
        _logger.warning('Salud: no pude leer la huella de la base: %s', type(error).__name__)
        return None
    if not fila or fila[1]:
        return None
    return fila[0]


def humo_del_arranque():
    """«ok» o «fallo» según la prueba de humo del último arranque (``dcasa.humo``); None si no se corrió."""
    try:
        fila = _consultar('SELECT value FROM ir_config_parameter WHERE key = %s', [PARAM_HUMO])
        if not fila:
            return None
        return 'ok' if json.loads(fila[0]).get('ok') is True else 'fallo'
    except Exception as error:  # noqa: BLE001 - un dato ilegible no es «ok»
        _logger.warning('Salud: no pude leer la prueba de humo: %s', type(error).__name__)
        return 'fallo'


def estado():
    """Lo que contesta la ruta: ``ok`` y, en la imagen de producción, la versión, si la base está al día y la prueba
    de humo del arranque."""
    ok = base_responde()
    cuerpo = {'ok': ok}
    if not ok:
        return cuerpo
    commit = (os.environ.get('DCASA_COMMIT_IMAGEN') or '').strip()
    codigo = (os.environ.get('DCASA_CODIGO') or '').strip()
    if commit:
        cuerpo['version'] = commit[:12]
    if codigo:
        cuerpo['base_al_dia'] = codigo_en_la_base() == codigo
    humo = humo_del_arranque()
    if humo:
        cuerpo['humo'] = humo
    return cuerpo


class SaludDcasa(http.Controller):

    @http.route('/dcasa/salud', type='http', auth='none', methods=['GET'], save_session=False,
                readonly=True)
    def salud(self):
        cuerpo = estado()
        return request.make_json_response(
            cuerpo,
            headers=[('Cache-Control', 'no-store')],
            status=200 if cuerpo['ok'] else 503,
        )
