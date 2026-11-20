{
    'name': "D'CASA Panamá — Pagos con Tilopay",
    'summary': 'Tarjeta (y lo que tenga activo la cuenta) en la página segura de Tilopay: el pago se confirma '
               'preguntándole a Tilopay, nunca por lo que diga el navegador. Nace apagado.',
    'description': """
Pagos con Tilopay
=================

* El cliente paga en la **página alojada de Tilopay** (Odoo nunca ve una tarjeta). Al volver, o cuando Tilopay avisa, o
  cuando una tarea programada pregunta, Odoo **consulta a Tilopay de servidor a servidor** y solo marca pagado si
  la orden
  existe, está aprobada, el monto y la moneda son exactamente los del pedido y el pago es del entorno que se espera
  (prueba o real).
* **Las claves viven solo como secretos del Worker de Cloudflare** (``TILOPAY_API_KEY``, ``TILOPAY_API_USER``,
  ``TILOPAY_API_PASSWORD``; el entorno, ``TILOPAY_ENTORNO``). Nunca en la base, en un log ni en la pantalla.
* Nace **apagado**. Se ofrece en la tienda solo si Gerencia lo activa, las claves están cargadas y el interruptor de
  Odoo coincide con ``TILOPAY_ENTORNO``.
* El cobro queda en el diario «Tilopay» (forma de pago visible en Caja y en «Cobrado por forma de pago»).
* Versión 1: el pedido completo de la tienda y del portal. Abonos parciales y reembolsos: siguiente paso.

Investigación, amenazas, qué poner en Cloudflare y guion de pruebas: ``docs/TILOPAY.md``.
""",
    'version': '19.0.1.1.0',
    'category': 'Accounting/Payment Providers',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['payment', 'account_payment', 'website_sale', 'dcasa_base'],
    'data': [
        'views/payment_tilopay_templates.xml',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        'data/ir_cron.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
}
