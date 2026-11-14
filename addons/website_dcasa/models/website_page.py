from odoo import models


class WebsitePage(models.Model):
    _inherit = 'website.page'

    def _get_cache_key(self, request):
        """La portada muestra precios: la caché de página se separa por tarifa y posición fiscal,
        así nadie ve el precio que le tocó a otro visitante."""
        clave = super()._get_cache_key(request)
        if hasattr(request, 'pricelist'):
            clave += (request.pricelist.id, request.fiscal_position.id)
        # El horario del pie no vive en una vista (sale de los Ajustes de Juan, models/horario_tienda.py): si cambia,
        # la página que Odoo guarda para el visitante (hasta 1 h) tiene que ser otra, como al cambiar una vista.
        website = getattr(request, 'website', None)
        if website:
            clave += (tuple(fila['corto'] for fila in website._dcasa_horario_tienda()),)
        return clave
