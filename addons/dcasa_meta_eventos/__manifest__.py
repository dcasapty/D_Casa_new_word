{
    'name': "D'CASA Panamá — Meta: píxel y ventas (Conversions API)",
    'summary': 'Píxel de Meta con consentimiento y las compras pagadas de la web y de la tienda hacia la Conversions '
               'API, con cola, reintentos y botón de prueba. Todo apagado de fábrica.',
    'description': """
Meta: píxel y ventas
====================

* **Apagado de fábrica.** Nada sale hacia Meta sin las cuatro condiciones: el interruptor encendido, la sección de
  Meta en la política de privacidad publicada (``id="privacidad-meta"``), el token ``META_CAPI_TOKEN`` en el servidor
  (para las ventas) y el consentimiento de la persona.
* **Píxel**: el sitio solo dibuja el atributo ``data-dcasa-meta-pixel``; el píxel se carga en el navegador después de
  que la persona acepta las cookies (ViewContent, AddToCart, InitiateCheckout, AddPaymentInfo, Search, Contact). Nunca
  manda la compra. Solo en producción y nunca para el personal con sesión.
* **Conversions API**: cada factura de cliente que queda pagada deja una fila en una cola (dentro de un savepoint, sin
  HTTP: un fallo de Meta nunca hace fallar un cobro) y un cron la manda con reintentos. El correo y el celular solo
  viajan cifrados con SHA-256 y solo con el consentimiento de la persona. Fuera de producción solo sale lo que lleva el
  código de prueba.
* **Consentimiento**: el aviso de cookies (navegador) y la casilla de la ficha del cliente o del checkout (persona),
  con fecha, dónde y quién.
* Sitio web › eCommerce › «Eventos enviados a Meta» (Gerencia) y Sitio web › Configuración › «Meta: píxel y ventas»
  (administradores) con el botón «Enviar evento de prueba».

Paso a paso y borrador de privacidad: ``docs/META_EVENTOS.md``.
""",
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'website_dcasa', 'dcasa_contactos', 'dcasa_tienda_borde', 'dcasa_base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/templates.xml',
        'views/meta_evento_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_meta_eventos/static/src/scss/meta.scss',
            'dcasa_meta_eventos/static/src/js/meta_pixel.js',
        ],
    },
    'installable': True,
}
