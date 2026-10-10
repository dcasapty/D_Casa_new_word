{
    'name': "D'CASA Panamá — Conversaciones (bandeja de Juan)",
    'summary': "Bandeja de conversaciones con clientes y API para «Juan», el asistente de WhatsApp y redes",
    'description': """
Conversaciones con clientes (Juan)
==================================

La parte de Odoo de «Juan», el asistente que atiende a los clientes por WhatsApp, Telegram,
Messenger e Instagram con el nombre público «el equipo de D'CASA». El motor de IA vive en el Worker
``juan`` (Cloudflare); aquí vive **la verdad**:

* **Bandeja**: cada conversación (canal + id externo) con el cliente como ficha de Odoo (el celular
  es la llave, sin duplicar), sus mensajes como un chat, y cada mensaje también en el chatter del
  cliente. Una vendedora puede **atender** (el bot calla), escribir y **devolver al bot**.
* **Ajustes** editables por la dueña: nombre público, bot encendido global y por canal, horario
  (8:00–17:00, todos los días, hora de Panamá), seguimiento (5 h y 5 días, máximo 2, solo en horario
  laboral), tope mensual de IA, modelos, bienvenida, privacidad, palabras prohibidas y pausa.
* **API** ``/dcasa/juan/v1/*`` para el Worker (token ``JUAN_ODOO_TOKEN``): registrar mensajes
  (idempotente), estado, configuración, herramientas y su ejecución, y confirmación de seguimientos.
* **Herramientas del bot** con vista pública (productos publicados, existencias solo como etiqueta,
  precios «+ ITBMS», reglas de Socios solo desde ``puntos.json``, saldo con PIN), registradas en el
  registro de Brian bajo el usuario técnico ``juan`` (sin permisos internos) y auditadas en
  ``brian.accion``. Ninguna escribe puntos, precios, stock, facturas ni pagos.
* **Seguimiento**: Odoo decide quién y cuándo, solo para quien mostró intención de compra (oportunidad
  viva) y nunca compró (5 h solo en horario laboral, luego 5 días, máximo 2; ninguno si ya es cliente
  o pidió que no lo contacten) y pide al Worker que redacte y envíe.

Contrato completo: docs/JUAN.md. Guía para la dueña: docs/JUAN_ODOO.md.
""",
    'version': '19.0.1.2.0',
    'category': 'Sales/CRM',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_brian', 'dcasa_catalogo', 'dcasa_interfaz', 'dcasa_socios', 'dcasa_contactos', 'crm', 'sale_crm',
                'mail', 'bus'],
    'data': [
        'security/conversaciones_security.xml',
        'security/ir.model.access.csv',
        'data/conversaciones_data.xml',
        'data/ir_cron_data.xml',
        'data/ir_cron_panel.xml',
        'data/crm_data.xml',
        'data/conocimiento_data.xml',
        'data/etiquetas_data.xml',
        'views/ajustes_views.xml',
        'views/conversacion_views.xml',
        'views/mensaje_views.xml',
        'views/conocimiento_views.xml',
        'views/etiquetas_views.xml',
        'views/res_partner_views.xml',
        'views/menus.xml',
        'views/panel_views.xml',
        'views/crm_lead_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_conversaciones/static/src/scss/*.scss',
            'dcasa_conversaciones/static/src/js/*.js',
            'dcasa_conversaciones/static/src/xml/*.xml',
        ],
    },
    'installable': True,
    'application': True,
}
