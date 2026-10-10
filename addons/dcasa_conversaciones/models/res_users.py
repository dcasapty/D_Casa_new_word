"""Lo que el equipo de ventas necesita saber de cada persona para repartir las conversaciones."""
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    dcasa_disponible = fields.Boolean(
        'Recibe conversaciones nuevas', default=True, copy=False,
        help='Con el reparto «por turnos» (Ajustes de Juan), las conversaciones que el asistente pasa a una persona '
             'se asignan solo a quien está disponible. Cada persona lo cambia desde la pantalla de Conversaciones '
             '(al irse a almorzar, al terminar el día…).')
    dcasa_turno = fields.Integer(
        'Turno', copy=False, readonly=True,
        help='Número de la última conversación que le tocó por turno (0 = nunca). El turno es de quien tiene el '
             'número más bajo, o sea, de quien lleva más tiempo sin recibir una.')
