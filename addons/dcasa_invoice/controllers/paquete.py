"""El PDF del «Imprimir documentos»: se arma en el momento y no se guarda en ningún lado."""
import logging

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


def _texto(mensaje, estado):
    """Un error en texto simple: el navegador lo muestra tal cual en un aviso."""
    return request.make_response(
        mensaje, headers=[('Content-Type', 'text/plain; charset=utf-8'), ('Cache-Control', 'no-store')],
        status=estado)


class PaqueteController(http.Controller):

    @http.route('/dcasa/paquete.pdf', type='http', auth='user', methods=['GET'])
    def paquete(self, facturas='', docs='', **_kw):
        """PDF unido de las facturas (``facturas=1,2``) y los documentos (``docs=cliente,copia,entrega``).

        Corre con los permisos de quien lo pide: quien no puede leer una factura (por ejemplo, la vendedora con la
        de un proveedor) recibe un 403, y solo salen facturas de clientes publicadas.
        """
        try:
            ids = [int(id_) for id_ in facturas.split(',') if id_.strip()]
        except ValueError:
            return _texto('Los números de factura no son válidos.', 400)
        if not ids:
            return _texto('No elegiste ninguna factura.', 400)
        claves = [clave for clave in docs.split(',') if clave]
        try:
            modelo = request.env['dcasa.impresion.paquete']
            contenido, nombre = modelo._armar_pdf(request.env['account.move'].browse(ids).exists(), claves)
        except (AccessError, MissingError):
            return _texto('No tienes permiso para imprimir estos documentos.', 403)
        except UserError as error:
            return _texto(str(error.args[0] if error.args else error), 400)
        return request.make_response(contenido, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(contenido)),
            # «inline»: se abre en el visor del navegador; el botón «Descargar» lo guarda con el nombre.
            ('Content-Disposition', http.content_disposition(nombre).replace('attachment', 'inline', 1)),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
        ])
