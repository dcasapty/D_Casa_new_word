{
    'name': "D'CASA Panamá — Tienda en el borde",
    'summary': 'Caché en el borde del HTML de Odoo para visitantes anónimos y aviso de cambios',
    'description': """
Caché en el borde (Worker de Cloudflare) del HTML que dibuja Odoo: una sola fuente de diseño.
El Worker guarda la página que Odoo dibuja para un visitante anónimo y la sirve a los anónimos;
quien tiene sesión propia (usuario, carrito, deseos, socio) pasa directo a Odoo.

* Cookie ``dcasa_personal``: Odoo la pone a quien tiene algo propio en la sesión y la quita cuando
  ya no (``models/ir_http.py``). Con ella el borde no sirve nada guardado.
* Cabecera ``X-Dcasa-Borde: <TIENDA_FEED_TOKEN>``: el borde pide así la página a guardar (sin
  cookies). Odoo no guarda sesión ni pone cookies y responde ``X-Dcasa-Borde: anonimo`` si la
  dibujó para el usuario público; sin esa marca el borde no la guarda.
* ``GET /dcasa/borde/csrf`` + ``static/src/js/borde_csrf.js``: el token CSRF de una página guardada
  es de otra sesión; antes de enviar un formulario se pide uno de la sesión de quien la ve.
* Aviso de cambios: precio, nombre, publicación, fotos, existencias, ventas confirmadas, facturas,
  categorías, ajustes del sitio, plantillas, menú, páginas, tarifas y Black Weekend dejan una marca
  «pendiente»; un cron (disparado al confirmar la transacción) avisa al Worker
  (``POST /__edge/tienda/regenerar``), que da por viejas las páginas guardadas y vuelve a pedir
  las principales.

Contrato con el Worker: edge/CONTRATO_CONTENEDOR.md, sección «Caché de páginas».
""",
    'version': '19.0.2.0.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['website_dcasa', 'website_sale_stock', 'sale', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_tienda_borde/static/src/js/borde_csrf.js',
        ],
    },
    'installable': True,
}
