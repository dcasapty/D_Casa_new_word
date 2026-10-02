{
    'name': "D'CASA Panamá — Brian, el asistente",
    'summary': "Asistente de IA para administrar D'CASA: chat en el panel, Telegram y MCP",
    'description': """
Brian ayuda al administrador a manejar toda la plataforma conversando: consulta ventas,
inventario, clientes, contabilidad y socios; y con su habilidad «el constructor» crea y
edita registros dentro de reglas claras (qué puede hacer solo, qué pide confirmación y
qué nunca hace). Funciona con Claude, ChatGPT, Grok, Llama u otro proveedor compatible,
incluso con modelos pequeños. Ver docs/BRIAN.md.
""",
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_interfaz', 'dcasa_contabilidad', 'dcasa_catalogo', 'dcasa_socios', 'mail'],
    'data': [
        'security/brian_security.xml',
        'security/ir.model.access.csv',
        'data/brian_data.xml',
        'views/brian_views.xml',
        'security/telegram_security.xml',
        'views/telegram_views.xml',
        'views/importacion_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_brian/static/src/scss/*.scss',
            'dcasa_brian/static/src/js/*.js',
            'dcasa_brian/static/src/xml/*.xml',
        ],
    },
    'external_dependencies': {'python': []},
    'installable': True,
}
