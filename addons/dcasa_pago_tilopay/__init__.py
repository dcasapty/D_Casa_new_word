import logging

from odoo.addons.payment import reset_payment_provider, setup_provider

from . import controllers, models

_logger = logging.getLogger(__name__)

CODIGO = 'tilopay'


def _preparar(env):
    proveedor = env.ref('dcasa_pago_tilopay.payment_provider_tilopay', raise_if_not_found=False)
    if proveedor:
        proveedor._dcasa_tilopay_preparar()


def post_init_hook(env):
    """Al instalar: la cuenta de método de pago de Odoo, el diario «Tilopay» y los mensajes en español.

    El proveedor nace APAGADO (data/payment_provider_data.xml): Gerencia lo enciende cuando las claves ya están en
    Cloudflare. Se puede repetir sin duplicar nada.

    En una base nueva Odoo carga el plan contable al FINAL de la carga del registro y borra los diarios que ya existían:
    el diario «Tilopay» se crea después de ese plan (nos colgamos del mismo punto que ``dcasa_base``). Y, si aun así
    faltara, al encender el proveedor se crea (``payment.provider._activate_default_pms``).
    """
    setup_provider(env, CODIGO)
    pendiente = getattr(env.registry, '_auto_install_template', None)
    if pendiente is None:
        _preparar(env)
        return

    def despues_del_plan(entorno):
        pendiente(entorno)
        _preparar(entorno)

    env.registry._auto_install_template = despues_del_plan


def uninstall_hook(env):
    reset_payment_provider(env, CODIGO)
