"""La página de entrada del equipo: ``/master`` (docs/SEGURIDAD_ACCESO.md §8).

Es el login del personal, aparte del login público (``/web/login``, que queda para clientes y socios). Cloudflare
Access pide el PIN al correo ANTES de que esta página exista para quien la pide (el borde, ``edge/src/puerta.ts``,
verifica ese paso y le manda a Odoo la cabecera firmada). Aquí se entra con correo y clave, o con una llave de acceso,
y después Odoo pide SIEMPRE el código de la app (Google Authenticator; ``models/res_users.py``).

No se reescribe nada de la autenticación: se reutiliza ``web_login`` de Odoo (clave, llave de acceso, Turnstile, bloqueo
progresivo, segundo factor) y solo cambia la plantilla y la dirección a la que envía el formulario.
"""
from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.http import request

PLANTILLA = 'dcasa_seguridad.master_login'


class DcasaMaster(Home):

    @http.route(['/master', '/master/'], type='http', auth='public', website=True, sitemap=False, multilang=False,
                methods=['GET', 'POST'], readonly=False)
    def dcasa_master(self, redirect=None, **kw):
        if request.httprequest.method == 'GET' and request.session.uid:
            # Ya hay sesión: el personal va al panel; un cliente que llegó por error, a su cuenta.
            interno = request.env['res.users'].sudo().browse(request.session.uid)._is_internal()
            return request.redirect('/odoo' if interno else '/my')
        respuesta = self.web_login(redirect=redirect, **kw)
        if getattr(respuesta, 'qcontext', None) is not None:      # el formulario (no una redirección)
            respuesta.template = PLANTILLA
            respuesta.headers['Cache-Control'] = 'no-store'
            respuesta.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return respuesta
