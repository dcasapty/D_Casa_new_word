"""``/dcasa/doc/<TIPO>/<REFERENCIA>``: lo que abre el código QR de uso interno de un documento.

* Sin sesión: manda a la pantalla de entrada y, al entrar, vuelve aquí (lo hace Odoo con ``auth='user'``).
* Con sesión y permiso de leerlo: redirige al formulario del documento.
* Con sesión pero sin permiso: aviso claro y 403, sin un solo dato del documento.
* Si no existe: aviso claro y 404.

Las referencias llevan barras (``INV/2026/00001``, ``WH/OUT/00005``): la ruta las acepta todas.
"""
from odoo import http
from odoo.http import request

from ..models.documento_abrir import OK, SIN_PERMISO


class DocumentoController(http.Controller):

    @http.route('/dcasa/doc/<string:tipo>/<path:referencia>', type='http', auth='user', methods=['GET'],
                readonly=True)
    def abrir(self, tipo, referencia, **_kw):
        documentos = request.env['dcasa.documento']
        referencia = referencia.strip('/ ')    # «INV/2026/00001/» (una barra de más) es el mismo documento
        estado, registro = documentos._dcasa_buscar_documento(tipo, referencia)
        if estado == OK:
            respuesta = request.redirect(documentos._dcasa_ruta_odoo(registro), code=302)
            respuesta.headers['Cache-Control'] = 'no-store'
            return respuesta
        sin_permiso = estado == SIN_PERMISO
        titulo = request.env._('No tienes permiso') if sin_permiso else request.env._('No encontramos el documento')
        return request.render('dcasa_invoice.documento_aviso', {
            'titulo': titulo,
            'mensaje': documentos._dcasa_mensaje_documento(estado, (tipo or '').upper()),
        }, headers={'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex'}, status=403 if sin_permiso else 404)

