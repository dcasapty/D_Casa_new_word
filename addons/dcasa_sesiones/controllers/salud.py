"""``GET /dcasa/salud``: ¿la base responde? La consulta el Worker del borde.

* 200 ``{"ok": true}`` si ``SELECT 1`` responde; 503 ``{"ok": false}`` si no.
* ``auth='none'`` y ``save_session=False``: no lee usuario, no guarda sesión, no pone cookie.
* No dice versión, base ni error: solo sí o no.
* Como el módulo es ``server_wide``, la ruta existe también sin base (cuando la base no
  responde Odoo cae al modo sin base, y desde ahí contesta 503).
"""

import logging

from odoo import http, sql_db
from odoo.http import request

from ..almacen import nombre_base

_logger = logging.getLogger(__name__)


def base_responde():
    """True si la base responde a ``SELECT 1``."""
    try:
        if request.env is not None:
            request.env.cr.execute('SELECT 1')
            return request.env.cr.fetchone() == (1,)
        nombre = request.db or nombre_base()
        if not nombre:
            return False
        with sql_db.db_connect(nombre).cursor() as cr:
            cr.execute('SELECT 1', log_exceptions=False)
            return cr.fetchone() == (1,)
    except Exception as error:  # noqa: BLE001 - cualquier fallo es «la base no responde»
        _logger.warning('Salud: la base no responde: %s', type(error).__name__)
        return False


class SaludDcasa(http.Controller):

    @http.route('/dcasa/salud', type='http', auth='none', methods=['GET'], save_session=False,
                readonly=True)
    def salud(self):
        ok = base_responde()
        return request.make_json_response(
            {'ok': ok},
            headers=[('Cache-Control', 'no-store')],
            status=200 if ok else 503,
        )
