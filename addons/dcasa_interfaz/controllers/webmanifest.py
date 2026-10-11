"""La app instalable del panel (celular, «Agregar a la pantalla de inicio») también es de D'CASA, no de Odoo."""
from odoo.addons.web.controllers.webmanifest import WebManifest

AZUL = '#1340B1'
ICONOS = (
    ('192x192', '/dcasa_interfaz/static/src/img/favicon-192.png'),
    ('512x512', '/dcasa_interfaz/static/src/img/favicon.png'),
)


class WebManifestDcasa(WebManifest):

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        manifest['background_color'] = AZUL
        manifest['theme_color'] = AZUL
        manifest['icons'] = [{'src': src, 'sizes': tamano, 'type': 'image/png'} for tamano, src in ICONOS]
        return manifest
