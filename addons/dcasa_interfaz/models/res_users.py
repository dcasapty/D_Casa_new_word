from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Usuarios nuevos sin la conversación de bienvenida de OdooBot.
    odoobot_state = fields.Selection(default='disabled')

    def _compute_tour_enabled(self):
        # Sin el recorrido guiado de Odoo (la «gota» con «¿Está listo para impulsar sus
        # ventas?»): D'CASA tiene su propio Inicio.
        self.tour_enabled = False
