import logging

from odoo.addons.payment import reset_payment_provider, setup_provider

from . import controllers, models

_logger = logging.getLogger(__name__)

CODIGO = 'tilopay'


def post_init_hook(env):
    """Al instalar: la cuenta de método de pago de Odoo, el diario «Tilopay» y los mensajes en español.

    El proveedor nace APAGADO (data/payment_provider_data.xml): Gerencia lo enciende cuando las claves ya están en
    Cloudflare. Se puede repetir sin duplicar nada.
    """
    setup_provider(env, CODIGO)
    proveedor = env.ref('dcasa_pago_tilopay.payment_provider_tilopay', raise_if_not_found=False)
    if proveedor:
        proveedor._dcasa_tilopay_preparar()


def uninstall_hook(env):
    reset_payment_provider(env, CODIGO)
