{
    'name': "D'CASA Panamá — Catálogo para Meta",
    'summary': "El catálogo de la tienda en línea por URL para los anuncios de Facebook e Instagram (Meta)",
    'description': """
Las bases para anunciar el catálogo en Meta (Facebook e Instagram) con anuncios de catálogo (Advantage+ catalog ads).
Viene APAGADO: la dirección no entrega nada hasta que Gerencia lo enciende. Ver docs/META_CATALOGO.md.

* Sitio web › Anuncios en Meta › Catálogo para Meta: el interruptor, la dirección secreta (con botón de copiar) que
  Meta lee cada hora o cada día, cuántos productos van y cuáles quedan fuera y por qué (sin foto, sin precio o
  marcados «No anunciar»), «Regenerar ahora» y «Cambiar la dirección secreta». Marca, condición y disponibilidad
  («como la web» o «según existencias»).
* El catálogo (``/dcasa/meta/catalogo.csv``): una fila por variante publicada, con el precio de la página (sin ITBMS),
  su enlace y sus fotos en JPEG. El ``id`` es el de la variante en Odoo: el mismo que usan el píxel y la Conversions
  API (dcasa_meta_eventos). Nunca la referencia del proveedor, el código de barras ni el costo.
* Etiquetas para armar conjuntos de productos en Meta: categoría, campaña, existencias (disponible / pocas /
  agotado), franja de precio y el código público DC del producto.
* Campañas para anuncios: Gerencia crea «Navidad», la pone en varios productos a la vez desde Productos y en Meta arma
  el conjunto con «Etiqueta personalizada 1 es igual a navidad».
* El CSV se guarda y solo se vuelve a armar si cambió algo (o pasó un día). El feed de Google de Odoo (``/gmc.xml``)
  nunca sirve el de Meta.
""",
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['website_sale_stock', 'website_dcasa', 'dcasa_catalogo', 'dcasa_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/meta_catalogo_views.xml',
        'views/product_views.xml',
        'data/product_feed_data.xml',
    ],
    'installable': True,
}
