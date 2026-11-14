{
    'name': "D'CASA Panamá — Brian de la tienda",
    'summary': 'El chat de ventas de la tienda web: Brian busca muebles, calcula el envío y deja el carrito listo',
    'description': """
«Brian de la tienda» (docs/BRIAN_TIENDA.md). Viene ENCENDIDO: la dueña lo aprobó el 2026-11-13.

* La burbuja con el robot reemplaza la burbuja flotante de WhatsApp (los botones «Escríbenos por WhatsApp» de la página
  se quedan). La pose cambia según la página y, de noche, Brian duerme.
* El navegador habla DIRECTO con el Worker de Juan (``POST {JUAN_URL}/tienda/v1/mensaje``): una respuesta de IA tarda
  segundos y no debe ocupar a Odoo. Odoo solo da el pase firmado (``POST /dcasa/brian/v1/pase``: corto, con la llave
  derivada de ``JUAN_WORKER_TOKEN``, sin secretos nuevos) con un tope por red.
* El modelo nunca toca el carrito: propone y el navegador aplica con la sesión del visitante
  (``/dcasa/brian/v1/carrito/*``); los precios y totales salen de Odoo. Cotización del carrito en PDF.
* No se guarda la conversación ni se crean contactos ni oportunidades. Las estrellas, solo número y fecha.
* Sitio web › Brian de la tienda (Gerencia y administradores): interruptor, presupuesto del mes, topes, gasto y
  calificaciones. Los ajustes llegan al Worker en ``GET /dcasa/juan/v1/config`` (clave ``brian_tienda``).
""",
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['website_dcasa', 'dcasa_conversaciones'],
    'data': [
        'security/ir.model.access.csv',
        'data/parametros.xml',
        'data/ir_cron.xml',
        'report/cotizacion.xml',
        'views/templates.xml',
        'views/ajustes_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_brian_tienda/static/src/scss/brian_tienda.scss',
            'dcasa_brian_tienda/static/src/js/brian_tienda.js',
        ],
        'web.assets_backend': [
            'dcasa_brian_tienda/static/src/xml/costos.xml',
        ],
        'web.assets_tests': [
            'dcasa_brian_tienda/static/tests/tours/*.js',
        ],
    },
    'installable': True,
}
