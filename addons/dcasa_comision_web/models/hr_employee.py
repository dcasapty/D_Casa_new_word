from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Quién le cambia a una persona su usuario o su contacto de trabajo queda en el chatter de la ficha: de eso depende
    # que «quien cobra no aprueba» sepa quién es quién (los usuarios ligados el día que se guardó una versión además
    # quedan fijos en el reparto: ``dcasa.web.reparto.usuario_ids``).
    user_id = fields.Many2one(tracking=True)
    work_contact_id = fields.Many2one(tracking=True)
