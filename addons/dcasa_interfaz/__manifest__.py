{
    'name': "D'CASA Panamá — Interfaz",
    'summary': "Odoo con la cara de D'CASA: tablero de inicio, íconos propios y sin avisos de pago",
    'description': """
La interfaz de trabajo de D'CASA, hecha a medida:

* «Inicio»: tablero del día (ventas, cobros por forma de pago, pedidos web,
  entregas, por cobrar, socios), accesos rápidos y las apps con íconos propios.
* Íconos D'CASA para cada aplicación del menú.
* Barra lateral de navegación (apps y secciones, colapsable, accesible) y un
  sistema de diseño propio: escala de azules, blancos fríos, bordes finos.
* Sin avisos de «Enterprise» ni ventanas de compra: lo que Odoo reserva para su
  versión de pago aparece como «En desarrollo» (lo construimos nosotros).
* Sin el recorrido guiado ni los mensajes de OdooBot; listas vacías sin datos de
  ejemplo ni videos promocionales.
* Sin enlaces a odoo.com (menú de usuario, inicio de sesión) y con la marca en
  los títulos y ventanas.
""",
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_catalogo', 'sale_management', 'stock', 'account', 'web_tour', 'mail_bot'],
    'data': [
        'views/inicio_views.xml',
        'views/login_templates.xml',
        'data/iconos_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_interfaz/static/src/scss/*.scss',
            'dcasa_interfaz/static/src/js/*.js',
            'dcasa_interfaz/static/src/xml/*.xml',
        ],
    },
    'post_init_hook': '_dcasa_interfaz_post_init',
    'installable': True,
}
