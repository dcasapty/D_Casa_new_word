"""El Excel de la pantalla «Rotación», hecho en el servidor (``dcasa.rotacion._excel``).

Solo Gerencia, administradores y el rol Marketing (``_excel`` exige el permiso antes de leer: a cualquier otra
persona, un error); sin dinero para el rol Marketing. Así sale el Excel sin abrirle a todo el mundo el «Exportar»
general de Odoo.
"""
from odoo import http
from odoo.http import content_disposition, request

TIPO_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class RotacionExcel(http.Controller):

    @http.route('/dcasa/rotacion/excel', type='http', auth='user', methods=['GET'])
    def rotacion_excel(self, vista=None, categoria=None, texto=None, orden=None, rebaja=None, **_otros):
        nombre, contenido = request.env['dcasa.rotacion']._excel(vista or None, categoria or None, texto or '',
                                                                 orden or None, rebaja or None)
        return request.make_response(contenido, headers=[
            ('Content-Type', TIPO_XLSX),
            ('Content-Disposition', content_disposition(nombre)),
            ('Cache-Control', 'no-store'),
        ])
