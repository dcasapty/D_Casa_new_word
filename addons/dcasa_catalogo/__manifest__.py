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
* Black Weekend: marca los 12 productos elegidos por la dueña (catalogo.BLACK_WEEKEND, por código;
  908K con su variante negra destacada). La ventana de la campaña vive en website_dcasa.
* Existencias de prueba solo en staging (dcasa_catalogo.stock_prueba; producción siempre 0).
* Inventario del sistema anterior (data/inventario_anterior.csv, transcrito de las capturas de
  «up media/inventario-anterior»): existencias, costo y precio por código; los códigos nuevos
  entran como productos (publicados solo con foto); combos con colchón sin publicar.
* Stock ordenable en Productos (campo dcasa_stock, guardado en cada producto): la lista de Productos ordena, filtra
  y suma por stock, precio y categoría para elegir qué empujar en una campaña; Productos abre en lista.
* Código público (DC-K7M4PX) a la vista en la ficha del producto, columna opcional en la lista y buscable en
  Productos y en las cotizaciones (el campo y el sorteo viven en dcasa_base). Esta versión se lo da a los
  productos que ya existían. Ver docs/CATALOGO.md.
* Combos cama + colchón que se arman en la venta (2026-10-22): botón «Armar combo» en la cotización (escoges la
  cama y salen los colchones de su medida con existencia); cada colchón tiene su «Precio en combo» por medida, que
  pone Gerencia en Ventas › Productos › Precios en combo, y se cobra solo si en la misma venta va una cama de su
  medida. Reglas en el servidor (models/combo_armable.py); en el papel, «Combo cama + colchón» y el ahorro.
  Ver docs/OPERACION.md.
* Idempotente: volver a correr la carga solo crea lo que falta; no pisa lo que la
  dueña cambió en Odoo (precios, fotos, textos).
""",
    'version': '19.0.1.11.0',
    'category': 'Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'website_dcasa', 'website_sale_stock'],
    'data': [
        'data/product_category_data.xml',
        'data/product_public_category_data.xml',
        'views/backend_views.xml',
        'views/codigo_publico_views.xml',
        'views/copiar_views.xml',
        'views/product_templates.xml',
        'views/combos_views.xml',
        'views/report_combos.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_catalogo/static/src/scss/catalogo.scss',
        ],
        'web.assets_backend': [
            'dcasa_catalogo/static/src/combo/armar_combo.js',
            'dcasa_catalogo/static/src/combo/armar_combo.xml',
            'dcasa_catalogo/static/src/combo/armar_combo.scss',
        ],
    },
    'post_init_hook': '_dcasa_catalogo_post_init',
    'installable': True,
}
