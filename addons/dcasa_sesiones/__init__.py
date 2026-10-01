from . import almacen
from . import controllers


def _dcasa_sesiones_post_load():
    """Odoo la llama al importar el módulo: como ``server_wide_module``, al arrancar el
    servidor (antes de la primera petición); si no, al cargar el registro de la base."""
    almacen.instalar()
