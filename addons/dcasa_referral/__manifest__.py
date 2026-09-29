{
    'name': "D'CASA Panamá — Referidos",
    'summary': "Programa de referidos: código por cliente, link para compartir y recompensa al pagarse la factura",
    'description': """
Programa de referidos de D'CASA.

* Cada cliente puede tener un código de referido (p. ej. ``DC7K3M9Q``) y un
  link para compartir: ``/r/<código>``.
* La orden de venta guarda quién refirió al cliente. En la tienda física o por
  WhatsApp la vendedora lo elige escribiendo el código o el nombre; en la web
  se toma del link compartido.
* Al publicarse la factura del referido se crea una recompensa **pendiente**;
  cuando la factura queda pagada pasa a **ganada**; si se anula o se revierte
  con nota de crédito, pasa a **anulada**. El pago al referidor se marca a mano.
* Recompensa configurable en Ventas > Configuración > Ajustes: porcentaje del
  subtotal sin ITBMS o monto fijo, y opción de premiar solo la primera compra.
* Portal: el cliente ve su código, su link y sus recompensas en /my/referidos.
""",
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'sale_management', 'account', 'portal', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/res_partner_views.xml',
        'views/dcasa_referral_reward_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/portal_templates.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
