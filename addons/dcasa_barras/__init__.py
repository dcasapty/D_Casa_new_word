from . import models


def _dcasa_post_init(env):
    """El «Retiro en tienda (…)» de la tienda web sale en «Para retirar en tienda» del panel de Bodega."""
    env['delivery.carrier']._dcasa_marcar_retiro_inicial()
