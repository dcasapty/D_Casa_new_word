"""El Excel de la pantalla «Movimiento», hecho en el servidor (``dcasa.movimiento_productos._excel``).

Solo Gerencia, administradores y el rol Marketing (``_excel`` exige el permiso antes de leer: a cualquier otra
persona, un error); sin dinero para el rol Marketing. Así sale el Excel sin abrirle a todo el mundo el «Exportar»
general de Odoo.
"""
from odoo import http
from odoo.http import content_disposition, request

TIPO_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class MovimientoExcel(http.Controller):

    @http.route('/dcasa/movimiento/excel', type='http', auth='user', methods=['GET'])
    def movimiento_excel(self, periodo=None, contra=None, desde=None, hasta=None, contra_desde=None,
                         contra_hasta=None, vista=None, categoria=None, texto=None, orden=None, **_otros):
        nombre, contenido = request.env['dcasa.movimiento_productos']._excel(
            periodo or None, contra or None, desde or None, hasta or None, contra_desde or None,
            contra_hasta or None, vista or None, categoria or None, texto or '', orden or None)
        return request.make_response(contenido, headers=[
            ('Content-Type', TIPO_XLSX),
            ('Content-Disposition', content_disposition(nombre)),
            ('Cache-Control', 'no-store'),
        ])
