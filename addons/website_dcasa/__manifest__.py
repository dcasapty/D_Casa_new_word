{
    'name': "D'CASA Panamá — Sitio web",
    'summary': "Sitio web y tienda de D'CASA con su marca, editable desde el constructor de Odoo",
    'description': """
Sitio web de D'CASA sobre el constructor de sitios y el eCommerce de Odoo:

* Paleta y tipografías de la marca (azul #1340B1, amarillo #FED00F, Anton,
  Oswald, Inter) cargadas como paleta del sitio: se pueden ajustar desde el
  editor sin tocar código.
* Portada v2 (docs/REDISENO.md): hero con placa, compra por espacio, carriles de
  productos con precio y «Agregar» en un clic, socios, guía y preguntas frecuentes.
* Ficha de producto con WhatsApp del mueble, sellos de confianza y botón fijo en el
  celular; tienda a 4 columnas; datos estructurados y SEO local.
* Pie de página con los datos reales y botón flotante de WhatsApp, sin el crédito de Odoo.
* Cabecera de vidrio flotante, animaciones de entrada (secciones y titulares) y
  opiniones reales de Google en una cinta en movimiento (data/resenas.json).
* Categorías de la tienda (Salas, Recámaras, Colchones, Zapateras, Estantes y
  organización, Oficina, y otras que la tienda oculta mientras no tengan productos).
* Enlaces al programa Socios D'CASA (/socios): puntos, referidos y premios.

Todo el contenido de las páginas es editable con el constructor de Odoo
(Sitio web > Editar), sin programador.
""",
    'version': '19.0.1.7.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_socios', 'website_sale'],
    'data': [
        'data/website_data.xml',
        'data/product_public_category_data.xml',
        'views/res_config_settings_views.xml',
        'views/layout_templates.xml',
        'views/resenas_templates.xml',
        'views/homepage_templates.xml',
        'views/paginas_templates.xml',
        'data/website_menu_data.xml',
        'data/tienda_data.xml',
        'views/tienda_templates.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'website_dcasa/static/src/scss/primary_variables.scss',
        ],
        'web.assets_frontend': [
            'website_dcasa/static/src/scss/dcasa.scss',
            'website_dcasa/static/src/js/animaciones.js',
        ],
    },
    'installable': True,
}
