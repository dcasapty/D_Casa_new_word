"""Las estrellas con que el visitante califica a Brian de la tienda: SOLO el número y la fecha (contrato §4).

Sin texto, sin sesión, sin red y sin conversación: no se puede saber de quién es. La escribe únicamente la ruta
``POST /dcasa/brian/v1/calificar`` (con ``sudo``, una vez por ``sid``); la leen Gerencia y los administradores (el
promedio y la cantidad del mes en Sitio web › Brian de la tienda). Nadie la crea, cambia ni borra por la interfaz
(el acceso es solo de lectura).
"""
from odoo import api, fields, models


class DcasaBrianTiendaCalificacion(models.Model):
    _name = 'dcasa.brian.tienda.calificacion'
    _description = 'Andrés (chat de la tienda): calificaciones (estrellas y fecha)'
    _order = 'fecha desc, id desc'
    _log_access = False
    _rec_name = 'fecha'

    fecha = fields.Datetime('Fecha', required=True, readonly=True, index=True, default=fields.Datetime.now)
    estrellas = fields.Integer('Estrellas', required=True, readonly=True)

    _estrellas_validas = models.Constraint('CHECK(estrellas BETWEEN 1 AND 5)', 'Las estrellas van de 1 a 5.')

    @api.model
    def _resumen(self, desde):
        """``{cantidad, promedio}`` desde ``desde`` (``promedio`` ``None`` si no hay ninguna)."""
        self.env.cr.execute('SELECT count(*), avg(estrellas) FROM dcasa_brian_tienda_calificacion WHERE fecha >= %s',
                            [desde])
        cantidad, promedio = self.env.cr.fetchone()
        return {'cantidad': cantidad or 0, 'promedio': round(float(promedio), 1) if promedio is not None else None}
