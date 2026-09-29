{
    'name': "D'CASA Panamá — Sitio web",
    'summary': "Sitio web y tienda de D'CASA con su marca, editable desde el constructor de Odoo",
    'description': """
Sitio web de D'CASA sobre el constructor de sitios y el eCommerce de Odoo:

* Paleta y tipografías de la marca (azul #1340B1, amarillo #FED00F, Anton,
  Oswald, Inter) cargadas como paleta del sitio: se pueden ajustar desde el
  editor sin tocar código.
* Página de inicio con el contenido del sitio anterior (Next.js), pie de página
  con los datos reales y botón flotante de WhatsApp.
* Categorías de la tienda (Salas, Comedores, Recámaras, Colchones,
  Electrodomésticos, Decoración, Exteriores).
* Página pública «Refiere y gana» conectada al programa de referidos.

Todo el contenido de las páginas es editable con el constructor de Odoo
(Sitio web > Editar), sin programador.
""",
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_referral', 'website_sale'],
    'data': [
        'data/website_data.xml',
        'data/product_public_category_data.xml',
        'views/res_config_settings_views.xml',
        'views/layout_templates.xml',
        'views/homepage_templates.xml',
        'views/referral_page_templates.xml',
        'data/website_menu_data.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'website_dcasa/static/src/scss/primary_variables.scss',
        ],
        'web.assets_frontend': [
            'website_dcasa/static/src/scss/dcasa.scss',
        ],
    },
    'installable': True,
}
