{
    'name': "D'CASA Panamá — Busca con una foto",
    'summary': 'En la tienda web: subes la foto de un mueble y salen los productos publicados que se le parecen',
    'description': """
«Busca con una foto» en la tienda web (docs/CATALOGO.md › Busca con una foto). Viene ENCENDIDO (la dueña dijo que sí).

* Un botón de cámara en la búsqueda del sitio (el modal de Odoo) y en la barra de búsqueda de /shop. Abre el
  selector del teléfono (tomar la foto o elegir una de la galería, también una captura de Instagram). El navegador la
  achica antes de subirla (lado mayor de 1024 px, JPEG) y muestra «Buscando muebles parecidos…».
* ``POST /shop/foto`` (con CSRF): valida tipo (JPEG, PNG, WebP) y tamaño (4 MB), aplica los topes (por visitante, por
  conexión y por día) y le pide la lectura al Worker de Juan (``POST /odoo/buscar-foto``), que usa el MISMO lector de
  imágenes de las conversaciones y devuelve solo un registro cerrado (tipo, códigos, categoría, medida, ¿pago?,
  ¿identidad?). Con eso busca SOLO entre productos publicados: primero por código, si no por categoría y medida.
* Un comprobante o una cédula no se buscan: «Esa foto parece un documento; para buscar, sube la foto de un mueble».
* La foto nunca se guarda: ni en Odoo, ni en la base, ni en R2, ni en los registros, ni en el Worker.
* Sitio web › Busca con una foto (Gerencia y administradores): el interruptor, los topes y cuántas búsquedas hubo.
""",
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['website_dcasa', 'dcasa_conversaciones'],
    'data': [
        'security/ir.model.access.csv',
        'data/parametros.xml',
        'data/ir_cron.xml',
        'views/templates.xml',
        'views/ajustes_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_buscar_foto/static/src/scss/buscar_foto.scss',
            'dcasa_buscar_foto/static/src/js/buscar_foto.js',
        ],
    },
    'installable': True,
}
