from werkzeug.urls import url_parse

from odoo import models


class WebsiteMenu(models.Model):
    _inherit = 'website.menu'

    def _is_active(self):
        """Un menú a un ancla (p. ej. «Visítanos» → /#visitanos) no es la página actual.

        Odoo ignora el fragmento al comparar, así que lo marcaría activo en «/».
        """
        if not self.child_id and url_parse(self._clean_url()).fragment:
            return False
        return super()._is_active()
