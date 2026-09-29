"""Sitio v2 en bases que ya tenían el módulo.

Los ajustes de ``data/website_data.xml`` van en ``noupdate`` (para no pisar lo que se cambie
luego desde el editor) y por eso una actualización no los aplica. Se aplican aquí una sola vez.
"""
from odoo import SUPERUSER_ID, api

DISENO_TIENDA = (
    'o_wsale_products_opt_layout_catalog o_wsale_products_opt_design_thumbs '
    'o_wsale_products_opt_name_color_regular o_wsale_products_opt_rounded_2 '
    'o_wsale_products_opt_img_secondary_show o_wsale_products_opt_img_hover_zoom_in_light '
    'o_wsale_products_opt_has_cta o_wsale_products_opt_actions_inline '
    'o_wsale_products_opt_actions_subtle o_wsale_products_opt_cc1'
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    website = env.ref('website.default_website', raise_if_not_found=False)
    if website:
        website.write({'shop_ppr': 4, 'shop_ppg': 24, 'shop_opt_products_design_classes': DISENO_TIENDA})
    portada = env.ref('website.homepage_page', raise_if_not_found=False)
    if portada:
        portada.write({
            'website_meta_title': "Mueblería en La Chorrera | D'CASA Panamá",
            'website_meta_description': (
                'Salas, recámaras, colchones y comedores con precios claros en La Chorrera. '
                'Entrega a todo Panamá y financiamiento. Escríbenos por WhatsApp.'
            ),
        })
    texto_cabecera = env.ref('website.header_text_element', raise_if_not_found=False)
    if texto_cabecera:
        texto_cabecera.active = False
