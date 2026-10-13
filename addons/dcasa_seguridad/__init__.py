from . import controllers, models
from .models.parametros import aplicar_sesiones_admin


def _dcasa_seguridad_post_init(env):
    """Valores por defecto de las sesiones de administrador (12 h / 60 min).

    Solo si el grupo no tiene nada configurado: nunca pisa lo que un administrador ajustó.
    """
    grupo = env.ref('base.group_system')
    if not grupo.lock_timeout and not grupo.lock_timeout_inactivity:
        aplicar_sesiones_admin(env)
