from . import models


def _dcasa_correo_post_init(env):
    """Al instalar: la factura al pagar y la bienvenida quedan listas (el interruptor general sigue APAGADO) y se
    guarda desde cuándo un cliente cuenta como nuevo para la bienvenida (los de antes no la reciben nunca)."""
    from odoo import fields

    from .models.correo import P_AL_PAGAR, P_BIENVENIDA, P_BIENVENIDA_DESDE

    ICP = env['ir.config_parameter'].sudo()
    for clave in (P_AL_PAGAR, P_BIENVENIDA):
        if not ICP.get_param(clave):   # sin guardar (Odoo devuelve False)
            ICP.set_param(clave, 'True')
    if not ICP.get_param(P_BIENVENIDA_DESDE):
        ICP.set_param(P_BIENVENIDA_DESDE, fields.Datetime.to_string(fields.Datetime.now()))
