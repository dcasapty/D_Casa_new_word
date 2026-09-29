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
""",
    'version': '19.0.1.1.0',
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
        'data/res_company_data.xml',
        'data/product_category_data.xml',
        'views/res_partner_views.xml',
    ],
    'post_init_hook': '_dcasa_base_post_init',
    'installable': True,
    'application': False,
}
