{
    'name': "D'CASA Panamá — Catálogo",
    'summary': "Productos reales de D'CASA (Excel + fotos de «up media») en inventario y tienda web",
    'description': """
Carga el catálogo real de D'CASA en Odoo: el mismo producto para el inventario,
las ventas y la tienda web.

* data/catalogo.json y static/img/productos/ los genera scripts/importar_catalogo.py
  a partir de «up media/DCASA_listado_productos.xlsx» y de las fotos (nombre = código).
* Precios del Excel tal cual, SIN ITBMS: el ITBMS 7 % se suma al precio (en la web,
  «$39.99 + ITBMS»; el total con impuesto sale en carrito, cotización y factura).
* Camas y colchones con tamaños (Twin, Full, Queen, King) como variantes.
* Varias fotos por código: la primera es la principal, el resto va a la galería.
* Productos sin foto quedan en inventario sin publicar en la web.
* Nombres que distinguen cada mueble (color y rasgos que se ven en la foto) y medidas
  cuando vienen impresas en la foto (data/fichas.json), con su lugar en la ficha.
* En Odoo: buscar por varias palabras («colchón queen»), lista de productos con foto y
  cotización por WhatsApp en un clic.
* Pedidos nuevos del proveedor (LTSC-07) por el mismo camino: precios terminados en .99,
  combo con el nombre del colchón, colores de un mismo código como variantes y código que
  ya existía como producto aparte (-LTSC07). Ver docs/CATALOGO.md.
* Existencias de prueba solo en staging (dcasa_catalogo.stock_prueba; producción siempre 0).
* Idempotente: volver a correr la carga solo crea lo que falta; no pisa lo que la
  dueña cambió en Odoo (precios, fotos, textos).
""",
    'version': '19.0.1.3.0',
    'category': 'Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'website_dcasa', 'website_sale_stock'],
    'data': [
        'data/product_category_data.xml',
        'data/product_public_category_data.xml',
        'views/backend_views.xml',
        'views/product_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_catalogo/static/src/scss/catalogo.scss',
        ],
    },
    'post_init_hook': '_dcasa_catalogo_post_init',
    'installable': True,
}
