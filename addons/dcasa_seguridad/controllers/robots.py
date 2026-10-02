"""/robots.txt: agrega la política para rastreadores de IA (``dcasa_seguridad.robots_ia``).

Lo de Odoo (Allow, Sitemap y el texto que un administrador escriba en el sitio) queda igual;
el bloque de D'CASA va al final (plantilla ``dcasa_seguridad.robots``).
"""
from odoo import http
from odoo.addons.website.controllers.main import Website
from odoo.http import request

from ..models.parametros import politica_robots, texto_robots_ia


class DcasaRobots(Website):

    @http.route()
    def robots(self, **kwargs):
        respuesta = super().robots(**kwargs)
        if getattr(respuesta, 'qcontext', None) is not None:
            respuesta.qcontext['dcasa_robots_ia'] = texto_robots_ia(politica_robots(request.env))
        return respuesta
