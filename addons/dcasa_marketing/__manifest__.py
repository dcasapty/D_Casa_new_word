{
    'name': "D'CASA Panamá — Marketing y fotos de productos",
    'summary': "Ver las fotos en grande, subir varias, ordenarlas y recortarlas; y «Marketing»: lo que se vende, "
               "lo quieto, el stock por categoría y las fotos que faltan",
    'description': """
Pedido de la dueña (2026-10-22): «ver la foto de un producto es un problema terrible» y «créame un botón de Marketing».

* **Fotos del producto** (ficha, lista y tarjetas de Productos, y el Escáner): al tocar la foto se abre en grande, casi
  a pantalla completa, con zoom (pellizcar en el celular, la rueda o los botones en la computadora), se pasa entre
  todas las fotos del producto y, quien puede editar el producto, la reemplaza (archivo o cámara), la recorta, la gira,
  la pone como principal, la quita o la descarga. Quien no puede editarlo solo ve y descarga.
* **Galería** (también en la pestaña Ventas del producto): todas las fotos (la principal y las «Imágenes extra» de la
  tienda) en cuadrícula grande; se suben varias a la vez (elegir varias o arrastrar y soltar), se ordenan arrastrando
  (también en el celular, dejando el dedo un momento) o con las flechas, y la primera es la principal.
* **Marketing** (app propia y acceso en el Inicio de Gerencia y administradores): por categoría, los productos con más
  y menos stock; los más vendidos (unidades, con la misma base del Inicio: facturas publicadas); lo que más se movió
  y lo más quieto en Semana / 15 días / Mes; y «Fotos»: buscar un producto por nombre, código o código de barras y
  subirle sus fotos ahí mismo, con los que no tienen foto o tienen una sola marcados.
* Brian: ``movimiento_de_productos`` y ``fotos_que_faltan``.

Ver docs/MARKETING.md.
""",
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_catalogo', 'dcasa_interfaz', 'dcasa_barras', 'dcasa_brian', 'website_sale', 'html_editor'],
    'data': [
        'views/marketing_views.xml',
        'views/product_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_marketing/static/src/scss/*.scss',
            'dcasa_marketing/static/src/js/*.js',
            'dcasa_marketing/static/src/xml/*.xml',
        ],
    },
    'installable': True,
}
