"""El botón «Organizar con Sofía» arriba del tablero y de la lista del CRM."""
from odoo import models


class CrmLeadSofia(models.Model):
    _inherit = 'crm.lead'

    def action_dcasa_sofia(self):
        """Abre la pantalla de Sofía y le pide revisar el CRM al entrar. Solo devuelve una acción."""
        accion = self.env['ir.actions.actions']._for_xml_id('dcasa_sofia.accion_sofia')
        accion['params'] = {'analizar': True}
        return accion
