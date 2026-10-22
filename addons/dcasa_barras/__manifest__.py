{
    'name': "D'CASA Panamá — Lector de códigos de barras",
    'summary': "Escanea un código y ve el producto, su precio y sus existencias; cuenta el inventario con el lector",
    'description': """
El «Escáner de códigos de barras» de Odoo es de pago (Enterprise). Esto es lo que D'CASA necesita con lo que sí trae
Odoo Community:

* Inventario › Escáner: se escanea (o se escribe) un código y sale la foto, el nombre, la referencia, el precio
  «+ ITBMS», las existencias por ubicación y si está disponible, con pocas o agotado. Sirve con un lector que escribe
  como teclado (Bluetooth, 2.4G o USB) y con el Android con lector integrado.
* Contar: Gerencia escribe lo contado y se registra el ajuste de inventario de Odoo (queda en el historial).
* Se encuentra el producto por código de barras, por referencia interna (aunque aún no tenga código) y por el código
  de su empaque. Tolera guiones y mayúsculas distintos según el teclado del lector.
* Inventario › Configuración › Códigos de barras: llena el código de barras de los productos que no tienen, a partir
  de su referencia interna. Nunca pisa uno que ya existe, avisa lo repetido y se puede deshacer.
* Escáner › Asignar: etiquetas numeradas de un rollo (DC0001, DC0002…): se escanea la etiqueta, se elige el producto y
  ese número queda como su código de barras. Se puede pasar a otro producto, reemplazar o quitar; el número viejo queda
  retirado y avisa si alguien lo escanea. Cada cambio queda en el historial. Solo Gerencia.
* El código QR de uso interno de un documento (factura, cotización, pedido de compra, entrega; ver dcasa_invoice): al
  escanearlo, el Escáner abre ese documento si tienes permiso para verlo. Todo lo demás se escanea como siempre.
* Inventario › Bodega (y el acceso «Bodega» del Inicio): las entregas pendientes «Para despachar (envío)» y «Para
  retirar en tienda», pensado para tablet. Se abre una entrega tocándola o escaneando el QR de su nota de entrega, se
  marca lo que sale (también escaneando cada producto) y se valida; si falta algo, lo demás queda pendiente.
""",
    'version': '19.0.1.3.0',
    'category': 'Inventory/Inventory',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_catalogo', 'dcasa_interfaz', 'dcasa_invoice', 'stock', 'stock_delivery'],
    'data': [
        'security/ir.model.access.csv',
        'security/barras_security.xml',
        'views/asignacion_views.xml',
        'views/etiqueta_views.xml',
        'views/menus.xml',
        'views/bodega_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_barras/static/src/scss/*.scss',
            'dcasa_barras/static/src/js/*.js',
            'dcasa_barras/static/src/xml/*.xml',
        ],
    },
    'post_init_hook': '_dcasa_post_init',
    'installable': True,
}
