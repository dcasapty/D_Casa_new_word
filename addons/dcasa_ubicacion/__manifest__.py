{
    'name': 'Ubicación exacta de entrega (web, chat y QR del chofer)',
    'summary': 'El cliente marca su punto en el mapa (web o enlace del chat) o lo comparte por WhatsApp; el envío se '
               'cotiza solo y el comprobante lleva un QR con Waze y Google Maps para el chofer',
    'description': """
Pedido del dueño de Baby Caleb (2026-11-25), con la idea de Nébula y sus fallas corregidas. Ver docs/UBICACION.md.

* **Checkout**: «¿Dónde te entregamos?» con «Marcar en el mapa» (Google Maps, pin fijo, «Usar mi ubicación», buscador
  de barriadas y lugares de la tabla de envíos, «¿Es aquí?») o «Escribirla». La zona (barriada, corregimiento,
  distrito, provincia) sale de la tabla de la calculadora y el precio del envío, de ahí mismo.
* **Chat**: el enlace de un solo uso ``/u/<secreto>`` amarrado a la conversación (Juan lo manda; al confirmar, Juan le
  escribe con la zona y el precio) y ``POST /dcasa/juan/v1/ubicacion`` para la ubicación de WhatsApp o un enlace de
  mapa. ``cotizar_envio`` sin lugar usa el punto guardado.
* **Chofer**: el QR del comprobante y de la nota de entrega abre ``/entrega/<secreto>`` (Waze, Google Maps,
  dirección, referencia, llamar). Vence a los 30 días y no cambia nada.
* **Brian / MCP**: ``ubicacion_de_entrega``, ``enlace_de_ubicacion_para_cliente`` y ``poner_ubicacion_de_entrega``.
* **Para que no vuelva el pedido**: quién recibe y un teléfono de respaldo (checkout, enlace, Juan con
  ``guardar_quien_recibe``, Brian con ``poner_quien_recibe``), la foto de la fachada (sin EXIF; la ve el chofer
  en ``/entrega/<secreto>/fachada``), «Avisar que llegué» por WhatsApp y la tarjeta «Marcar mi casa» al pagar.
* **Avisos** (models/avisos.py): al confirmar una venta a domicilio sin la casa en el mapa, el asistente le pide el
  punto por el chat (o queda un pendiente y «📲 Pedir ubicación por WhatsApp»); el día de la entrega, «🚚 Sale hoy:
  avisarle» (venta, entrega, lista y Brian: ``pedir_ubicacion_al_cliente`` y ``avisar_que_sale_hoy``).
* Claves (opcionales, en Cloudflare): ``GOOGLE_MAPS_CLAVE_NAVEGADOR`` (el mapa) y ``GOOGLE_MAPS_CLAVE_SERVIDOR`` (la
  calle). Sin ellas: GPS, búsqueda en la tabla y dirección escrita siguen funcionando.
""",
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_envios', 'dcasa_conversaciones', 'website_dcasa', 'dcasa_invoice', 'dcasa_brian',
                'dcasa_brian_tienda', 'website_sale', 'delivery', 'sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/iconos_templates.xml',
        'views/casa_iconos_templates.xml',
        'views/paginas_templates.xml',
        'views/checkout_templates.xml',
        'views/reporte_templates.xml',
        'views/pedido_templates.xml',
        'views/backend_views.xml',
        'views/casa_views.xml',
        'data/avisos_data.xml',
        'views/avisos_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_ubicacion/static/src/lib/mapa_entrega.js',
            'dcasa_ubicacion/static/src/interactions/checkout_ubicacion.js',
            'dcasa_ubicacion/static/src/scss/ubicacion.scss',
        ],
    },
    'installable': True,
}
