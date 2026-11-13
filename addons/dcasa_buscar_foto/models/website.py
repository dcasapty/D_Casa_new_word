from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_buscar_foto_activa(self):
        """¿Se dibuja la cámara de «Busca con una foto»? (Sitio web › Busca con una foto)."""
        return self.env['dcasa.buscar.foto']._dcasa_activa()
