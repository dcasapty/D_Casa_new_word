"""``GET /dcasa/salud``: ¿la base responde? La consulta el Worker del borde.

* 200 ``{"ok": true}`` si ``SELECT 1`` responde; 503 ``{"ok": false}`` si no.
* En la imagen de producción además dice **qué versión responde** y **si la base está al día** con su
  código: ``{"ok": true, "version": "<12 primeros del commit>", "base_al_dia": true}``. El despliegue
  lo exige (``.github/scripts/esperar_salud.sh``): «sano» es la versión nueva con la base actualizada,
  no solo «Odoo contesta» (incidente del 2026-10-16, #97). El commit es público (el repositorio lo es);
  no dice nombre de base ni errores.
* ``auth='none'`` y ``save_session=False``: no lee usuario, no guarda sesión, no pone cookie.
* Como el módulo es ``server_wide``, la ruta existe también sin base (cuando la base no
  responde Odoo cae al modo sin base, y desde ahí contesta 503).
"""

import logging
import os

from odoo import http, sql_db
from odoo.http import request

from ..almacen import nombre_base

_logger = logging.getLogger(__name__)

# Lo escribe el arranque (docker/entrypoint.sh) con la huella del código de la imagen tras actualizar la base.
PARAM_CODIGO = 'dcasa.codigo_desplegado'


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
    """La huella del código con que se actualizó la base por última vez, o None si no se sabe."""
    try:
        fila = _consultar('SELECT value FROM ir_config_parameter WHERE key = %s', [PARAM_CODIGO])
    except Exception as error:  # noqa: BLE001 - sin dato: el despliegue esperará y fallará con su aviso
        _logger.warning('Salud: no pude leer la huella de la base: %s', type(error).__name__)
        return None
    return fila[0] if fila else None


def estado():
    """Lo que contesta la ruta: ``ok`` y, en la imagen de producción, la versión y si la base está al día."""
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
