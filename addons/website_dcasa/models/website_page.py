from odoo import models


class WebsitePage(models.Model):
    _inherit = 'website.page'

    def _get_cache_key(self, request):
        """La portada muestra precios: la caché de página se separa por tarifa y posición fiscal,
        así nadie ve el precio que le tocó a otro visitante."""
        clave = super()._get_cache_key(request)
        if hasattr(request, 'pricelist'):
            clave += (request.pricelist.id, request.fiscal_position.id)
        return clave
