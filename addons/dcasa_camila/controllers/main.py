"""``/novedades/si``: el enlace «¿Te avisamos de lo nuevo? Sí, quiero» del pie de la factura y de la bienvenida.

* **GET** (el enlace del correo) solo muestra la página con la marca y el botón «Sí, quiero»: los filtros de correo
  de algunas empresas abren los enlaces solos para revisarlos, y eso no puede contar como un «sí».
* **POST** (el botón, con el token de la sesión contra CSRF) anota el permiso y muestra «¡Gracias!».
* El enlace va firmado con el secreto de la base (HMAC): sin la firma, vencido o si la ficha ya cambió de correo,
  no sirve. Con baja, no se vuelve a dar de alta (la baja es final).
* Nunca se guarda en el borde ni en el navegador (``no-store``) y no se indexa.
"""
from odoo import http
from odoo.http import request

TITULOS = {
    'confirmar': '¿Te avisamos de lo nuevo?',
    'gracias': '¡Listo, gracias!',
    'ya': 'Ya estás en la lista',
    'baja': 'Te diste de baja',
    'invalido': 'Este enlace ya no sirve',
}


class NovedadesDcasa(http.Controller):

    @http.route('/novedades/si', type='http', auth='public', website=True, methods=['GET', 'POST'], sitemap=False)
    def novedades_si(self, t=None, **_kwargs):
        Camila = request.env['dcasa.camila'].sudo()
        if request.httprequest.method == 'POST':
            estado = Camila._enlace_confirmar(t)
        else:
            estado = Camila._enlace_leer(t)[0]
        website = request.website
        respuesta = request.render('dcasa_camila.pagina_novedades', {
            'estado': estado,
            'titulo': TITULOS[estado],
            'token': t if estado == 'confirmar' else '',
            'whatsapp': website._dcasa_whatsapp_url("Hola D'CASA, quiero saber de lo nuevo."),
        })
        respuesta.headers['Cache-Control'] = 'no-store'
        respuesta.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return respuesta
