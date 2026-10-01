{
    'name': "D'CASA Panamá — Adjuntos en R2",
    'summary': "Guarda el contenido de los adjuntos (fotos, PDF, assets) en Cloudflare R2 en lugar de la base",
    'description': """
El contenedor de Cloudflare no tiene disco persistente y la base se respalda entera
(pgBackRest + pg_dump) en R2: hoy los adjuntos son la mayor parte de su tamaño.

* ``ir_attachment.location = r2``: el contenido va a R2 (API S3) con la llave
  ``adjuntos/<sha1[:2]>/<sha1>`` (direccionado por contenido, como el filestore de Odoo).
  En la base solo queda ``store_fname = r2://adjuntos/...``.
* Sin credenciales (CI, desarrollo) se comporta como ``db``.
* Nunca borra en R2 al desvincular: una restauración a un punto anterior de la base
  volvería a apuntar a esos objetos. Los borra un cron solo si nadie los referencia
  y llevan más que la ventana de respaldos sin uso (por defecto 45 días).
* Migración por lotes db → r2 (cron) y r2 → db (emergencia, desde ``odoo-bin shell``).

Ver docs/OPERACION.md → «Adjuntos en R2».
""",
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
    ],
    'uninstall_hook': '_dcasa_adjuntos_r2_uninstall',
    'installable': True,
    'application': False,
}
