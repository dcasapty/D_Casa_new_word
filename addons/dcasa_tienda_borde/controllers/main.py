"""Ruta de apoyo a la caché de páginas del borde."""
import json

from odoo import http
from odoo.http import request


class DcasaTiendaBorde(http.Controller):

    @http.route('/dcasa/borde/csrf', type='http', auth='public', methods=['GET'], sitemap=False)
    def csrf(self, **kwargs):
        """Token CSRF de la sesión de quien pregunta.

        Una página servida desde la caché del borde es la misma para todo anónimo: su token CSRF
        es de otra sesión. ``static/src/js/borde_csrf.js`` pide este antes de enviar un formulario.
        La sesión se guarda (``touch``) para que la cookie que recibe el navegador sea la misma con
        la que se firmó el token. Nunca se guarda en caché (el borde no la tiene en su lista).
        """
        request.session.touch()
        return request.make_response(
            json.dumps({'csrf_token': request.csrf_token()}),
            headers=[
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Cache-Control', 'no-store'),
                ('X-Robots-Tag', 'noindex'),
            ],
        )
