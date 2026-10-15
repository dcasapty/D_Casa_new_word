"""Cuántas veces cada persona usó «Llévame ahí» en cada tarea de la Guía.

Es lo que alimenta «Lo que tú más usas». Una fila por persona y tarea; cada quien ve y escribe solo la suya (regla de
registro global). No guarda nada de clientes ni de documentos: solo quién, qué tarea de la Guía, cuántas veces y cuándo
fue la última. Se escribe desde ``dcasa.guia.registrar_uso``, que antes comprueba que la tarea existe y que la persona
puede abrirla.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .guia import buscar_tarea


class DcasaGuiaUso(models.Model):
    _name = 'dcasa.guia.uso'
    _description = 'Uso de «Llévame ahí» por persona'
    _order = 'veces desc, ultima_vez desc, id'

    user_id = fields.Many2one('res.users', string='Persona', required=True, ondelete='cascade', index=True,
                              default=lambda self: self.env.uid)
    tarea = fields.Char(string='Tarea de la Guía', required=True,
                        help='El id de la tarea en guia.json (por ejemplo «cierre-mes»).')
    veces = fields.Integer(string='Veces', default=1, required=True)
    ultima_vez = fields.Datetime(string='Última vez', default=fields.Datetime.now, required=True)

    _persona_tarea_unica = models.Constraint(
        'UNIQUE (user_id, tarea)', 'Cada persona tiene una sola fila de uso por tarea.')
    _veces_positivas = models.Constraint('CHECK (veces > 0)', 'Las veces deben ser al menos una.')

    @api.constrains('tarea')
    def _check_tarea_existe(self):
        for fila in self:
            if not buscar_tarea(fila.tarea):
                raise ValidationError(self.env._('La tarea «%s» no existe en la Guía.', fila.tarea))

    @api.model
    def _sumar(self, tarea):
        """+1 y la hora para quien llama (crea la fila la primera vez). Lo llama ``registrar_uso`` ya validado."""
        ahora = fields.Datetime.now()
        fila = self.search([('user_id', '=', self.env.uid), ('tarea', '=', tarea)], limit=1)
        if fila:
            fila.write({'veces': fila.veces + 1, 'ultima_vez': ahora})
        else:
            self.create({'user_id': self.env.uid, 'tarea': tarea, 'veces': 1, 'ultima_vez': ahora})
