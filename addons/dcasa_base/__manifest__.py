{
    'name': "D'CASA Panamá — Base",
    'summary': "Configuración base de D'CASA: empresa, Panamá (ITBMS 7%), RUC con DV y apps del ERP",
    'description': """
Módulo raíz del ERP de D'CASA Panamá.

* Instala las apps que usa la mueblería: Ventas, Inventario, Facturación,
  Compras, CRM y Contactos, con la localización de Panamá (ITBMS 7%).
* Deja la empresa configurada (RUC con DV, dirección, logo, moneda USD).
* Añade el Dígito Verificador (DV) al contacto y lo muestra junto al RUC.
* Guarda los adjuntos en la base de datos: el contenedor en Cloudflare es
  efímero y no tiene disco persistente.
* Odoo al grano para la tienda: en español y hora de Panamá, precios sin ITBMS
  (el 7 % se suma), descuentos y tamaños visibles, cobros en Efectivo, Yappy y Tarjeta,
  y las financieras Tafi y Crediviva, menú «Hoy» (ventas y cobros del día) y sin menús que no se usan.
* Interfaz con la marca: azul D'CASA en vez del morado de Odoo, letra Inter y
  cantidades enteras (se venden camas, no cuartos de cama).
* Roles de la tienda «D'CASA / Vendedora» (ve solo lo suyo), «D'CASA / Caja»
  (factura y cobra todo lo de clientes) y «D'CASA / Gerencia», con el interruptor
  «Cada vendedora ve solo sus documentos» (Ajustes de Ventas y, para Gerencia,
  Ventas › Configuración › Permisos de las vendedoras), y tope de descuento por
  línea para quien no es Gerencia (Ajustes de Ventas).
* Reglas contables de la gerencia (2026-10-17): el cobro solo en Caja (la Vendedora ya
  no registra cobros por ningún camino); pasar a borrador o anular una factura publicada,
  notas de crédito, devolver dinero y dejar saldo a favor, solo Gerencia.
* Barandas de costo: depuración mensual (adjuntos huérfanos, correos fallidos)
  y reporte mensual de tamaños de la base con aviso al pasar 0,7 GB.
* Operación: vigilancia horaria de disco, memoria y tamaño de la base con aviso por
  Telegram (canal de Brian, vía dcasa_seguridad) y apagado de las acciones planificadas
  de Odoo que no aplican a la tienda.
""",
    'version': '19.0.1.9.0',
    'category': 'Hidden',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': [
        'contacts',
        'crm',
        'sale_management',
        'sale_stock',
        'purchase',
        'stock',
        'account',
        'l10n_pa',
    ],
    'data': [
        'security/dcasa_roles.xml',
        'security/dcasa_reglas_ventas.xml',
        'security/dcasa_reglas_contables.xml',
        'security/ir.model.access.csv',
        'data/res_company_data.xml',
        'data/descuento_data.xml',
        'data/product_category_data.xml',
        'data/ir_cron_data.xml',
        'data/crons_odoo.xml',
        'data/menus_roles_data.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/hoy_views.xml',
        'views/res_config_settings_views.xml',
        'views/solo_lo_suyo_views.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'dcasa_base/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'dcasa_base/static/src/scss/backend.scss',
            'dcasa_base/static/src/scss/copiar.scss',
            'dcasa_base/static/src/js/*.js',
            'dcasa_base/static/src/xml/*.xml',
        ],
    },
    'post_init_hook': '_dcasa_base_post_init',
    'installable': True,
    'application': False,
}
