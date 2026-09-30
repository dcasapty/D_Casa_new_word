from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _dcasa_nota(self):
        """Términos de la cotización con los enlaces al sitio público, nunca a localhost."""
        self.ensure_one()
        return self.company_id._dcasa_sin_enlaces_locales(self.note)
