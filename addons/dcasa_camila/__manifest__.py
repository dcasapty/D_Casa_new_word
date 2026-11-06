{
    'name': "D'CASA Panamá — Camila, la asistente del mail marketing",
    'summary': 'Campañas de correo con lo que hay en tienda y el precio real de Odoo, para el público que elijas; una '
               'persona las aprueba y salen por Resend solo a quien dijo que sí, una cada 15 días por cliente',
    'description': """
Camila (decisiones de la dueña, 2026-11-06; docs/CAMILA.md):

* **El permiso del cliente** en su ficha (cuándo, por dónde y con quién): la casilla que marca la vendedora, el
  enlace firmado «¿Te avisamos de lo nuevo? Sí, quiero» al pie del correo de la factura y de la bienvenida, y el
  correo que dio cuando Sofía se lo pidió para avisarle de promociones (solo si el mensaje que salió lo decía). Una
  baja se respeta siempre; en la fusión de fichas se queda el permiso más reciente y cualquier baja manda.
* **Las campañas** (Marketing › Camila, y «Crear campaña con estos» en el tablero de Marketing): varias a la vez, para
  públicos distintos del CRM; productos en tienda, con foto y publicados, el precio de la tienda en línea, el
  redactor con la IA de Brian (por producto y desde una idea) con revisión de marca, «Previsualizar», «Enviarme una
  prueba» y «Enviar a N clientes». A cada cliente le llega como mucho una cada 15 días; staging nunca envía; el
  servidor lo revisa todo.
* **Resend Broadcasts** con su propia clave (``RESEND_CAMPANAS_API_KEY``, Full access): un segmento de envío que se
  deja exactamente con los destinatarios de cada campaña; las bajas van y vienen cada hora y antes de cada envío.
* **Juan sabe que el cliente vino del correo**: la campaña y sus productos van en lo que Odoo le pasa por
  conversación; la conversación queda con la etiqueta «Vino del correo» y la cotización dice de qué campaña.
* **Resultados**: a cuántos se envió, los chats que llegaron con la marca de la campaña y sus ventas (la atribución
  de Conversaciones), y las aperturas y clics que da Resend. Brian: ``estado_campanas``.
""",
    'version': '19.0.2.0.0',
    'category': 'Marketing',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_correo', 'dcasa_marketing', 'dcasa_conversaciones', 'dcasa_sofia', 'dcasa_brian',
                'dcasa_contactos', 'website_dcasa'],
    'data': [
        'security/ir.model.access.csv',
        'security/pregunta_reglas.xml',
        'data/ir_cron.xml',
        'data/etiqueta.xml',
        'views/correo_templates.xml',
        'views/novedades_templates.xml',
        'views/res_partner_views.xml',
        'views/venta_views.xml',
        'views/pregunta_views.xml',
        'views/camila_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_camila/static/src/scss/*.scss',
            'dcasa_camila/static/src/js/*.js',
            'dcasa_camila/static/src/xml/*.xml',
        ],
        'web.assets_frontend': [
            'dcasa_camila/static/src/frontend/novedades.scss',
        ],
    },
    'installable': True,
}
