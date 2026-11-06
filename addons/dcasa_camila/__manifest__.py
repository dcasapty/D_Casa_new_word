{
    'name': "D'CASA Panamá — Camila, la asistente del mail marketing",
    'summary': 'Arma la campaña de correo cada 15 días con lo que hay en tienda y el precio real de Odoo; una persona '
               'la aprueba y sale por Resend solo a quien dijo que sí',
    'description': """
Camila (decisiones de la dueña, 2026-11-06; docs/CAMILA.md):

* **El permiso del cliente** en su ficha (cuándo, por dónde y con quién): la casilla que marca la vendedora, el
  enlace firmado «¿Te avisamos de lo nuevo? Sí, quiero» al pie del correo de la factura y de la bienvenida, y el
  correo que dio cuando Sofía se lo pidió para avisarle de promociones (solo si el mensaje que salió lo decía). Una
  baja se respeta siempre; en la fusión de fichas se queda el permiso más reciente y cualquier baja manda.
* **La campaña** (Marketing › Camila): productos en tienda, con foto y publicados (lo nuevo, lo más vendido y lo
  quieto), el precio de la tienda en línea, el texto de la IA de Brian con revisión de marca (o un texto fijo), la
  vista previa en el celular, editar, «Volver a armar», «Enviarme una prueba» y «Enviar a N clientes». Una cada 15
  días como mucho; staging nunca envía; el servidor lo revisa todo.
* **Resend Broadcasts** con su propia clave (``RESEND_CAMPANAS_API_KEY``, Full access): el segmento queda igual a
  Odoo antes de cada envío y cada hora (las bajas de Resend vuelven a la ficha y las de Odoo suben).
* **Resultados**: a cuántos se envió, los chats que llegaron con la marca de la campaña y sus ventas (la atribución
  de Conversaciones), y las aperturas y clics que da Resend. Brian: ``estado_campanas``.
""",
    'version': '19.0.1.0.0',
    'category': 'Marketing',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_correo', 'dcasa_marketing', 'dcasa_conversaciones', 'dcasa_sofia', 'dcasa_brian',
                'dcasa_contactos', 'website_dcasa'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/correo_templates.xml',
        'views/novedades_templates.xml',
        'views/res_partner_views.xml',
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
