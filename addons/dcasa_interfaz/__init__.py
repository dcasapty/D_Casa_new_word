from . import models


def _dcasa_interfaz_post_init(env):
    env['dcasa.tablero']._dcasa_configurar_inicio()
