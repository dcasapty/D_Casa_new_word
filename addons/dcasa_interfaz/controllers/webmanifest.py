"""La app instalable del panel (celular, «Agregar a la pantalla de inicio») también es de D'CASA, no de Odoo.

El ícono es estrictamente el logo (pedido de la dueña, 2026-10-22), hecho con ``scripts/iconos_de_la_marca.py``: solo
el logo (transparente) para «any» y sobre blanco, dentro de la zona segura, para «maskable» (Android lo recorta en
círculo o en gota). El fondo de la pantalla de arranque es blanco, como el ícono; la barra del navegador, azul.
"""
from odoo.addons.web.controllers.webmanifest import WebManifest

AZUL = '#1340B1'
BLANCO = '#FFFFFF'
CARPETA = '/dcasa_base/static/img/icono'
ICONOS = (
    ('192x192', f'{CARPETA}/logo-192.png', 'any'),
    ('512x512', f'{CARPETA}/logo-512.png', 'any'),
    ('192x192', f'{CARPETA}/logo-maskable-192.png', 'maskable'),
    ('512x512', f'{CARPETA}/logo-maskable-512.png', 'maskable'),
)
APPLE_TOUCH_ICON = f'{CARPETA}/apple-touch-icon.png'
FAVICON = f'{CARPETA}/logo-192.png'


class WebManifestDcasa(WebManifest):

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        manifest['background_color'] = BLANCO
        manifest['theme_color'] = AZUL
        manifest['icons'] = [{'src': src, 'sizes': tamano, 'type': 'image/png', 'purpose': uso}
                             for tamano, src, uso in ICONOS]
        return manifest

    def _icon_path(self):
        """El ícono de la página «sin conexión» del panel y de las apps sueltas sin ícono propio: el logo, no Odoo."""
        return FAVICON.lstrip('/')
