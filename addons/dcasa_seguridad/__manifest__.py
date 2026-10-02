{
    'name': "D'CASA Panamá — Seguridad de acceso",
    'summary': "Doble factor (app de códigos y llaves de acceso), bloqueo progresivo, registro y avisos "
               "de inicios de sesión, sesiones de administrador con vencimiento, Turnstile y robots.txt para IA",
    'description': """
Seguridad del acceso al panel de D'CASA (docs/SEGURIDAD_ACCESO.md).

* Doble factor con una app de códigos (Google Authenticator, Microsoft Authenticator…):
  ``auth_totp`` de Odoo, en español. Llaves de acceso (passkeys): ``auth_passkey``.
* Obligatoriedad configurable (``DCASA_2FA_OBLIGATORIO`` → ``dcasa_seguridad.2fa_obligatorio``),
  APAGADA por defecto. Encendida, quien está en el alcance (administradores o todo el personal)
  y aún no tiene la app enrolada la enrola al entrar, antes de abrir el panel. No usa el código
  por correo de Odoo (``auth_totp.policy``): sin servidor de correo saliente dejaría a todos fuera.
* Bloqueo progresivo por IP tras intentos fallidos (base de Odoo: 5 fallos; luego 1, 2, 4…
  minutos, con tope ``dcasa_seguridad.bloqueo_tope_s``).
* Registro de inicios de sesión (correctos, fallidos y de segundo factor) en Ajustes › Usuarios ›
  Accesos al panel, con purga a los 180 días. Aviso por Telegram (canal de Brian, si está
  instalado y vinculado) cuando entra un administrador o le fallan la clave varias veces.
* Sesiones de administrador: cierre obligatorio a las 12 h y bloqueo de pantalla tras 60 min sin
  actividad (``auth_timeout``; configurable en el grupo o con variables de entorno).
* Cloudflare Turnstile (``website_cf_turnstile`` de Odoo) en el acceso, el registro, el cambio
  de clave y los formularios del sitio: apagado mientras no haya claves.
* robots.txt: política para rastreadores de IA (``dcasa_seguridad.robots_ia``).
""",
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'website',
        'auth_totp',
        'auth_totp_mail',
        'auth_passkey',
        'auth_timeout',
        'website_cf_turnstile',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/acceso_views.xml',
        'views/templates.xml',
    ],
    'post_init_hook': '_dcasa_seguridad_post_init',
    'installable': True,
    'application': False,
}
