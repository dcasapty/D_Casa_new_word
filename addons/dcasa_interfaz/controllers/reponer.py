"""El Excel de Compras › Reponer, hecho en el servidor (``dcasa.reponer._excel``).

Solo Gerencia y los administradores: ``_excel`` lo exige antes de leer (a cualquier otra persona, 403). Así Gerencia
saca su Excel sin abrirle a todo el mundo el «Exportar» general de Odoo.
"""
from odoo import http
from odoo.http import content_disposition, request

TIPO_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class ReponerExcel(http.Controller):

    @http.route('/dcasa/reponer/excel', type='http', auth='user', methods=['GET'])
    def reponer_excel(self, meses=None, reserva=None, proveedor=None, **_otros):
        nombre, contenido = request.env['dcasa.reponer']._excel(meses, reserva, proveedor or False)
        return request.make_response(contenido, headers=[
            ('Content-Type', TIPO_XLSX),
            ('Content-Disposition', content_disposition(nombre)),
            ('Cache-Control', 'no-store'),
        ])
