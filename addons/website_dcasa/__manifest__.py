{
    'name': "D'CASA Panamá — Sitio web",
    'summary': "Sitio web y tienda de D'CASA con su marca, mantenido desde el código (sin constructor)",
    'description': """
Sitio web de D'CASA sobre el constructor de sitios y el eCommerce de Odoo:

* Paleta y tipografías de la marca (azul #1340B1, amarillo #FED00F, Anton,
  Oswald, Inter) cargadas como paleta del sitio: se pueden ajustar desde el
  editor sin tocar código.
* Portada v2 (docs/historico/REDISENO.md): hero con placa, compra por espacio, carriles de
  productos con precio y «Agregar» en un clic, socios, guía y preguntas frecuentes.
* Ficha de producto con WhatsApp del mueble, sellos de confianza y botón fijo en el
  celular; tienda a 4 columnas; datos estructurados y SEO local.
* Pie de página con los datos reales y botón flotante de WhatsApp, sin el crédito de Odoo.
* La píldora de /socios en todas las páginas (logo, menú, carrito, búsqueda, cuenta y
  «Escríbenos»), la foto de la portada con sus colores reales y el texto en placa navy,
  cabeceras de página como la de /socios (legales, cuenta) y fotos de producto en 3:4.
* Cabecera de vidrio flotante, animaciones de entrada (secciones y titulares) y
  opiniones reales de Google en una cinta en movimiento (data/resenas.json).
* Categorías de la tienda (Salas, Recámaras, Colchones, Zapateras, Estantes y
  organización, Oficina, y otras que la tienda oculta mientras no tengan productos).
* Fotos de producto en WebP (y JPEG de respaldo) al ancho justo: ``/dcasa/img/...``,
  generadas una vez y cacheadas un año en el borde (models/imagen.py).
* Enlaces al programa Socios D'CASA (/socios): puntos, referidos y premios.
* Búsqueda (lote 1 de la web, 2026-11-13): la lupa también a la vista en el celular; la caja de la cabecera
  busca en el catálogo (/shop?search=…, con fotos grandes, «+ ITBMS» y el botón de agregar) y una tilde ya no
  da «no coincidió…»; sin resultados ofrece las categorías y WhatsApp. /catalogo y /tienda llevan al catálogo
  (301). Las páginas para entrar y los resultados de búsqueda no salen en Google (noindex). Carrito vacío en
  tuteo y la foto de la ficha en grande con el dedo (models/buscador.py, views/buscador_templates.xml).
* Visítanos y opiniones (lote 2 de la web, 2026-11-13): el horario de la tienda en una tabla y en el pie, sacado
  de un solo lugar (el gancho ``website._dcasa_horario_tienda``, que llena dcasa_conversaciones con los Ajustes de
  Juan); el mapa de Google solo con las cookies aceptadas o al tocar «Ver el mapa»; opiniones de productos de
  quien los compró y pagó, publicadas solo si Gerencia las aprueba (models/resena.py), con estrellas en la ficha y
  ``aggregateRating`` solo con las publicadas.
* Black Weekend: banda en la portada, página /black-weekend y etiqueta en las tarjetas de los
  productos marcados, solo dentro de la ventana de la campaña (models/black_weekend.py).

Todo el contenido de las páginas es editable con el constructor de Odoo
(Sitio web > Editar), sin programador.
""",
    'version': '19.0.1.18.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_socios', 'dcasa_contactos', 'website_sale'],
    'data': [
        'security/dcasa_roles_website.xml',
        'security/ir.model.access.csv',
        'data/website_data.xml',
        'data/product_public_category_data.xml',
        'views/res_config_settings_views.xml',
        'views/apartados_views.xml',
        'views/resenas_views.xml',
        'views/layout_templates.xml',
        'views/resenas_templates.xml',
        'views/black_weekend_templates.xml',
        'views/campana_views.xml',
        'views/homepage_templates.xml',
        'views/paginas_templates.xml',
        'views/legal_templates.xml',
        'data/website_menu_data.xml',
        'data/tienda_data.xml',
        'views/tienda_templates.xml',
        'views/opiniones_templates.xml',
        'views/buscador_templates.xml',
        'views/nombres_cliente_templates.xml',
        'data/seo_data.xml',
        'data/black_weekend_data.xml',
        'data/ir_cron_data.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'website_dcasa/static/src/scss/primary_variables.scss',
        ],
        'web.assets_frontend': [
            'website_dcasa/static/src/scss/fuentes.scss',
            'website_dcasa/static/src/scss/dcasa.scss',
            'website_dcasa/static/src/js/animaciones.js',
            'website_dcasa/static/src/js/carrito.js',
            'website_dcasa/static/src/js/carril.js',
            'website_dcasa/static/src/js/foto_grande.js',
            'website_dcasa/static/src/js/mapa.js',
        ],
    },
    'installable': True,
}
