from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_whatsapp_number = fields.Char(related='website_id.dcasa_whatsapp_number', readonly=False)
