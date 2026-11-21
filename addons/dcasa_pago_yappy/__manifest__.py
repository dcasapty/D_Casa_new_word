{
    'name': "D'CASA Panamá — Pagos con Yappy directo",
    'summary': 'El Botón de Pago de Yappy Comercial, directo con el banco: el pago se confirma solo con el aviso '
               'firmado de Yappy, nunca por lo que diga el navegador. Nace apagado.',
    'description': """
Pagos con Yappy directo
=======================

* El cliente paga con el **botón de Yappy** dentro de la tienda: escribe su número, recibe la solicitud en su app y la
  confirma. Es el Botón de Pago de Yappy Comercial, directo con el banco (la cuenta de Tilopay no habilita Yappy).
* **El navegador nunca marca un pago.** Solo el aviso (IPN) de Yappy, con su hash HMAC-SHA256 comprobado en tiempo
  constante y con un dominio nuestro, paga el pedido. Estados: E pagó; R no confirmó a tiempo; C canceló en la app; X la
  solicitud venció.
* **Las claves viven solo como variables del Worker de Cloudflare** (``YAPPY_ID_COMERCIO`` y ``YAPPY_CLAVE_SECRETA``,
  secretas; ``YAPPY_DOMINIO`` y ``YAPPY_ENTORNO``, normales). Nunca en la base, en un log ni en la pantalla.
* Nace **apagado**. Se ofrece en la tienda solo si Gerencia lo activa, las claves están cargadas y el interruptor de
  Odoo coincide con ``YAPPY_ENTORNO``. Cuando se ofrece reemplaza al «Yappy» manual de siempre: nunca se ven dos.
* El cobro queda en el diario «Yappy». Sin comisiones inventadas.
* El equipo ve **qué compró** cada persona: el pedido (productos, modelos, cantidades, precios), el cliente, la
  entrega, el origen y cómo pagó; y la orden de Yappy empieza con el número del pedido.
* Si el aviso se pierde (Yappy no tiene consulta de estado), una tarea le deja a Caja un pendiente claro; no paga ni
  cancela.

Cómo funciona, qué poner en Cloudflare, la lista antes de cobrar de verdad y las amenazas: ``docs/YAPPY.md``.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['payment', 'account_payment', 'website_sale', 'dcasa_base', 'website_dcasa'],
    'data': [
        'views/payment_yappy_templates.xml',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        'data/ir_cron.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_pago_yappy/static/src/scss/yappy.scss',
            'dcasa_pago_yappy/static/src/interactions/payment_form.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
}
