{
    'name': "D'CASA Panamá — Catálogo",
    'summary': "Productos reales de D'CASA (Excel + fotos de «up media») en inventario y tienda web",
    'description': """
Carga el catálogo real de D'CASA en Odoo: el mismo producto para el inventario,
las ventas y la tienda web.

* data/catalogo.json y static/img/productos/ los genera scripts/importar_catalogo.py
  a partir de «up media/DCASA_listado_productos.xlsx» y de las fotos (nombre = código).
* Precios del Excel tal cual, con ITBMS incluido (impuesto «ITBMS 7% incluido»).
* Camas y colchones con tamaños (Twin, Full, Queen, King) como variantes.
* Varias fotos por código: la primera es la principal, el resto va a la galería.
* Productos sin foto quedan en inventario sin publicar en la web.
* Idempotente: volver a correr la carga solo crea lo que falta; no pisa lo que la
  dueña cambió en Odoo (precios, fotos, textos).
""",
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'website_dcasa', 'website_sale_stock'],
    'data': [
        'data/product_category_data.xml',
    ],
    'post_init_hook': '_dcasa_catalogo_post_init',
    'installable': True,
}
