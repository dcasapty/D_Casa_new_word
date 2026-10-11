"""Se retiró la pantalla «Alta del equipo» (pedido de la dueña, 2026-10-11): Odoo ya quitó su modelo, menú y permisos,
pero deja las tablas de los dos asistentes (temporales, sin datos que valgan). Se borran para no dejar basura."""


def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS dcasa_equipo_alta_linea, dcasa_equipo_alta CASCADE")
