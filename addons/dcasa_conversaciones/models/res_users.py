"""Lo que el equipo de ventas necesita saber de cada persona para repartir las conversaciones."""
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    dcasa_disponible = fields.Boolean(
        'Recibe conversaciones nuevas', default=True, copy=False,
        help='Con el reparto activado (Ajustes de Juan), las conversaciones que el asistente pasa a una persona '
             'se asignan solo a las vendedoras disponibles (Gerencia y administradoras no reciben). Cada vendedora lo '
             'cambia desde la pantalla de Conversaciones (al irse a almorzar, al terminar el día…) y se reinicia solo '
             'cada mañana, antes de abrir la tienda.')
    dcasa_no_disponible_desde = fields.Datetime(
        'No disponible desde', copy=False, readonly=True,
        help='Cuándo se marcó «No disponible». Cada mañana, antes de abrir la tienda, quien lleva la pausa marcada '
             'desde antes de esa hora vuelve a «Disponible» (el reparto no se queda sin ella por un olvido).')
    dcasa_turno = fields.Integer(
        'Turno', copy=False, readonly=True,
        help='Número de la última conversación que le tocó (0 = nunca). Con empate en todo lo demás, el turno es de '
             'quien tiene el número más bajo, o sea, de quien lleva más tiempo sin recibir una.')
    dcasa_fuera_del_reparto = fields.Boolean(
        'No recibe conversaciones del asistente', default=False, copy=False,
        help='Gerencia lo marca para vacaciones o ausencias: el asistente no le pasa conversaciones, pero conserva '
             'todos sus permisos y puede tomar las que quiera. Se cambia desde la pantalla «Reparto». No se reinicia '
             'solo cada mañana: sigue hasta el día de regreso o hasta que Gerencia la vuelva a meter.')
    dcasa_fuera_hasta = fields.Date(
        'Vuelve a recibir el', copy=False,
        help='El día en que vuelve al reparto (ya cuenta ese día). Vacío: no recibe hasta que Gerencia lo cambie.')

    def _dcasa_en_el_reparto(self, hoy):
        """¿El asistente puede pasarle conversaciones? Sí, salvo que Gerencia la haya sacado del reparto y todavía no
        haya llegado el día en que vuelve. ``hoy``: la fecha de hoy en Panamá."""
        self.ensure_one()
        if not self.dcasa_fuera_del_reparto:
            return True
        return bool(self.dcasa_fuera_hasta and hoy >= self.dcasa_fuera_hasta)
