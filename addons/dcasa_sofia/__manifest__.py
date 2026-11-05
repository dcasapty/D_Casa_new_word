{
    'name': "D'CASA Panamá — Sofía, la asistente del CRM",
    'summary': 'Revisa el CRM con un botón y cada mañana, y propone a quién escribirle, qué repartir y qué datos pedir',
    'description': """
Sofía es la asistente del CRM (como Brian lo es del administrador). No cambia nada por su cuenta: revisa el CRM con el
botón «Organizar con Sofía» y cada mañana, y deja propuestas que una persona aprueba o descarta:

* contestar a quien espera, recordar la cotización que vence, escribirle a los tibios y calientes que nadie atendió;
* pedir el nombre y apellido y el correo a quien llegó por WhatsApp o redes con un emoji o una frase (para avisarle de
  promociones, del programa Socios y de su cumpleaños) y guardar el correo que escribió en el chat;
* repartir las oportunidades sin vendedora y poner en la oportunidad a la vendedora que atiende su chat (Gerencia).

Gerencia ve y aprueba todo; cada vendedora lo suyo, con un resumen por Telegram cada mañana. No toca el proceso de Juan.
Ver docs/SOFIA.md.
""",
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_conversaciones', 'dcasa_contactos', 'sale_crm'],
    'data': [
        'security/sofia_security.xml',
        'security/ir.model.access.csv',
        'data/plantillas.xml',
        'data/ir_cron.xml',
        'views/sofia_views.xml',
        'views/ajustes_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_sofia/static/src/scss/*.scss',
            'dcasa_sofia/static/src/js/*.js',
            'dcasa_sofia/static/src/xml/*.xml',
        ],
    },
    'installable': True,
}
