"""SW-03: fuera las promesas sin respaldo (financiamiento, tarjeta) de lo que quedó copiado.

Las plantillas ya traen el texto nuevo; esto limpia las copias por sitio, los bloques guardados
desde el editor y el mensaje del pago al recibir. El SEO de la portada lo corrige
data/seo_data.xml en cada actualización.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['website']._dcasa_retirar_promesas()
