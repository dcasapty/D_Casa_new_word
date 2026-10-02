{
    'name': "D'CASA Panamá — Tienda en el borde",
    'summary': 'Catálogo publicado como JSON para la tienda estática del Worker y aviso de cambios',
    'description': """
Fase 2 v1: el sitio público (portada, catálogo, fichas, Visítanos, privacidad y términos) se
genera en el Worker de Cloudflare desde los datos de Odoo; el carrito, el pago, /my y el resto
siguen en Odoo.

* ``GET /dcasa/tienda/feed``: catálogo publicado (solo lectura) protegido con el secreto
  ``TIENDA_FEED_TOKEN`` (cabecera ``X-Dcasa-Tienda-Token``). Mismas URL, precios, «+ ITBMS»,
  categorías, fotos y JSON-LD que las páginas de Odoo.
* Aviso de cambios: precio, nombre, publicación, fotos, existencias, ventas confirmadas y facturas
  dejan una marca «pendiente»; un cron (disparado al confirmar la transacción) avisa al Worker
  (``POST /__edge/tienda/regenerar``) para que regenere las páginas.
* Black Weekend: el feed trae la campaña (ventana ya evaluada en hora de Panamá, productos con su
  precio y combo) y un cron horario regenera la tienda cuando la campaña empieza o termina.
* ``POST /dcasa/carrito/agregar-borde``: «Agregar al carrito» desde las páginas estáticas, sin
  token CSRF pero solo desde el mismo origen (cabeceras Origin / Sec-Fetch-Site / Referer).

Contrato con el Worker: edge/CONTRATO_CONTENEDOR.md, sección «Tienda estática».
""",
    'version': '19.0.1.1.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['website_dcasa', 'website_sale_stock', 'sale', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
    ],
    'installable': True,
}
