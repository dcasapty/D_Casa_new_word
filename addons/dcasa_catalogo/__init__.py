from . import models
from .catalogo import cargar_catalogo, marcar_black_weekend


def _dcasa_catalogo_post_init(env):
    """Carga el catálogo cuando el plan contable de Panamá ya está (el ITBMS que se suma sale de ahí).

    En una base nueva, dcasa_base difiere el plan contable al final de la carga del
    registro; el catálogo se engancha detrás para usar el ITBMS de Panamá.
    """
    pendiente = getattr(env.registry, '_auto_install_template', None)
    if pendiente:
        def plan_y_catalogo(env):
            pendiente(env)
            cargar_catalogo(env)
            marcar_black_weekend(env)
        env.registry._auto_install_template = plan_y_catalogo
    else:
        cargar_catalogo(env)
        marcar_black_weekend(env)
