{
    'name': "D'CASA Panamá — Correo a clientes (Resend)",
    'summary': 'La factura en PDF al registrar un pago (o el abono con lo que falta), la bienvenida a clientes nuevos '
               "y «Enviar por correo» con la marca D'CASA, por Resend. Apagado de fábrica.",
    'description': """
Correo a clientes por Resend
============================

* **Apagado de fábrica**: sin la clave ``RESEND_API_KEY`` en el servidor no sale ningún correo (Odoo se comporta igual
  que antes) y, con la clave, el interruptor «Enviar correos a clientes» de Ajustes viene apagado. Staging nunca le
  escribe a un cliente. El botón «Enviar correo de prueba» manda uno a quien lo pulsa.
* **Al registrar un pago** de una factura de cliente («Pagar», Brian, la conciliación del banco): al cliente le llega
  su factura en PDF nueva. Si queda saldo, el correo dice cuánto pagó, cuánto le falta y hasta cuándo
  (``_dcasa_estado_abono``). Se encola dentro del pago, en un savepoint: nunca hace fallar el pago y no se duplica.
* **Bienvenida** corta con la marca D'CASA, una sola vez, solo a clientes nuevos (creados desde que se instaló el
  módulo) y cuando ya pueden entrar: cómo entran a Mi cuenta y el botón «Entrar a Mi cuenta». Sin cifras.
* **«Enviar» de la factura** (la casilla de correo de Odoo) y de la cotización con la plantilla D'CASA, y «Enviar por
  correo» en el diálogo de la cotización del panel de Conversaciones. Brian: ``enviar_factura_por_correo`` y
  ``enviar_cotizacion_por_correo``.
* La lista «Correos a clientes» (Gerencia) dice qué salió, qué no y por qué. Los errores temporales de Resend se
  reintentan solos.

Paso a paso para la dueña: ``docs/CORREO.md``.
""",
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['mail', 'account', 'sale', 'sale_management', 'dcasa_base', 'dcasa_invoice', 'dcasa_socios',
                'website_dcasa', 'dcasa_conversaciones'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/layout_correo.xml',
        'data/mail_templates.xml',
        'views/res_config_settings_views.xml',
        'views/correo_envio_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_correo/static/src/js/cotizacion_correo.js',
            'dcasa_correo/static/src/xml/cotizacion_correo.xml',
        ],
    },
    'post_init_hook': '_dcasa_correo_post_init',
    'installable': True,
}
