from . import models, wizard


def _dcasa_envios_uninstall(env):
    """Al desinstalar, vuelve el «En desarrollo» de siempre en el menú Envíos."""
    menu = env.ref('dcasa_contabilidad.menu_envios_en_desarrollo', raise_if_not_found=False)
    if menu:
        menu.active = True
