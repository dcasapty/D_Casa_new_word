"""Cada búsqueda por foto que pasó los topes: para los topes y para saber cuántas hubo. Nunca la foto.

Una fila = la hora, el resultado (de una lista cerrada) y dos huellas (de la sesión y de la red de la conexión, /24 en
IPv4 y /64 en IPv6) hechas con la sal al azar del día (``dcasa.buscar.foto.sal``). Sirven para contar «cuántas en la
última hora»; son huellas que no dicen quién eres y se borran al día siguiente, igual que la sal. La fila entera se
borra a los 90 días (``_cron_limpiar``). Solo el servidor escribe aquí.
"""
from datetime import timedelta

from odoo import api, fields, models

RESULTADOS = [
    ('resultados', 'Encontró productos'),
    ('nada', 'No encontró nada parecido'),
    ('documento', 'Parecía un documento (no se buscó)'),
    ('otra', 'No era un mueble'),
    ('no_ahora', 'No se pudo leer (Worker apagado, caído o lento, o sin cupo de IA)'),
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
    huella_conexion = fields.Char('Huella de la red de la conexión', index=True, readonly=True)

    @api.model
    def _cron_limpiar(self):
        """Borra las huellas de más de un día, las sales de antes de ayer y las filas de más de 90 días."""
        ahora = fields.Datetime.now()
        viejas = self.sudo().search([('fecha', '<', ahora - timedelta(hours=HUELLAS_HORAS)), '|',
                                     ('huella_visitante', '!=', False), ('huella_conexion', '!=', False)])
        viejas.write({'huella_visitante': False, 'huella_conexion': False})
        self.sudo().search([('fecha', '<', ahora - timedelta(days=GUARDAR_DIAS))]).unlink()
        hoy = self.env['dcasa.buscar.foto']._dcasa_ahora_local(ahora).date()
        self.env['dcasa.buscar.foto.sal'].sudo().search([('fecha', '<', hoy - timedelta(days=1))]).unlink()
        return True


class DcasaBuscarFotoSal(models.Model):
    """La sal al azar de cada día (Panamá) para las huellas de los topes. Vive dos días: hoy y ayer."""
    _name = 'dcasa.buscar.foto.sal'
    _description = 'Busca con una foto: sal del día para las huellas'
    _order = 'fecha desc'
    _rec_name = 'fecha'
    _log_access = False

    fecha = fields.Date('Día (Panamá)', required=True, readonly=True)
    valor = fields.Char('Sal', required=True, readonly=True)

    _fecha_unica = models.Constraint('UNIQUE(fecha)', 'Ya hay una sal para ese día.')
