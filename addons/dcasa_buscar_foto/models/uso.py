"""Cada búsqueda por foto que llegó al Worker: para los topes y para saber cuántas hubo. Nunca la foto.

Una fila = la hora, el resultado (de una lista cerrada) y dos huellas HMAC (de la sesión y de la conexión) que sirven
para contar «cuántas en la última hora» y no se pueden revertir. Las huellas se borran al día siguiente (solo hacen
falta para el tope por hora) y la fila entera a los 90 días (``_cron_limpiar``). Solo el servidor escribe aquí.
"""
from datetime import timedelta

from odoo import api, fields, models

RESULTADOS = [
    ('resultados', 'Encontró productos'),
    ('nada', 'No encontró nada parecido'),
    ('documento', 'Parecía un documento (no se buscó)'),
    ('otra', 'No era un mueble'),
    ('no_ahora', 'No se pudo leer (Worker apagado, caído o lento, o tope de IA del mes)'),
]
HUELLAS_HORAS = 24
GUARDAR_DIAS = 90


class DcasaBuscarFotoUso(models.Model):
    _name = 'dcasa.buscar.foto.uso'
    _description = 'Busca con una foto: búsquedas hechas (sin la foto)'
    _order = 'fecha desc, id desc'
    _log_access = False

    fecha = fields.Datetime('Cuándo', required=True, default=fields.Datetime.now, index=True, readonly=True)
    resultado = fields.Selection(RESULTADOS, 'Resultado', required=True, readonly=True)
    huella_visitante = fields.Char('Huella de la sesión', index=True, readonly=True)
    huella_conexion = fields.Char('Huella de la conexión', index=True, readonly=True)

    @api.model
    def _cron_limpiar(self):
        """Borra las huellas de más de un día y las filas de más de 90 (no queda nada que una a una persona)."""
        ahora = fields.Datetime.now()
        viejas = self.sudo().search([('fecha', '<', ahora - timedelta(hours=HUELLAS_HORAS)), '|',
                                     ('huella_visitante', '!=', False), ('huella_conexion', '!=', False)])
        viejas.write({'huella_visitante': False, 'huella_conexion': False})
        self.sudo().search([('fecha', '<', ahora - timedelta(days=GUARDAR_DIAS))]).unlink()
        return True
