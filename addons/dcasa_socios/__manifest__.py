{
    'name': "D'CASA Panamá — Socios (puntos y referidos)",
    'summary': "Programa de puntos y referidos de D'CASA dentro de Odoo: puntos automáticos al pagarse "
               "la factura, referidos, premios, canjes, cumpleaños y app del socio con celular + PIN",
    'description': """
Socios D'CASA
=============

Reglas del programa diseñado por Abrinay (repositorio DCasa-Referidos), llevadas
a Odoo para que haya un solo sistema:

* Economía en ``data/puntos.json`` (versionada en git): 1 punto por dólar pagado
  con ITBMS, compra mínima $20, 100 puntos = $1 al canjear.
* Libro mayor inmutable (``dcasa.movimiento``): el saldo es la suma de asientos;
  las correcciones son asientos contrarios con motivo.
* La factura de Odoo pagada suma puntos sola; una nota de crédito o una
  cancelación los devuelve (y deshace el referido que disparó).
* Referidos: padrino 500 / invitado 250 con la PRIMERA compra que da puntos,
  nunca al registrarse; topes de 50 invitados y 5.000 puntos al mes.
* Premios y canjes con código de 72 h; los puntos se reservan al pedir.
* Regalo de cumpleaños automático (una vez al año, con compra previa).
* App del socio en /socios: se entra con celular + PIN (candado 5→15 min,
  10→24 h). Link para invitar: /r/<código> o ?ref=<código> en cualquier página.
* Socios en la web: catálogo público de premios en /socios/premios, puntos en el
  carrito de la tienda (parámetro dcasa_socios.puntos_en_carrito: 'premios' | 'todo')
  con reverso automático si el pedido se cancela, y cuenta unificada: el usuario de la
  tienda ve sus puntos en /my y /socios reconoce su sesión (misma ficha, llave celular).
""",
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_invoice', 'sale_management', 'account', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/product_data.xml',
        'data/premios_data.xml',
        'data/ir_cron_data.xml',
        'wizard/wizard_views.xml',
        'views/res_partner_views.xml',
        'views/dcasa_compra_views.xml',
        'views/dcasa_movimiento_views.xml',
        'views/dcasa_canje_views.xml',
        'views/sale_order_views.xml',
        'views/report_invoice.xml',
        'views/socios_templates.xml',
        'views/website_sale_templates.xml',
        'views/portal_templates.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_socios/static/src/scss/socios.scss',
        ],
    },
    'installable': True,
    'application': True,
}
