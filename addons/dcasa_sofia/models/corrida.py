"""Cada vez que Sofía revisó el CRM (con el botón o cada mañana): cuándo, quién la pidió y qué encontró."""
from odoo import fields, models

ORIGENES = [('boton', 'Con el botón'), ('manana', 'Cada mañana')]


class SofiaCorrida(models.Model):
    _name = 'dcasa.sofia.corrida'
    _description = 'Revisión del CRM hecha por Sofía'
    _order = 'id desc'
    _rec_name = 'inicio'

    origen = fields.Selection(ORIGENES, 'Cómo empezó', required=True, readonly=True)
    usuario_id = fields.Many2one('res.users', 'La pidió', readonly=True, ondelete='set null')
    dia = fields.Date('Día (hora de Panamá)', required=True, readonly=True, index=True)
    inicio = fields.Datetime('Empezó', required=True, readonly=True, default=fields.Datetime.now)
    fin = fields.Datetime('Terminó', readonly=True)
    total = fields.Integer('Propuestas pendientes', readonly=True)
    nuevas = fields.Integer('Nuevas', readonly=True)
    vencidas = fields.Integer('Ya no hacían falta', readonly=True)
    resumen = fields.Json('Por tipo', readonly=True)
    omitidas = fields.Json('Sin mostrar (pasaron el tope)', readonly=True)
    avisos_telegram = fields.Integer('Avisos por Telegram', readonly=True)
