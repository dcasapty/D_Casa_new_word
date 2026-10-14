"""Código público (DC-K7M4PX) para los productos que ya existen.

Desde esta versión cada producto nuevo nace con su código (addons/dcasa_base/models/codigo_publico.py). Aquí se le da
uno a los que ya estaban (más de 600 en producción, archivados y combos incluidos). Es seguro de repetir: no toca
los códigos ya dados, trabaja por lotes, vuelve a sortear si dos códigos chocan y no cambia la fecha de modificación
de los productos (las fotos del sitio no se vuelven a pedir).

También se descarta el mapa del sitio guardado (``/sitemap-*.xml``): las direcciones de las fichas ya no llevan la
referencia del proveedor (addons/website_dcasa/models/producto.py) y Google debe ver las nuevas. Las viejas siguen
funcionando: redirigen (301) a la nueva.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rellenados = env['product.template']._dcasa_rellenar_codigos_publicos()
    _logger.info('Código público: %s productos recibieron su código.', rellenados)
    env['ir.attachment'].sudo().search([('type', '=', 'binary'), ('url', '=like', '/sitemap-%.xml')]).unlink()
