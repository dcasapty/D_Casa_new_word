{
    'name': "D'CASA Panamá — Sesiones en la base",
    'summary': "Sesiones HTTP en PostgreSQL (el contenedor no tiene disco) y ruta de salud /dcasa/salud",
    'description': """
El contenedor de Cloudflare tiene disco efímero: con las sesiones de Odoo en disco,
cada reinicio o despliegue desconecta a todo el mundo (vendedoras, carritos, socios).

* Guarda las sesiones HTTP en la tabla ``dcasa_http_session`` de la base, con la
  misma lógica de Odoo (rotación, expiración, cierre de sesión desde «Dispositivos»).
  La llave es el SHA-256 del identificador: el identificador completo no queda en la base.
* La limpieza la hace el autovacuum diario de Odoo (``ir.http._gc_sessions``) con el
  mismo plazo (``sessions.max_inactivity_seconds``, 7 días por defecto).
* ``GET /dcasa/salud``: 200 ``{"ok": true}`` si la base responde, 503 si no. Sin sesión,
  sin cookie y sin versión: la usa el Worker del borde.

Debe cargarse como módulo de todo el servidor (``server_wide_modules = base,web,dcasa_sesiones``)
para que las sesiones vayan a la base desde la primera petición (ver ``almacen.py``).
""",
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [],
    'post_load': '_dcasa_sesiones_post_load',
    'installable': True,
    'application': False,
}
